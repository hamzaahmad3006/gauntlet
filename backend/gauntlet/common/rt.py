"""Real-time asyncio runtime.

Audio is paced in 20 ms frames, so timer precision matters. On Windows with Python 3.12 the default
event loop keeps time with ``time.monotonic`` (15.625 ms resolution) and considers any timer within
one clock tick "due", which turns 20 ms pacing into 15/31 ms bursts. ``run`` installs a loop whose
clock is ``perf_counter`` and raises the system timer resolution to 1 ms for the process lifetime.
On Linux the stock loop is already precise and is used unchanged.
"""

from __future__ import annotations

import asyncio
import sys
import time
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")

_timer_period_set = False


def _raise_windows_timer_resolution() -> None:
    global _timer_period_set
    if _timer_period_set or sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.WinDLL("winmm").timeBeginPeriod(1)
        _timer_period_set = True
    except OSError:  # pragma: no cover - best effort
        pass


if sys.platform == "win32":

    class PreciseEventLoop(asyncio.ProactorEventLoop):  # type: ignore[name-defined,misc]
        def __init__(self) -> None:
            super().__init__()
            self._clock_resolution = 1e-4

        def time(self) -> float:
            return time.perf_counter()

    def loop_factory() -> asyncio.AbstractEventLoop:
        _raise_windows_timer_resolution()
        return PreciseEventLoop()

else:

    def loop_factory() -> asyncio.AbstractEventLoop:
        return asyncio.new_event_loop()


def run(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro, loop_factory=loop_factory)
