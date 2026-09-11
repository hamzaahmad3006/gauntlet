"""The single measurement clock.

Every timestamp that participates in arithmetic comes from ``now_ns``. Wall-clock time is recorded
alongside for display only (SRS 17.1).

Deviation D-08 (docs/DECISIONS.md): the SRS names ``time.monotonic_ns()``. On Windows with
Python < 3.13 that clock is ``GetTickCount64`` with a 15.625 ms resolution, which alone would exceed
the calibration error budget. ``time.perf_counter_ns()`` is QueryPerformanceCounter on Windows
(100 ns) and CLOCK_MONOTONIC on Linux — the same clock the SRS intended — and is system-wide on
both, so two processes on one host share it (required by deviation D-06).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

NS_PER_MS = 1_000_000
NS_PER_S = 1_000_000_000


def now_ns() -> int:
    return time.perf_counter_ns()


def wall_now() -> datetime:
    return datetime.now(UTC)


def ns_to_ms(ns: int | float) -> float:
    return ns / NS_PER_MS


def ms_to_ns(ms: int | float) -> int:
    return int(round(ms * NS_PER_MS))
