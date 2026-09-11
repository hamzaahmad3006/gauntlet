"""ARC-030 caller agent — one synthetic call from dial to hang-up (SRS 13, state machine SRS 8.3).

States: opening -> pursuing (<-> interrupting) -> verifying -> closing. The state machine makes every
control decision; the language model only writes words. The caller's goal belief steers the
conversation, but success is decided later by the referee, never by the caller (SRS 8.4).

Per turn (SRS 13.2): produce the utterance (model with timeout, else scripted line), synthesise (cache,
provider, local), transmit through the chaos pipeline, await agent onset (bounded by the persona's
patience and TURN_TIMEOUT_MS), fire a scheduled interruption at onset + offset if one is due, await the
agent's offset, record the turn, publish ``metric.updated``.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from gauntlet.caller import policies
from gauntlet.caller.adapters.base import Transport, TransportError
from gauntlet.caller.brain import BrainContext, CallerBrain, ScriptedLines
from gauntlet.caller.interrupts import DEFAULT_LINES
from gauntlet.caller.media_session import MediaSession
from gauntlet.caller.transmit import Utterance
from gauntlet.caller.tts import SpeechSynth, SynthResult
from gauntlet.common.clock import now_ns, wall_now
from gauntlet.cost.calculator import RigCounters
from gauntlet.media.chaos import ChaosParams
from gauntlet.media.probe import ProbeConfig
from gauntlet.metrics.compute import (
    AgentWindow,
    CallMetrics,
    Interruption,
    TurnRecord,
    call_metrics,
    classify_interruption,
    latency,
)
from gauntlet.referee.transcribe import AgentTranscriber, NullTranscriber

AGENT_TURN_MAX_S = 30.0
PROMPT_LINE = "Hello? Are you still there?"
Publish = Callable[[str, dict[str, Any]], Awaitable[None]]


class Aborted(Exception):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass
class SessionConfig:
    turn_timeout_ms: int = 8000
    yield_timeout_ms: int = 2000
    dead_air_threshold_ms: int = 1500
    greeting_wait_ms: int = 3500
    speech_margin_db: float = 12.0
    record_audio: bool = True


@dataclass
class CallOutcome:
    ended: str  # conversation | errored
    reason_code: str | None
    turns: list[TurnRecord]
    events: list[dict[str, Any]]
    caller_intervals: list[tuple[int, int]]
    agent_intervals: list[tuple[int, int]]
    windows: list[AgentWindow]
    metrics: CallMetrics | None
    interruptions: list[Interruption]
    achieved_impairment: dict[str, Any]
    counters: RigCounters
    flags: set[str]
    fallbacks: dict[str, int]
    utterances: int
    cache_hits: int
    goal_believed_met: bool
    started_at: Any
    ended_at: Any
    t0_ns: int | None
    duration_ms: float | None
    wav: bytes | None = None
    peaks: bytes | None = None
    referee_engine: str = "none"
    referee_error: str | None = None
    connect_ms: float | None = None
    audio_in_ok: bool = False


@dataclass
class CallPlan:
    call_id: str
    seed: int
    scenario: dict[str, Any]
    persona: dict[str, Any]
    chaos: ChaosParams
    interruption_schedule: list[dict[str, Any]] = field(default_factory=list)
    epoch: int = 0


class CallSession:
    def __init__(self, plan: CallPlan, transport: Transport, synth: SpeechSynth, brain: CallerBrain,
                 transcriber: AgentTranscriber | None = None, config: SessionConfig | None = None,
                 publish: Publish | None = None, abort_event: asyncio.Event | None = None,
                 budget_ok: Callable[[], Awaitable[bool]] | None = None,
                 condition_source: Callable[[], tuple[int, ChaosParams]] | None = None):
        self.plan = plan
        self.transport = transport
        self.synth = synth
        self.brain = brain
        self.referee = transcriber or NullTranscriber()
        self.cfg = config or SessionConfig()
        self._publish = publish
        self.abort_event = abort_event or asyncio.Event()
        self._budget_ok = budget_ok
        self._condition_source = condition_source
        self.epoch = plan.epoch
        sc = plan.scenario
        self.timing = {"max_turns": 12, "max_duration_s": 120, "turn_timeout_ms": self.cfg.turn_timeout_ms,
                       **(sc.get("timing") or {})}
        self.policies = sc.get("behaviour_policies") or {}
        self.lines = ScriptedLines(list(sc.get("fallback_lines") or []))
        self.media = MediaSession(transport, plan.chaos, plan.seed,
                                  ProbeConfig(margin_db=self.cfg.speech_margin_db), record=self.cfg.record_audio,
                                  max_seconds=int(self.timing["max_duration_s"]) + 30,
                                  on_agent_frame=self.referee.feed)
        self.turns: list[TurnRecord] = []
        self.events: list[dict[str, Any]] = []
        self.interruptions = [Interruption(int(e["turn_idx"]), float(e["offset_ms"]))
                              for e in plan.interruption_schedule]
        self.counters = RigCounters()
        self.flags: set[str] = set()
        self.fallbacks: dict[str, int] = {}
        self.history: list[tuple[str, str]] = []
        self.utterances = 0
        self.cache_hits = 0
        self.goal_believed_met = False
        self._policy_done: set[str] = set()
        self._caller_utts: list[Utterance] = []
        self._closing_utt: Utterance | None = None
        self._interrupt_pcm: list[SynthResult] = []

    # -- helpers ----------------------------------------------------------------------------------
    def _event(self, kind: str, t_ns: int | None = None, **payload: Any) -> None:
        self.events.append({"t_ns": t_ns if t_ns is not None else now_ns(), "wall_at": wall_now().isoformat(),
                            "kind": kind, "payload": payload})

    async def _emit(self, kind: str, payload: dict[str, Any]) -> None:
        if self._publish is not None:
            with contextlib.suppress(Exception):
                await self._publish(kind, payload)

    def _fallback(self, kind: str) -> None:
        self.fallbacks[kind] = self.fallbacks.get(kind, 0) + 1

    def _check(self) -> None:
        if self.abort_event.is_set():
            raise Aborted("run_aborted")
        if self.media.failure:
            raise TransportError(self.media.failure)
        if self.media.rx_closed.is_set():
            raise TransportError(getattr(self.transport, "bye_reason", None) or "transport_disconnected")

    async def _spend_ok(self) -> None:
        if self._budget_ok is not None and not await self._budget_ok():
            raise Aborted("budget_exceeded")

    def _maybe_new_epoch(self) -> None:
        if self._condition_source is None:
            return
        epoch, params = self._condition_source()
        if epoch != self.epoch and self.media.tx is not None:
            self.epoch = epoch
            self.media.tx.apply_params_at_next_utterance(params, epoch)
            self._event("condition_change", epoch=epoch, parameters=params.to_profile())

    async def _synth(self, text: str, rate_mult: float = 1.0) -> SynthResult:
        rate = float(self.plan.persona.get("speech_rate", 1.0)) * rate_mult
        await self._spend_ok()
        res = await self.synth.synthesize(text, str(self.plan.persona.get("voice_id", "default")), rate)
        self.utterances += 1
        if res.cached:
            self.cache_hits += 1
        else:
            self.counters.tts_characters += res.characters
            self._event("cache_miss", provider=res.provider)
        if res.voice_substituted:
            self.flags.add("voice_substituted")
        if res.rate_applied_locally:
            self.flags.add("rate_applied_locally")
        if res.fallback:
            self.flags.add("synthesis_fallback")
            self._fallback("synthesis")
        return res

    async def _abortable(self, coro: Awaitable[Any], timeout_s: float) -> Any:
        """Run a bounded wait, checking the abort flag at least every second (abort within 10 s)."""
        task = asyncio.ensure_future(coro)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s + 1.0
        try:
            while True:
                done, _ = await asyncio.wait({task}, timeout=min(1.0, max(0.0, deadline - loop.time())))
                if done:
                    return task.result()
                self._check()
                if loop.time() >= deadline:
                    task.cancel()
                    return None
        finally:
            if not task.done():
                task.cancel()

    # -- the call ---------------------------------------------------------------------------------
    async def run(self) -> CallOutcome:
        started_at = wall_now()
        ended, reason = "conversation", None
        try:
            await self.media.start()
        except TransportError as e:
            return self._outcome("errored", e.reason_code, started_at)
        await self._emit("caller.connected", {"call_id": self.plan.call_id, "adapter": self.transport.name,
                                              "connect_ms": self.transport.connect_ms})
        await self.referee.start()
        if self.referee.error:
            self.flags.add("referee_unavailable")
        try:
            await self._conversation()
        except Aborted as e:
            ended, reason = "errored", e.reason_code
        except TransportError as e:
            ended, reason = "errored", e.reason_code
        except Exception as e:  # rig fault: record, never crash the worker
            ended, reason = "errored", "rig_backpressure"
            self._event("rig_fault", error=f"{type(e).__name__}: {e}"[:300])
        finally:
            if self.media.tx is not None:
                self.media.tx.cancel_all()
            await asyncio.sleep(0.05)
            await self.media.stop("done" if ended == "conversation" else (reason or "error"))
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self.referee.close(), 10)
        return self._outcome(ended, reason, started_at)

    async def _conversation(self) -> None:
        assert self.media.tx is not None and self.media.rx is not None
        tx, rx = self.media.tx, self.media.rx
        sc, persona = self.plan.scenario, self.plan.persona
        max_turns, max_s = int(self.timing["max_turns"]), float(self.timing["max_duration_s"])
        turn_timeout_s = min(float(self.timing["turn_timeout_ms"]) / 1000, float(persona.get("patience_s", 8)))

        # interruption audio is synthesised before dialling so its timing never waits on a provider
        lines = list(sc.get("interruption_lines") or DEFAULT_LINES)
        for i, _ in enumerate(self.interruptions):
            self._interrupt_pcm.append(await self._synth(lines[i % len(lines)]))

        # greeting window: many agents speak first
        greet = await self._abortable(rx.wait_onset(self.media.t0_ns or 0, self.cfg.greeting_wait_ms / 1000),
                                      self.cfg.greeting_wait_ms / 1000)
        if greet is not None:
            off = await self._abortable(rx.wait_offset(greet.t_ns, AGENT_TURN_MAX_S), AGENT_TURN_MAX_S)
            t0 = TurnRecord(0, t_agent_first_audio_ns=greet.t_ns, t_agent_last_audio_ns=off.t_ns if off else None)
            await self._fill_agent_text(t0)
            self.turns.append(t0)
            if t0.agent_text:
                self.history.append(("agent", t0.agent_text))
            await self._abortable(rx.wait_quiet(AGENT_TURN_MAX_S), AGENT_TURN_MAX_S)

        stage = "opening"
        consecutive_timeouts = 0
        carry: tuple[Utterance, TurnRecord] | None = None
        force_text: str | None = None
        turn = 1
        while True:
            self._check()
            if self.media.elapsed_s() > max_s:
                self._event("budget_exhausted", kind="duration")
                break
            self._maybe_new_epoch()

            if carry is not None:
                utt, rec = carry
                carry = None
            else:
                if turn > max_turns:
                    self._event("budget_exhausted", kind="turns")
                    break
                if stage == "closing":
                    break
                if stage != "opening" and turn >= max_turns - 1 and stage == "pursuing":
                    stage = "verifying"
                utt, rec = await self._caller_turn(turn, stage, force_text)
                force_text = None
                if stage == "opening":
                    stage = "pursuing"
            turn = rec.idx + 1
            t_last = utt.last_voiced_ns
            rec.t_caller_last_sample_ns = t_last
            rec.t_caller_last_nominal_ns = utt.last_voiced_nominal_ns
            rec.t_caller_first_voiced_ns = utt.first_voiced_ns
            if t_last is None:
                self.turns.append(rec)
                continue

            # Premature speech (CH-07) is an event: the agent began talking while the caller was still
            # mid-utterance. It is flagged and counted, but the turn's latency is still measured from the
            # caller's last voiced sample to the agent's next onset — unless the agent is *still talking*
            # at that instant, in which case it committed early and the latency is excluded.
            onset = None
            for ev in rx.events:
                if ev.kind == "speech_onset" and utt.first_voiced_ns is not None and utt.first_voiced_ns < ev.t_ns < t_last:
                    rec.premature = True
                    self._event("premature_speech", t_ns=ev.t_ns, turn=rec.idx)
                    break
            covering = next(((s, e) for s, e in rx.all_intervals(now_ns()) if s < t_last < e), None)
            if covering is not None:
                onset = next(ev for ev in rx.events if ev.kind == "speech_onset" and ev.t_ns == covering[0])
            else:
                onset = await self._abortable(rx.wait_onset(t_last, turn_timeout_s), turn_timeout_s)
            if onset is None:
                rec.censored = True
                self._event("dead_air", t_ns=t_last, turn=rec.idx, waited_ms=turn_timeout_s * 1000)
                self.turns.append(rec)
                await self._emit("metric.updated", {"call_id": self.plan.call_id, "turn_idx": rec.idx,
                                                    "latency_ms": None, "censored": True})
                consecutive_timeouts += 1
                if consecutive_timeouts >= 2:
                    break
                force_text = PROMPT_LINE
                continue
            consecutive_timeouts = 0
            rec.t_agent_first_audio_ns = onset.t_ns
            latency(rec)

            # scheduled interruption for this turn (CH-06)
            intr = next((i for i in self.interruptions if i.turn_idx == rec.idx and i.status == "pending"), None)
            if intr is not None:
                idx = self.interruptions.index(intr)
                pcm = self._interrupt_pcm[idx].pcm if idx < len(self._interrupt_pcm) else None
                if pcm is not None and len(pcm):
                    start_at = onset.t_ns + int(intr.scheduled_offset_ms * 1_000_000)
                    iu = tx.say(Utterance.from_pcm(pcm, text=lines[idx % len(lines)], kind="interruption",
                                                   start_at_ns=start_at))
                    await self._abortable(iu.wait(), 10)
                    self._caller_utts.append(iu)
                    intr.onset_ns = iu.first_voiced_ns
                    self._event("interrupt_fired", t_ns=iu.first_voiced_ns, turn=rec.idx,
                                offset_ms=intr.scheduled_offset_ms)
                    off = await self._abortable(
                        rx.wait_offset(intr.onset_ns or 0, self.cfg.yield_timeout_ms / 1000 + 0.5),
                        self.cfg.yield_timeout_ms / 1000 + 0.5)
                    rec.t_agent_last_audio_ns = off.t_ns if off else None
                    classify_interruption(intr, rx.all_intervals(now_ns()), self.cfg.yield_timeout_ms)
                    if intr.status == "not_applicable":
                        self._event("interrupt_not_applicable", t_ns=intr.onset_ns, turn=rec.idx)
                    rec.barge_stop_ms, rec.no_yield = intr.barge_stop_ms, intr.no_yield
                    rec.interruption_status = intr.status
                    await self._fill_agent_text(rec)
                    self._record(rec)
                    await self._emit_turn(rec)
                    # the interruption is the caller's next turn; its response is measured from its end
                    if not rx.speaking or intr.no_yield:
                        await self._abortable(rx.wait_quiet(AGENT_TURN_MAX_S), AGENT_TURN_MAX_S)
                    nxt = TurnRecord(rec.idx + 1, caller_text=iu.text, epoch=self.epoch)
                    self.history.append(("caller", iu.text))
                    carry = (iu, nxt)
                    continue

            off = await self._abortable(rx.wait_offset(onset.t_ns, AGENT_TURN_MAX_S), AGENT_TURN_MAX_S)
            rec.t_agent_last_audio_ns = off.t_ns if off else None
            await self._fill_agent_text(rec)
            self._record(rec)
            await self._emit_turn(rec)
            if stage == "verifying" and utt is not self._closing_utt:
                stage = "closing_next"
            if stage == "closing_next":
                utt2, rec2 = await self._caller_turn(rec.idx + 1, "closing", None)
                rec2.t_caller_first_voiced_ns = utt2.first_voiced_ns
                rec2.t_caller_last_sample_ns = utt2.last_voiced_ns
                self._closing_utt = utt2
                goodbye = await self._abortable(rx.wait_onset(utt2.last_voiced_ns or now_ns(), 3.0), 3.0)
                if goodbye is not None:
                    rec2.t_agent_first_audio_ns = goodbye.t_ns
                    latency(rec2)
                    o2 = await self._abortable(rx.wait_offset(goodbye.t_ns, 10.0), 10.0)
                    rec2.t_agent_last_audio_ns = o2.t_ns if o2 else None
                    await self._fill_agent_text(rec2)
                self._record(rec2)
                break
            if self.goal_believed_met and stage == "pursuing":
                stage = "verifying"

    async def _caller_turn(self, idx: int, stage: str, force_text: str | None) -> tuple[Utterance, TurnRecord]:
        assert self.media.tx is not None and self.media.rx is not None
        sc, persona = self.plan.scenario, self.plan.persona
        rec = TurnRecord(idx, epoch=self.epoch)
        inference_ms = 0.0
        if force_text:
            text = force_text
        elif stage == "opening":
            text = sc["opening_utterance"]
        elif stage == "verifying":
            text = sc.get("verify_line") or "Could you confirm the details for me?"
        elif stage == "closing":
            text = sc.get("closing_line") or "Thanks, goodbye."
        else:
            corr = policies.correction_due(self.policies, idx, self._policy_done)
            if policies.repetition_due(self.policies, idx, self._policy_done) and self.history:
                last_caller = next((t for s, t in reversed(self.history) if s == "caller"), None)
                text = last_caller or self.lines.next()
                self._policy_done.add("repetition")
                self._event("policy_repetition", turn=idx)
            else:
                await self._spend_ok()
                ctx = BrainContext(sc["objective"], persona, self.history, "pursue", idx,
                                   int(self.timing["max_turns"]))
                reply = await self.brain.next_utterance(ctx, self.lines)
                text = reply.text
                inference_ms = reply.inference_ms
                rec.fallback_used = reply.fallback_used
                rec.prompt_tokens, rec.completion_tokens = reply.prompt_tokens, reply.completion_tokens
                rec.usage_estimated = reply.usage_estimated
                self.counters.llm_prompt_tokens += reply.prompt_tokens
                self.counters.llm_completion_tokens += reply.completion_tokens
                if reply.fallback_used:
                    self._fallback("caller_line")
                    self._event("fallback_used", turn=idx, reason=reply.error)
                if reply.done or (not self.brain.enabled and self.lines.exhausted):
                    self.goal_believed_met = True
            if corr:
                text = f"{text} ... {corr}"
                self._policy_done.add("correction")
                self._event("policy_correction", turn=idx)

        # CH-07 slow caller and hesitation: a seeded mid-utterance pause
        pause_ms = policies.hesitation_pause(self.policies, self.plan.chaos.pause_ms)
        rate_mult = self.plan.chaos.speech_rate
        split = policies.split_for_pause(text) if pause_ms > 0 and stage not in ("closing",) else None
        synth_ms = 0.0
        cached_all = True
        if split:
            a = await self._synth(split[0], rate_mult)
            b = await self._synth(split[1], rate_mult)
            pcm, segments = policies.join_with_pause([a.pcm, b.pcm], pause_ms)
            synth_ms, cached_all = a.synthesis_ms + b.synthesis_ms, a.cached and b.cached
            self._event("policy_hesitation", turn=idx, pause_ms=pause_ms)
        else:
            s = await self._synth(text, rate_mult)
            pcm, segments, synth_ms, cached_all = s.pcm, None, s.synthesis_ms, s.cached
        rec.caller_text = text
        rec.inference_ms, rec.synthesis_ms = round(inference_ms, 3), round(synth_ms, 3)
        rec.rig_overhead_ms = round(inference_ms + synth_ms, 3)
        rec.cache_hit = cached_all
        rec.tts_chars = len(text)

        # extended silence policy: withhold audio after the agent finished
        silence = policies.extended_silence_ms(self.policies)
        if silence > 0 and idx > 1:
            self._event("policy_extended_silence", turn=idx, silence_ms=silence)
            await asyncio.sleep(silence / 1000)
        # never start talking over the agent unless this is a scheduled interruption: wait for a
        # human-sized gap after the agent's last word, so the caller does not jump into sentence pauses
        await self._abortable(self.media.rx.wait_silence(self._turn_gap_ms(), AGENT_TURN_MAX_S), AGENT_TURN_MAX_S)
        utt = self.media.tx.say(Utterance.from_pcm(pcm, text=text, segments=segments))
        self._event("caller_utterance_start", turn=idx)
        await self._abortable(utt.wait(), max(5.0, len(pcm) / 16000 + 5))
        self._event("caller_utterance_end", t_ns=utt.last_voiced_ns, turn=idx)
        self._caller_utts.append(utt)
        self.history.append(("caller", text))
        return utt, rec

    async def _fill_agent_text(self, rec: TurnRecord) -> None:
        if rec.t_agent_first_audio_ns is None or not self.referee.enabled:
            return
        end = rec.t_agent_last_audio_ns or now_ns()
        await self.referee.settle(end, timeout_s=1.5)
        text, conf = self.referee.text_between(rec.t_agent_first_audio_ns - 50_000_000, end + 200_000_000)
        rec.agent_text, rec.agent_confidence = text, conf
        if text:
            self.history.append(("agent", text))

    def _turn_gap_ms(self) -> float:
        """Silence the caller waits for before taking the floor. Impatient personas wait less."""
        tendency = float(self.plan.persona.get("interruption_tendency", 0.0))
        return 450.0 if tendency >= 0.6 else 700.0

    def _record(self, rec: TurnRecord) -> None:
        self.turns.append(rec)

    async def _emit_turn(self, rec: TurnRecord) -> None:
        await self._emit("metric.updated", {"call_id": self.plan.call_id, "turn_idx": rec.idx,
                                            "latency_ms": rec.latency_ms, "barge_stop_ms": rec.barge_stop_ms,
                                            "rig_overhead_ms": rec.rig_overhead_ms, "premature": rec.premature})

    # -- results ----------------------------------------------------------------------------------
    def _outcome(self, ended: str, reason: str | None, started_at: Any) -> CallOutcome:
        tx, rx = self.media.tx, self.media.rx
        end_ns = now_ns()
        caller_iv = list(tx.voiced_intervals) if tx else []
        agent_iv = rx.all_intervals(end_ns) if rx else []
        if rx is not None:
            for ev in rx.events:
                self._event(ev.kind, t_ns=ev.t_ns, level_db=round(ev.level_db, 2), truncated=ev.truncated)
            if "floor_fallback" in rx.probe.flags:
                self.flags.add("floor_fallback")
                self._event("floor_fallback")
            if rx.playout.max_lag_ns > 200_000_000:
                self.flags.add("playout_lag")
        # agent windows: from each caller utterance's last voiced sample to the next caller utterance
        windows: list[AgentWindow] = []
        utts = [u for u in self._caller_utts if u.last_voiced_ns is not None and u is not self._closing_utt]
        for i, u in enumerate(utts):
            nxt = next((v.first_voiced_ns for v in self._caller_utts[self._caller_utts.index(u) + 1:]
                        if v.first_voiced_ns is not None), None)
            windows.append(AgentWindow(u.last_voiced_ns, nxt if nxt is not None else end_ns))  # type: ignore[arg-type]
        for intr in self.interruptions:
            if intr.onset_ns is None and intr.status == "pending":
                intr.status = "not_reached"
        metrics = call_metrics(caller_iv, agent_iv, windows, self.cfg.dead_air_threshold_ms) if caller_iv else None
        if tx:
            self.events.sort(key=lambda e: e["t_ns"])
        # configured = the parameters in force at the end of the call (the last epoch); every epoch's
        # parameters are listed alongside in achieved["epochs"]
        achieved = self.media.chaos.stats.achieved(self.media.chaos.params)
        if tx:
            achieved["transmit_intervals"] = tx.achieved_intervals()
        if achieved.get("impairment_deviation"):
            self.flags.add("impairment_deviation")
        if self.transport.name == "livekit":
            self.counters.media_participant_minutes += self.media.elapsed_s() / 60
        self.counters.stt_audio_seconds += self.referee.audio_seconds
        rec = self.media.recorder
        return CallOutcome(
            ended=ended, reason_code=reason, turns=self.turns, events=self.events, caller_intervals=caller_iv,
            agent_intervals=agent_iv, windows=windows, metrics=metrics, interruptions=self.interruptions,
            achieved_impairment=achieved, counters=self.counters, flags=self.flags, fallbacks=self.fallbacks,
            utterances=self.utterances, cache_hits=self.cache_hits, goal_believed_met=self.goal_believed_met,
            started_at=started_at, ended_at=wall_now(), t0_ns=self.media.t0_ns,
            duration_ms=round(self.media.elapsed_s() * 1000, 3) if self.media.t0_ns else None,
            wav=rec.wav_bytes() if rec is not None and rec.duration_s > 0 else None,
            peaks=rec.peaks_json() if rec is not None and rec.duration_s > 0 else None,
            referee_engine=self.referee.engine, referee_error=self.referee.error,
            connect_ms=self.transport.connect_ms,
            audio_in_ok=bool(rx and rx.audio_frames_above_floor >= 25),
        )


def turn_payload(rec: TurnRecord) -> dict[str, Any]:
    return {k: v for k, v in rec.__dict__.items() if k != "extra"}


def silence_pcm(ms: float) -> np.ndarray:
    return np.zeros(int(ms * 16), dtype=np.int16)
