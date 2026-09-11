"""Transport interface every media adapter satisfies."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

import numpy as np


class TransportError(Exception):
    """Carries the terminal reason code from the SRS 28.2 vocabulary."""

    def __init__(self, reason_code: str, message: str = ""):
        super().__init__(message or reason_code)
        self.reason_code = reason_code


class Transport(ABC):
    name = "base"

    def __init__(self) -> None:
        self.markers: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.connect_ms: float | None = None
        self.stats: dict[str, Any] = {}

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def send_frame(self, frame: np.ndarray) -> None:
        """Hand one 20 ms, 16 kHz mono int16 frame to the transport."""

    @abstractmethod
    def frames(self) -> AsyncIterator[tuple[np.ndarray, int]]:
        """Yield (frame, t_recv_ns) for every received 20 ms frame, in arrival order."""

    @abstractmethod
    async def close(self, reason: str = "done") -> None: ...
