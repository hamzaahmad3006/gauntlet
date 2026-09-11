"""UUID v7 (time-ordered) identifiers (SRS 9: "All identifiers are UUID v7 for time-ordered locality")."""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """RFC 9562 layout: 48-bit Unix ms | version 7 | 12 random bits | variant 10 | 62 random bits."""
    ms = (time.time_ns() // 1_000_000) & ((1 << 48) - 1)
    rand_a = int.from_bytes(os.urandom(2), "big") & 0x0FFF
    rand_b = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)
    return uuid.UUID(int=(ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b)


def new_id() -> uuid.UUID:
    return uuid7()
