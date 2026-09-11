"""One call's media plumbing: transport + chaos + transmitter + receive path + recorder, on one clock.

This is the object that makes "one process owns both directions" true (SRS 12.1): the transmit timeline
and the receive timeline are both stamped here by ``gauntlet.common.clock.now_ns``.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable

import numpy as np

from gauntlet.caller.adapters.base import Transport, TransportError
from gauntlet.caller.receive import ReceivePath
from gauntlet.caller.transmit import Transmitter
from gauntlet.common.clock import now_ns
from gauntlet.media.chaos import ChaosParams, ChaosPipeline
from gauntlet.media.probe import ProbeConfig
from gauntlet.media.recorder import CallRecorder


class MediaSession:
    def __init__(self, transport: Transport, chaos_params: ChaosParams, call_seed: int,
                 probe_config: ProbeConfig | None = None, record: bool = True, max_seconds: int = 300,
                 on_agent_frame: Callable[[np.ndarray, int], None] | None = None):
        self.transport = transport
        self.chaos = ChaosPipeline(chaos_params, call_seed)
        self.probe_config = probe_config
        self.record = record
        self.max_seconds = max_seconds
        self.on_agent_frame = on_agent_frame
        self.recorder: CallRecorder | None = None
        self.tx: Transmitter | None = None
        self.rx: ReceivePath | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self.t0_ns: int | None = None
        self.failure: str | None = None  # reason code once the media path has died
        self.rx_closed = asyncio.Event()

    async def start(self) -> None:
        await self.transport.connect()  # raises TransportError(connect_failed | auth_failed | ...)
        self.t0_ns = now_ns()
        self.recorder = CallRecorder(self.t0_ns, self.max_seconds) if self.record else None
        self.tx = Transmitter(self.transport, self.chaos, self.recorder)
        self.rx = ReceivePath(self.probe_config, self.recorder, on_frame=self.on_agent_frame)
        self._tasks = [asyncio.create_task(self._run_tx(), name="tx"), asyncio.create_task(self._run_rx(), name="rx")]

    async def _run_tx(self) -> None:
        assert self.tx is not None
        try:
            await self.tx.run()
        except TransportError as e:
            self.failure = self.failure or e.reason_code
        except asyncio.CancelledError:
            raise
        except Exception:
            self.failure = self.failure or "rig_backpressure"

    async def _run_rx(self) -> None:
        assert self.rx is not None
        try:
            async for frame, t in self.transport.frames():
                self.rx.feed(frame, t)
            if getattr(self.transport, "bye_reason", None) not in (None, "done"):
                self.failure = self.failure or "transport_disconnected"
        except TransportError as e:
            self.failure = self.failure or e.reason_code
        except asyncio.CancelledError:
            raise
        finally:
            self.rx_closed.set()

    async def stop(self, reason: str = "done") -> None:
        if self.tx is not None:
            self.tx.stop()
        await self.transport.close(reason)
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        if self.rx is not None:
            self.rx.finish()

    def elapsed_s(self) -> float:
        return 0.0 if self.t0_ns is None else (now_ns() - self.t0_ns) / 1e9
