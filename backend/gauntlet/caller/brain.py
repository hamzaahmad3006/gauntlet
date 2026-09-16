"""Caller utterance generation (SRS-FR-040, -041, SRS 13).

The language model only writes the *words* of the next caller utterance. Every control decision — when
to speak, interrupt, stay silent, verify or hang up — is made by the session's state machine. The model
receives the objective, never the goal checklist (SRS 14.3), so it cannot recite the checklist.

Inference is raced against CALLER_LLM_TIMEOUT_MS; on timeout or error the scenario's scripted fallback
lines supply the utterance and ``fallback_used`` is recorded. There are no retries inside a live turn
(SRS 28.3).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
from dataclasses import dataclass, field
from typing import Any

import httpx

from gauntlet.common.clock import now_ns
from gauntlet.common.llm import FALLBACK_MODEL, reasoning_params, resolve_model

MAX_UTTERANCE_CHARS = 320

VERBOSITY = {"terse": "Answer in at most 8 words.", "normal": "Answer in at most 16 words.",
             "verbose": "Answer in at most 28 words, chatty but on topic."}


@dataclass
class BrainContext:
    objective: str
    persona: dict[str, Any]
    history: list[tuple[str, str]]  # (speaker, text) with speaker in {"caller", "agent"}
    stage: str  # pursue | verify
    turn: int
    max_turns: int


@dataclass
class BrainReply:
    text: str
    done: bool
    fallback_used: bool
    inference_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    usage_estimated: bool = False
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class ScriptedLines:
    """Deterministic walk through a scenario's fallback lines."""

    def __init__(self, lines: list[str]):
        self.lines = lines or ["Sorry, could you repeat that?"]
        self.i = 0

    def next(self) -> str:
        line = self.lines[min(self.i, len(self.lines) - 1)]
        self.i += 1
        return line

    @property
    def exhausted(self) -> bool:
        return self.i >= len(self.lines)


class CallerBrain:
    def __init__(self, api_key: str = "", base_url: str = "https://api.groq.com/openai/v1",
                 model: str = "qwen/qwen3.6-27b", timeout_ms: int = 400, temperature: float = 0.6,
                 seed: int | None = None):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = resolve_model(model)
        self.timeout_ms = timeout_ms
        self.temperature = temperature
        self.seed = seed
        self._client: httpx.AsyncClient | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()

    async def warm(self) -> None:
        """Open the provider connection before the first turn. A cold TLS handshake alone can exceed the
        inference bound, which would push the first caller turn onto a scripted line."""
        if not self.enabled:
            return
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        with contextlib.suppress(Exception):
            await self._client.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"},
                                   timeout=3.0)

    def _messages(self, ctx: BrainContext) -> list[dict[str, str]]:
        p = ctx.persona
        system = (
            "You are role-playing a phone caller talking to a business's voice assistant. "
            f"Your goal: {ctx.objective} "
            f"Persona: {p.get('description', 'an ordinary caller')}. {VERBOSITY.get(p.get('verbosity', 'normal'))} "
            "Speak naturally, one short turn at a time, only as the caller. Never describe actions, never use "
            "stage directions, never mention being an AI or a test. "
            'Reply with JSON: {"say": "<exactly what you say next>", "done": <true once the goal is fully '
            'achieved and confirmed, else false>}.'
        )
        if ctx.stage == "verify":
            system += " Now ask the assistant to confirm the full details back to you."
        msgs = [{"role": "system", "content": system}]
        for speaker, text in ctx.history[-16:]:
            msgs.append({"role": "user" if speaker == "agent" else "assistant", "content": text})
        if not ctx.history or ctx.history[-1][0] != "agent":
            msgs.append({"role": "user", "content": "[the assistant is silent]"})
        return msgs

    async def next_utterance(self, ctx: BrainContext, fallback: ScriptedLines) -> BrainReply:
        t0 = now_ns()
        if not self.enabled:
            return BrainReply(fallback.next(), fallback.exhausted, True, 0.0, error="no_provider")
        msgs = self._messages(ctx)
        try:
            reply = await asyncio.wait_for(self._call(msgs), self.timeout_ms / 1000)
            reply.inference_ms = (now_ns() - t0) / 1e6
            if not reply.text:
                raise ValueError("empty utterance")
            return reply
        except Exception as e:  # timeout or provider fault: scripted line, recorded (SRS-FR-041)
            prompt_chars = sum(len(m["content"]) for m in msgs)
            return BrainReply(fallback.next(), False, True, (now_ns() - t0) / 1e6,
                              prompt_tokens=math.ceil(prompt_chars / 4), usage_estimated=True,
                              error=type(e).__name__)

    async def _call(self, msgs: list[dict[str, str]]) -> BrainReply:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        body: dict[str, Any] = {"model": self.model, "messages": msgs, "temperature": self.temperature,
                                "max_tokens": 400, "response_format": {"type": "json_object"},
                                **reasoning_params(self.model)}
        if self.seed is not None:
            body["seed"] = self.seed
        r = await self._client.post(f"{self.base_url}/chat/completions", json=body,
                                    headers={"Authorization": f"Bearer {self.api_key}"})
        if r.status_code == 404 and self.model != FALLBACK_MODEL:  # the model left the provider's catalogue
            self.model = FALLBACK_MODEL
            body["model"] = FALLBACK_MODEL
            body.update(reasoning_params(FALLBACK_MODEL))
            r = await self._client.post(f"{self.base_url}/chat/completions", json=body,
                                        headers={"Authorization": f"Bearer {self.api_key}"})
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        try:
            parsed = json.loads(content)
            text, done = str(parsed.get("say", "")).strip(), bool(parsed.get("done", False))
        except json.JSONDecodeError:
            text, done = content.strip(), False
        usage = data.get("usage") or {}
        est = not usage
        return BrainReply(
            text=text[:MAX_UTTERANCE_CHARS], done=done, fallback_used=False, inference_ms=0.0,
            prompt_tokens=int(usage.get("prompt_tokens") or math.ceil(sum(len(m["content"]) for m in msgs) / 4)),
            completion_tokens=int(usage.get("completion_tokens") or math.ceil(len(content) / 4)),
            usage_estimated=est,
        )
