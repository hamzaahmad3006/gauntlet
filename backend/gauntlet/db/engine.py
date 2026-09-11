"""Engine lifecycle. Schema creation is idempotent and runs as the release step (D-21)."""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from gauntlet.db.tables import metadata

_engine: AsyncEngine | None = None


def make_engine(url: str) -> AsyncEngine:
    if url.startswith("sqlite"):
        eng = create_async_engine(url, connect_args={"timeout": 30})

        @event.listens_for(eng.sync_engine, "connect")
        def _pragmas(dbapi_conn, _):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

        return eng
    return create_async_engine(url, pool_size=10, max_overflow=10, pool_pre_ping=True)


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("database engine not initialised")
    return _engine


async def init_engine(url: str, create_schema: bool = True) -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = make_engine(url)
    if create_schema:
        async with _engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
    return _engine


async def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
