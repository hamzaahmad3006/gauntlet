"""Builds the app: middleware chain, routers, lifespan. Decides nothing.

Middleware order: request id first, then CORS, then the error handlers, then routers. In development
with no REDIS_URL, the worker and sweeper run inside this process (D-12).
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gauntlet.common.paths import REPO_ROOT

if str(REPO_ROOT) not in sys.path:  # fixtures/ lives at the repository root
    sys.path.insert(0, str(REPO_ROOT))

from gauntlet.common.logging import configure  # noqa: E402
from gauntlet.common.settings import get_settings  # noqa: E402
from gauntlet.context import build_context, close_context  # noqa: E402
from gauntlet.middleware import errors  # noqa: E402
from gauntlet.middleware.request_id import RequestIdMiddleware  # noqa: E402
from gauntlet.routes import routers  # noqa: E402

VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure(settings.log_level)
    c = await build_context(settings)
    stop = asyncio.Event()
    tasks: list[asyncio.Task[None]] = []
    if c.broker.in_process or settings.environment == "development":
        from gauntlet.orchestrator.sweeper import sweep_forever
        from gauntlet.worker.main import worker_loop

        tasks = [asyncio.create_task(worker_loop(stop, "in-process")), asyncio.create_task(sweep_forever(stop))]
    try:
        yield
    finally:
        stop.set()
        for t in tasks:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        await close_context()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="GAUNTLET API", version=VERSION, lifespan=lifespan,
                  description="The infrastructure crash-test rig for real-time voice AI.")
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()] or [settings.app_base_url]
    if settings.is_dev:
        origins += ["http://localhost:5173", "http://127.0.0.1:5173"]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Last-Event-ID",
                                      "X-Correlation-Id"],
                       expose_headers=["X-Correlation-Id", "Retry-After", "X-RateLimit-Remaining"])
    app.add_middleware(RequestIdMiddleware, version=VERSION)
    errors.install(app)
    for r in routers:
        app.include_router(r)
    return app


app = create_app()
