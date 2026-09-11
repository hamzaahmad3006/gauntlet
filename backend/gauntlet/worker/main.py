"""Worker role (SRS 1.7 Role B): consume call jobs from the queue and run them, at most
MAX_CALLS_PER_WORKER at a time. The same code runs inside the API process in development (D-12).

    python -m gauntlet.worker.main
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
from uuid import UUID

from gauntlet.context import build_context, close_context, ctx
from gauntlet.orchestrator.sweeper import sweep_forever
from gauntlet.worker.executor import execute_call

log = logging.getLogger("gauntlet.worker")


async def worker_loop(stop: asyncio.Event, worker_id: str | None = None) -> None:
    c = ctx()
    wid = worker_id or f"{socket.gethostname()}-{os.getpid()}"
    limit = asyncio.Semaphore(c.settings.max_calls_per_worker)
    running: set[asyncio.Task[None]] = set()
    log.info("worker started", extra={"worker_id": wid})
    while not stop.is_set():
        await limit.acquire()
        try:
            msg = await c.broker.claim(wid, block_ms=1000)
        except Exception:
            limit.release()
            await asyncio.sleep(1.0)
            continue
        if msg is None:
            limit.release()
            continue
        msg_id, fields = msg

        async def job(mid: str = msg_id, f: dict[str, str] = fields) -> None:
            try:
                await execute_call(UUID(f["run_id"]), UUID(f["call_id"]), wid)
            except Exception:
                log.exception("job failed", extra={"call_id": f.get("call_id")})
            finally:
                with contextlib.suppress(Exception):
                    await c.broker.ack(mid)
                limit.release()

        t = asyncio.create_task(job())
        running.add(t)
        t.add_done_callback(running.discard)
    for t in list(running):
        t.cancel()


async def _main() -> None:
    from gauntlet.common.logging import configure
    from gauntlet.common.settings import get_settings

    settings = get_settings()
    configure(settings.log_level)
    await build_context(settings)
    stop = asyncio.Event()
    sweeper = asyncio.create_task(sweep_forever(stop))
    try:
        await worker_loop(stop)
    finally:
        stop.set()
        sweeper.cancel()
        await close_context()


def main() -> None:
    from gauntlet.common import rt

    rt.run(_main())


if __name__ == "__main__":
    main()
