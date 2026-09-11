"""Standalone WebSocket server for the calibration target / synthetic agent.

    python -m fixtures.calibration_target.server --port 8765

Connect with ``ws://127.0.0.1:8765/?mode=agent&delay_ms=400&yield_ms=250&endpoint_ms=500``.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
from urllib.parse import parse_qsl, urlparse

import websockets

from fixtures.calibration_target.session import FixtureConfig, FixtureSession
from gauntlet.common import rt
from gauntlet.common.clock import now_ns


async def handle(ws: websockets.ServerConnection) -> None:
    path = ws.request.path if ws.request else "/"
    try:
        cfg = FixtureConfig.from_query(dict(parse_qsl(urlparse(path).query)))
    except ValueError as e:
        await ws.close(code=1008, reason=str(e)[:100])
        return
    session = FixtureSession(cfg, ws.send, ws.send)
    pacer: asyncio.Task[None] | None = None
    try:
        async for msg in ws:
            if isinstance(msg, str):
                if not await session.on_text(msg):
                    break
                if pacer is None and session.hello is not None:
                    pacer = asyncio.create_task(session.pace())
            else:
                session.on_frame(msg, now_ns())
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        session.stop()
        if pacer:
            pacer.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await pacer


async def serve(host: str = "127.0.0.1", port: int = 8765) -> websockets.Server:
    return await websockets.serve(handle, host, port, compression=None, max_size=2**20)


async def _main(host: str, port: int) -> None:
    server = await serve(host, port)
    print(f"gauntlet fixture listening on ws://{host}:{port}/?mode=calibration|agent|echo", flush=True)
    await server.wait_closed()


def main() -> None:
    ap = argparse.ArgumentParser(description="GAUNTLET calibration target / synthetic agent")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    rt.run(_main(args.host, args.port))


if __name__ == "__main__":
    main()
