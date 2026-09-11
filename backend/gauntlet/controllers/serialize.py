"""Explicit response shapes. Encrypted columns and secrets are never included (SRS-SEC-002)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID


def jsonable(v: Any) -> Any:
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    return v


TARGET_FIELDS = ("id", "name", "adapter", "description", "bundled", "connection_hint", "verified_at",
                 "pipeline_declaration", "last_diagnostic", "baseline_run_id", "baseline_set_at", "speech_margin_db",
                 "created_at")


def target(row: dict[str, Any], include_prices: bool = True) -> dict[str, Any]:
    out = {k: jsonable(row.get(k)) for k in TARGET_FIELDS}
    out["unit_prices"] = jsonable(row.get("unit_prices")) if include_prices else None
    out["cost_model_declared"] = bool(row.get("unit_prices"))
    return out


RUN_FIELDS = ("id", "target_id", "suite_id", "suite_version_hash", "condition_profile_key", "condition_parameters",
              "threshold_profile_key", "threshold_version_hash", "definitions_version", "concurrency_requested",
              "concurrency_effective", "concurrency_peak", "repeats", "total_calls", "status", "flags", "spend_cap_usd",
              "rig_cost_usd", "rig_cost", "estimated_target_cost_usd", "grade", "overall", "label", "current_epoch",
              "epochs", "providers", "created_by", "pinned", "started_at", "ended_at", "created_at")


def run(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: jsonable(row.get(k)) for k in RUN_FIELDS}
    out["seed"] = str(row["seed"])  # 63-bit: string so JavaScript clients never round it
    return out


CALL_FIELDS = ("id", "run_id", "scenario_key", "persona_key", "coverage_tag", "repeat_index", "interruption_schedule",
               "status", "reason_code", "attempt", "talkover_ms", "dead_air_ratio", "duration_ms", "cache_hit_rate",
               "achieved_impairment", "interruptions", "fallbacks", "flags", "rig_cost_usd", "estimated_target_cost",
               "referee_engine", "referee_error", "connect_ms", "epoch_start", "started_at", "ended_at", "expires_at")


def call(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: jsonable(row.get(k)) for k in CALL_FIELDS}
    out["seed"] = str(row["seed"])
    out["has_audio"] = bool(row.get("audio_uri"))
    return out


def rows(items: list[dict[str, Any]], fn: Any) -> list[dict[str, Any]]:
    return [fn(i) for i in items]
