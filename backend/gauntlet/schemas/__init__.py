"""Pydantic request and response models. Response models never include encrypted columns, so a secret
cannot leak through a serialisation default (SRS-SEC-002)."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[Literal["run:create", "run:read", "gate:execute"]] = Field(min_length=1)


class TargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    adapter: Literal["livekit", "websocket_pcm"]
    connection: dict[str, Any]
    description: str | None = Field(default=None, max_length=500)
    pipeline_declaration: dict[str, Any] | None = None
    unit_prices: dict[str, Any] | None = None
    speech_margin_db: float | None = Field(default=None, ge=6, le=30)


class TargetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    adapter: str | None = None
    connection: dict[str, Any] | None = None
    description: str | None = Field(default=None, max_length=500)
    pipeline_declaration: dict[str, Any] | None = None
    unit_prices: dict[str, Any] | None = None
    speech_margin_db: float | None = Field(default=None, ge=6, le=30)


class SuiteCreate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    yaml: str = Field(min_length=1, max_length=256 * 1024)


class RunCreate(BaseModel):
    target_id: UUID
    suite_id: UUID
    condition_profile_key: str = "clean"
    threshold_profile_key: str = "default"
    concurrency: int = Field(default=5, ge=1, le=100)
    repeats: int = Field(default=1, ge=1, le=5)
    spend_cap_usd: float | None = Field(default=None, ge=0.10, le=50.0)
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    baseline_run_id: UUID | None = None
    scenario_keys: list[str] | None = None
    persona_keys: list[str] | None = None
    label: str | None = Field(default=None, max_length=120)


class ConditionChange(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
    profile_key: str | None = None


class BaselinePromote(BaseModel):
    run_id: UUID


class GateRequest(BaseModel):
    run_id: UUID
    baseline_run_id: UUID | None = None
    tolerance: float | None = Field(default=None, ge=0, le=100)


class ShareCreate(BaseModel):
    expires_in_days: int = Field(default=30, ge=1, le=90)
