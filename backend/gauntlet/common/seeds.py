"""ARC-018 seed service — deterministic derivation of every pseudo-random stream (SRS-FR-034).

A call's seed is derived from the run seed and the call's identity. Each consumer (chaos stages,
interruption schedule, behaviour policies, fallback-line choice) draws from its own named sub-stream,
so enabling one stage never shifts another stage's schedule.

Two narrowings of SRS-FR-034, both recorded in docs/DECISIONS.md:
- identity uses scenario and persona *keys* rather than row UUIDs. Keys are covered by the suite's
  content hash, so two runs on "the same suite" derive the same seeds even across workspaces;
- seeds are 63-bit (top bit of the blake2b digest cleared) so they round-trip through a PostgreSQL
  ``bigint`` unchanged. A seed that cannot be stored exactly cannot be reused exactly.
"""

from __future__ import annotations

import hashlib
import secrets

import numpy as np

SEED_MAX = 2**63 - 1


def new_run_seed() -> int:
    return secrets.randbits(63)


def validate_seed(seed: int) -> int:
    if not isinstance(seed, int) or not 0 <= seed <= SEED_MAX:
        raise ValueError(f"seed must be an integer between 0 and {SEED_MAX}")
    return seed


def _digest63(text: str) -> int:
    return int.from_bytes(hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest(), "big") & SEED_MAX


def call_seed(run_seed: int, scenario_key: str, persona_key: str, repeat_index: int) -> int:
    """Per-call seed: blake2b(f"{run_seed}:{scenario}:{persona}:{repeat}", 8 bytes), 63-bit."""
    validate_seed(run_seed)
    return _digest63(f"{run_seed}:{scenario_key}:{persona_key}:{repeat_index}")


def substream_seed(seed: int, stream: str) -> int:
    return _digest63(f"{seed}:{stream}")


def rng(seed: int, stream: str) -> np.random.Generator:
    """An independent, reproducible generator for one named consumer of a call seed."""
    return np.random.Generator(np.random.PCG64(substream_seed(seed, stream)))
