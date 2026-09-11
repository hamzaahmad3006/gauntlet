"""The bundled synthetic agent served by this deployment (`/fixtures/agent`), speaking gauntlet.pcm.v1.

Bundled targets dial this endpoint over the real network path, so the demo target exercises the same
WebSocket adapter as any third-party agent. It is a test fixture, not a product (LIMITATIONS 16).
"""

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from fixtures.calibration_target.session import FixtureConfig, FixtureSession
from gauntlet.common.clock import now_ns

router = APIRouter()


@router.websocket("/fixtures/agent")
async def fixture_agent(ws: WebSocket) -> None:
    try:
        cfg = FixtureConfig.from_query(dict(ws.query_params))
    except ValueError:
        await ws.close(code=1008)
        return
    await ws.accept()
    session = FixtureSession(cfg, ws.send_bytes, ws.send_text)
    pacer: asyncio.Task[None] | None = None
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                session.on_frame(msg["bytes"], now_ns())
            elif msg.get("text") is not None:
                if not await session.on_text(msg["text"]):
                    break
                if pacer is None and session.hello is not None:
                    pacer = asyncio.create_task(session.pace())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        session.stop()
        if pacer:
            pacer.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await pacer
        with contextlib.suppress(Exception):
            await ws.close()
