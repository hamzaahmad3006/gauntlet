"""Groq model names and per-family request parameters (D-31).

Groq retired the Llama 3.x models this project was built against. Stored targets and suites may still name
them, so a retired name resolves to its replacement instead of failing every call with model_not_found.
Reasoning models spend completion tokens thinking before they answer; for a caller turn that thinking is
latency, so it is switched off where the model allows and kept low otherwise, and never returned.
"""

from __future__ import annotations

from typing import Any

# Hosted catalogues change under a demo: each of these names returned model_not_found at some point during
# the build, so a stored target or suite naming one resolves to a model that exists instead of failing.
FALLBACK_MODEL = "openai/gpt-oss-20b"

RETIRED_MODELS = {
    "llama-3.1-8b-instant": FALLBACK_MODEL,
    "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b": FALLBACK_MODEL,
}


def resolve_model(model: str) -> str:
    return RETIRED_MODELS.get(model, model)


def reasoning_params(model: str, effort: str = "low") -> dict[str, Any]:
    if model.startswith("openai/gpt-oss"):
        return {"reasoning_effort": effort, "include_reasoning": False}
    if model.startswith("qwen/"):
        return {"reasoning_effort": "none"}
    return {}
