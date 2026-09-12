"""Process-wide application context: settings, database engine, broker, storage, keys, pricing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from gauntlet.caller.tts import SpeechSynth
from gauntlet.common.crypto import load_key
from gauntlet.common.paths import CALIBRATION_DIR, REPO_ROOT
from gauntlet.common.settings import Settings
from gauntlet.common.storage import Storage
from gauntlet.cost.calculator import Pricing, load_pricing
from gauntlet.db.engine import init_engine
from gauntlet.orchestrator.broker import Broker


@dataclass
class AppContext:
    settings: Settings
    engine: AsyncEngine
    broker: Broker
    storage: Storage
    key: bytes
    pricing: Pricing
    synth: SpeechSynth
    calibration: dict[str, Any] | None
    rig_benchmark: dict[str, Any] | None = None
    background: list[Any] = field(default_factory=list)


_ctx: AppContext | None = None


def ctx() -> AppContext:
    if _ctx is None:
        raise RuntimeError("application context not initialised")
    return _ctx


def _load_json(p) -> dict[str, Any] | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_calibration() -> dict[str, Any] | None:
    return _load_json(CALIBRATION_DIR / "summary.json")


def load_rig_benchmark() -> dict[str, Any] | None:
    """The committed rig benchmark: how much concurrency this rig sustains before its own timing slips."""
    return _load_json(REPO_ROOT / "benchmarks" / "summary.json")


async def build_context(settings: Settings) -> AppContext:
    global _ctx
    key = load_key(settings.secret_encryption_key, settings.environment)
    engine = await init_engine(settings.effective_database_url)
    broker = await Broker.create(settings.redis_url)
    storage = Storage(settings.s3_bucket, settings.s3_endpoint_url, settings.s3_access_key_id,
                      settings.s3_secret_access_key)
    synth = SpeechSynth(settings.elevenlabs_api_key, settings.elevenlabs_model, settings.elevenlabs_default_voice_id)
    _ctx = AppContext(settings, engine, broker, storage, key, load_pricing(), synth, load_calibration(),
                      load_rig_benchmark())
    return _ctx


async def close_context() -> None:
    global _ctx
    if _ctx is None:
        return
    await _ctx.broker.close()
    await _ctx.synth.aclose()
    from gauntlet.db.engine import dispose_engine

    await dispose_engine()
    _ctx = None
