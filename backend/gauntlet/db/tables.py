"""Database schema, SQLAlchemy Core (SRS 9, DB-001..DB-019).

Portable types (D-12): the same metadata creates PostgreSQL 15 tables in production (UUID, JSONB,
timestamptz, numeric) and SQLite tables in development. Arrays are stored as JSON lists. Every table
carrying user data has a non-null workspace_id, directly or through its parent (SRS-FR-002).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData()

JSON = sa.JSON().with_variant(JSONB(), "postgresql")
TS = sa.DateTime(timezone=True)
MONEY = sa.Numeric(12, 6, asdecimal=False)


def _id() -> sa.Column:
    return sa.Column("id", sa.Uuid, primary_key=True)


def _ts(name: str = "created_at", nullable: bool = False) -> sa.Column:
    return sa.Column(name, TS, nullable=nullable, server_default=sa.func.now() if not nullable else None)


# DB-001
workspaces = sa.Table(
    "workspaces", metadata, _id(),
    sa.Column("name", sa.String(80), nullable=False),
    _ts(),
    sa.Column("audio_retention_days", sa.Integer, nullable=False, server_default="7"),
    sa.Column("daily_spend_cap_usd", MONEY, nullable=False, server_default="5"),
    sa.Column("max_concurrent_runs", sa.Integer, nullable=False, server_default="2"),
    sa.CheckConstraint("audio_retention_days between 1 and 30", name="ck_ws_retention"),
)

# DB-002
users = sa.Table(
    "users", metadata, _id(),
    sa.Column("workspace_id", sa.Uuid, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True),
    sa.Column("auth_subject", sa.String(200), nullable=False, unique=True),
    sa.Column("github_login", sa.String(100)),
    sa.Column("email", sa.String(320)),
    _ts(),
)

# DB-003
api_keys = sa.Table(
    "api_keys", metadata, _id(),
    sa.Column("workspace_id", sa.Uuid, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True),
    sa.Column("name", sa.String(80), nullable=False),
    sa.Column("prefix", sa.String(8), nullable=False, unique=True),
    sa.Column("hash", sa.Text, nullable=False),
    sa.Column("scopes", JSON, nullable=False),
    _ts(),
    sa.Column("last_used_at", TS),
    sa.Column("revoked_at", TS),
)

# DB-004
targets = sa.Table(
    "targets", metadata, _id(),
    sa.Column("workspace_id", sa.Uuid, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
    sa.Column("name", sa.String(80), nullable=False),
    sa.Column("adapter", sa.String(20), nullable=False),
    sa.Column("description", sa.Text),
    sa.Column("bundled", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("connection_encrypted", sa.LargeBinary, nullable=False),
    sa.Column("connection_nonce", sa.LargeBinary, nullable=False),
    sa.Column("connection_hint", sa.String(120)),  # masked, display-only
    sa.Column("verified_at", TS),
    sa.Column("verification_nonce", sa.String(80)),
    sa.Column("verification_nonce_expires_at", TS),
    sa.Column("pipeline_declaration", JSON),
    sa.Column("unit_prices", JSON),
    sa.Column("speech_margin_db", sa.Float),
    sa.Column("last_diagnostic", JSON),
    sa.Column("baseline_run_id", sa.Uuid),
    sa.Column("baseline_set_at", TS),
    sa.Column("baseline_set_by", sa.String(120)),
    _ts(),
    sa.CheckConstraint("adapter in ('livekit','websocket_pcm')", name="ck_target_adapter"),
    sa.UniqueConstraint("workspace_id", "name", name="uq_target_name"),
    sa.Index("ix_targets_ws_created", "workspace_id", "created_at"),
)

# DB-005
suites = sa.Table(
    "suites", metadata, _id(),
    sa.Column("workspace_id", sa.Uuid, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
    sa.Column("key", sa.String(64), nullable=False),
    sa.Column("name", sa.String(120), nullable=False),
    sa.Column("version_hash", sa.String(64), nullable=False),
    sa.Column("parent_suite_id", sa.Uuid),
    sa.Column("yaml_source", sa.Text, nullable=False),
    sa.Column("document", JSON, nullable=False),
    _ts(),
    sa.UniqueConstraint("workspace_id", "version_hash", name="uq_suite_hash"),
)

# DB-006
scenarios = sa.Table(
    "scenarios", metadata, _id(),
    sa.Column("suite_id", sa.Uuid, sa.ForeignKey("suites.id", ondelete="CASCADE"), nullable=False),
    sa.Column("key", sa.String(64), nullable=False),
    sa.Column("coverage_tag", sa.String(20), nullable=False),
    sa.Column("definition", JSON, nullable=False),
    sa.Column("max_turns", sa.Integer, nullable=False, server_default="12"),
    sa.Column("max_duration_s", sa.Integer, nullable=False, server_default="120"),
    sa.UniqueConstraint("suite_id", "key", name="uq_scenario_key"),
    sa.CheckConstraint("coverage_tag in ('happy_path','edge_case','adversarial','out_of_scope')", name="ck_cov"),
)

# DB-007
personas = sa.Table(
    "personas", metadata, _id(),
    sa.Column("suite_id", sa.Uuid, sa.ForeignKey("suites.id", ondelete="CASCADE"), nullable=False),
    sa.Column("key", sa.String(64), nullable=False),
    sa.Column("voice_id", sa.String(64), nullable=False),
    sa.Column("speech_rate", sa.Float, nullable=False),
    sa.Column("patience_s", sa.Integer, nullable=False),
    sa.Column("definition", JSON, nullable=False),
    sa.UniqueConstraint("suite_id", "key", name="uq_persona_key"),
)

# DB-008
condition_profiles = sa.Table(
    "condition_profiles", metadata, _id(),
    sa.Column("workspace_id", sa.Uuid, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
    sa.Column("key", sa.String(64), nullable=False),
    sa.Column("parameters", JSON, nullable=False),
    _ts(),
    sa.UniqueConstraint("workspace_id", "key", name="uq_condition_key"),
)

# DB-009
threshold_profiles = sa.Table(
    "threshold_profiles", metadata, _id(),
    sa.Column("workspace_id", sa.Uuid, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
    sa.Column("key", sa.String(64), nullable=False),
    sa.Column("version_hash", sa.String(64), nullable=False),
    sa.Column("document", JSON, nullable=False),
    _ts(),
    sa.UniqueConstraint("workspace_id", "key", "version_hash", name="uq_threshold_version"),
)

# DB-010
runs = sa.Table(
    "runs", metadata, _id(),
    sa.Column("workspace_id", sa.Uuid, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
    sa.Column("target_id", sa.Uuid, sa.ForeignKey("targets.id", ondelete="RESTRICT"), nullable=False),
    sa.Column("suite_id", sa.Uuid, sa.ForeignKey("suites.id", ondelete="RESTRICT"), nullable=False),
    sa.Column("suite_version_hash", sa.String(64), nullable=False),
    sa.Column("condition_profile_key", sa.String(64), nullable=False),
    sa.Column("condition_parameters", JSON, nullable=False),
    sa.Column("threshold_profile_key", sa.String(64), nullable=False),
    sa.Column("threshold_version_hash", sa.String(64), nullable=False),
    sa.Column("threshold_document", JSON, nullable=False),
    sa.Column("definitions_version", sa.String(10), nullable=False),
    sa.Column("seed", sa.BigInteger, nullable=False),
    sa.Column("concurrency_requested", sa.Integer, nullable=False),
    sa.Column("concurrency_effective", sa.Integer, nullable=False),
    sa.Column("concurrency_peak", sa.Integer),
    sa.Column("repeats", sa.Integer, nullable=False, server_default="1"),
    sa.Column("total_calls", sa.Integer, nullable=False, server_default="0"),
    sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
    sa.Column("flags", JSON, nullable=False),
    sa.Column("spend_cap_usd", MONEY, nullable=False),
    sa.Column("rig_cost_usd", MONEY),
    sa.Column("rig_cost", JSON),
    sa.Column("estimated_target_cost_usd", MONEY),
    sa.Column("score", JSON),
    sa.Column("grade", sa.String(2)),
    sa.Column("overall", sa.Float),
    sa.Column("label", sa.String(120)),
    sa.Column("current_epoch", sa.Integer, nullable=False, server_default="0"),
    sa.Column("epochs", JSON, nullable=False),
    sa.Column("providers", JSON),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("idempotency_key", sa.String(200)),
    sa.Column("pinned", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("started_at", TS),
    sa.Column("ended_at", TS),
    _ts(),
    sa.CheckConstraint("status in ('queued','running','completed','aborted','aborted_budget','failed')", name="ck_run_status"),
    sa.Index("ix_runs_ws_created", "workspace_id", "created_at"),
    sa.Index("ix_runs_target_created", "target_id", "created_at"),
    sa.UniqueConstraint("workspace_id", "idempotency_key", name="uq_run_idem"),
)

# DB-011
calls = sa.Table(
    "calls", metadata, _id(),
    sa.Column("run_id", sa.Uuid, sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
    sa.Column("scenario_id", sa.Uuid, sa.ForeignKey("scenarios.id", ondelete="RESTRICT"), nullable=False),
    sa.Column("persona_id", sa.Uuid, sa.ForeignKey("personas.id", ondelete="RESTRICT"), nullable=False),
    sa.Column("scenario_key", sa.String(64), nullable=False),
    sa.Column("persona_key", sa.String(64), nullable=False),
    sa.Column("coverage_tag", sa.String(20), nullable=False),
    sa.Column("repeat_index", sa.Integer, nullable=False, server_default="0"),
    sa.Column("seed", sa.BigInteger, nullable=False),
    sa.Column("interruption_schedule", JSON, nullable=False),
    sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
    sa.Column("reason_code", sa.String(40)),
    sa.Column("attempt", sa.Integer, nullable=False, server_default="1"),
    sa.Column("worker_id", sa.String(80)),
    sa.Column("lease_expires_at", TS),
    sa.Column("talkover_ms", sa.Float),
    sa.Column("dead_air_ratio", sa.Float),
    sa.Column("duration_ms", sa.Float),
    sa.Column("cache_hit_rate", sa.Float),
    sa.Column("achieved_impairment", JSON),
    sa.Column("interruptions", JSON),
    sa.Column("fallbacks", JSON, nullable=False),
    sa.Column("flags", JSON, nullable=False),
    sa.Column("counters", JSON),
    sa.Column("rig_cost_usd", MONEY),
    sa.Column("estimated_target_cost", JSON),
    sa.Column("intervals", JSON),
    sa.Column("referee_engine", sa.String(40)),
    sa.Column("referee_error", sa.Text),
    sa.Column("connect_ms", sa.Float),
    sa.Column("epoch_start", sa.Integer, nullable=False, server_default="0"),
    sa.Column("audio_uri", sa.Text),
    sa.Column("waveform_uri", sa.Text),
    sa.Column("expires_at", TS),
    sa.Column("started_at", TS),
    sa.Column("ended_at", TS),
    sa.CheckConstraint("status in ('pending','dialling','in_call','scoring','completed','failed','needs_review','errored')",
                       name="ck_call_status"),
    sa.CheckConstraint("status in ('pending','dialling','in_call','scoring','completed') or reason_code is not null",
                       name="ck_call_reason"),
    sa.CheckConstraint("attempt <= 2", name="ck_call_attempt"),
    sa.Index("ix_calls_run_status", "run_id", "status"),
    sa.Index("ix_calls_expires", "expires_at"),
)

# DB-012
turns = sa.Table(
    "turns", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("call_id", sa.Uuid, sa.ForeignKey("calls.id", ondelete="CASCADE"), nullable=False),
    sa.Column("idx", sa.Integer, nullable=False),
    sa.Column("caller_text", sa.Text),
    sa.Column("agent_text", sa.Text),
    sa.Column("agent_confidence", sa.Float),
    sa.Column("t_caller_first_voiced_ns", sa.BigInteger),
    sa.Column("t_caller_last_sample_ns", sa.BigInteger),
    sa.Column("t_agent_first_audio_ns", sa.BigInteger),
    sa.Column("t_agent_last_audio_ns", sa.BigInteger),
    sa.Column("latency_ms", sa.Float),
    sa.Column("raw_latency_ms", sa.Float),
    sa.Column("censored", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("premature", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("rig_overhead_ms", sa.Float),
    sa.Column("inference_ms", sa.Float),
    sa.Column("synthesis_ms", sa.Float),
    sa.Column("cache_hit", sa.Boolean),
    sa.Column("barge_stop_ms", sa.Float),
    sa.Column("no_yield", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("interruption_status", sa.String(20)),
    sa.Column("fallback_used", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("epoch", sa.Integer, nullable=False, server_default="0"),
    sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
    sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
    sa.Column("usage_estimated", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.UniqueConstraint("call_id", "idx", name="uq_turn_idx"),
)

# DB-013
call_events = sa.Table(
    "call_events", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("call_id", sa.Uuid, sa.ForeignKey("calls.id", ondelete="CASCADE"), nullable=False),
    sa.Column("t_ns", sa.BigInteger, nullable=False),
    sa.Column("wall_at", TS, nullable=False),
    sa.Column("kind", sa.String(40), nullable=False),
    sa.Column("payload", JSON, nullable=False),
    sa.Index("ix_call_events_call_t", "call_id", "t_ns"),
    sa.Index("ix_call_events_call_kind", "call_id", "kind"),
)

# DB-014
verdicts = sa.Table(
    "verdicts", metadata, _id(),
    sa.Column("call_id", sa.Uuid, sa.ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, unique=True),
    sa.Column("task_success", sa.Boolean),
    sa.Column("steps", JSON, nullable=False),
    sa.Column("passes", JSON),
    sa.Column("needs_review", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("agreement", sa.Float),
    sa.Column("status", sa.String(20), nullable=False, server_default="scored"),
    sa.Column("model", sa.String(80), nullable=False),
    sa.Column("prompt_version", sa.String(20), nullable=False),
    _ts(),
)

# DB-015
run_metrics = sa.Table(
    "run_metrics", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("run_id", sa.Uuid, sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
    sa.Column("name", sa.String(64), nullable=False),
    sa.Column("value", sa.Float),
    sa.Column("n", sa.Integer, nullable=False),
    sa.Column("unit", sa.String(10), nullable=False),
    sa.Column("normalised", sa.Float),
    sa.Column("flags", JSON, nullable=False),
    sa.Column("epoch", sa.Integer),
    sa.UniqueConstraint("run_id", "name", "epoch", name="uq_run_metric"),
)

# DB-016
gates = sa.Table(
    "gates", metadata, _id(),
    sa.Column("workspace_id", sa.Uuid, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
    sa.Column("run_id", sa.Uuid, sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
    sa.Column("baseline_run_id", sa.Uuid, sa.ForeignKey("runs.id", ondelete="RESTRICT"), nullable=False),
    sa.Column("verdict", sa.String(10), nullable=False),
    sa.Column("breaches", JSON, nullable=False),
    sa.Column("markdown", sa.Text, nullable=False),
    sa.Column("tolerance", sa.Float, nullable=False),
    _ts(),
    sa.CheckConstraint("verdict in ('passed','failed','error')", name="ck_gate_verdict"),
)

# DB-017 — standalone rig-quality record, intentionally without foreign keys
calibrations = sa.Table(
    "calibrations", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("injected_ms", sa.Integer, nullable=False),
    sa.Column("measured_ms", sa.Float, nullable=False),
    sa.Column("error_ms", sa.Float, nullable=False),
    sa.Column("repetition", sa.Integer, nullable=False),
    sa.Column("condition_profile_key", sa.String(64), nullable=False),
    sa.Column("git_sha", sa.String(40), nullable=False),
    sa.Column("run_at", TS, nullable=False),
)

# DB-018
share_links = sa.Table(
    "share_links", metadata, _id(),
    sa.Column("run_id", sa.Uuid, sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
    sa.Column("workspace_id", sa.Uuid, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
    sa.Column("token", sa.String(64), nullable=False, unique=True),
    sa.Column("revoked_at", TS),
    sa.Column("expires_at", TS, nullable=False),
    _ts(),
)

# DB-019
audit_events = sa.Table(
    "audit_events", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("workspace_id", sa.Uuid, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
    sa.Column("actor", sa.String(120), nullable=False),
    sa.Column("action", sa.String(60), nullable=False),
    sa.Column("resource", sa.String(120), nullable=False),
    sa.Column("payload", JSON, nullable=False),
    _ts(),
)
