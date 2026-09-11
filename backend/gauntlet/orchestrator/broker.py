"""ARC-017 orchestrator primitives and ARC-019 event bus, on Redis (SRS 7 E, 11, 29).

One dependency serves queue, bus and limits. In development with no REDIS_URL, an in-process fakeredis
instance provides the identical API, and the worker runs inside the API process (D-12).

- Call jobs: one Redis Stream with a consumer group; a job is claimed by exactly one worker.
- Concurrency: a per-run hash of call_id -> lease expiry. A slot is taken under optimistic locking and
  the measured peak is updated in the same transaction, so ``concurrency_peak`` is observed, never assumed.
- Abort, spend and mid-run condition epochs: plain keys the worker polls at turn boundaries.
- Live events: a per-run stream with a monotonically increasing ``seq``; retained for the run's lifetime
  plus one hour, which is what makes Last-Event-ID replay lossless.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import ResponseError, WatchError

CALL_STREAM = "gauntlet:calls"
GROUP = "workers"


class Broker:
    def __init__(self, client: Any, in_process: bool):
        self.r = client
        self.in_process = in_process

    @classmethod
    async def create(cls, url: str) -> Broker:
        if url:
            client = aioredis.from_url(url, decode_responses=True, health_check_interval=30)
            b = cls(client, in_process=False)
        else:
            import fakeredis

            b = cls(fakeredis.aioredis.FakeRedis(decode_responses=True), in_process=True)
        await b.ensure_group()
        return b

    async def close(self) -> None:
        try:
            await self.r.aclose()
        except Exception:
            pass

    async def ping(self) -> bool:
        try:
            return bool(await self.r.ping())
        except Exception:
            return False

    # -- job queue -------------------------------------------------------------------------------
    async def ensure_group(self) -> None:
        try:
            await self.r.xgroup_create(CALL_STREAM, GROUP, id="0", mkstream=True)
        except ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def enqueue(self, run_id: str, call_id: str) -> str:
        return await self.r.xadd(CALL_STREAM, {"run_id": run_id, "call_id": call_id})

    async def _poll(self, fn: Any, block_ms: int) -> Any:
        """fakeredis ignores BLOCK and returns at once; emulate blocking by polling so an in-process
        consumer never busy-spins the event loop."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + block_ms / 1000
        while True:
            res = await fn()
            if res or loop.time() >= deadline:
                return res
            await asyncio.sleep(0.05)

    async def claim(self, consumer: str, block_ms: int = 2000) -> tuple[str, dict[str, str]] | None:
        if self.in_process:
            res = await self._poll(lambda: self.r.xreadgroup(GROUP, consumer, {CALL_STREAM: ">"}, count=1), block_ms)
        else:
            res = await self.r.xreadgroup(GROUP, consumer, {CALL_STREAM: ">"}, count=1, block=block_ms)
        if not res:
            return None
        _, entries = res[0]
        if not entries:
            return None
        msg_id, fields = entries[0]
        return msg_id, fields

    async def ack(self, msg_id: str) -> None:
        await self.r.xack(CALL_STREAM, GROUP, msg_id)
        await self.r.xdel(CALL_STREAM, msg_id)

    async def queue_depth(self) -> int:
        try:
            info = await self.r.xinfo_groups(CALL_STREAM)
            return int(sum(int(g.get("lag") or 0) for g in info)) if info else 0
        except Exception:
            return int(await self.r.xlen(CALL_STREAM))

    # -- concurrency slots -----------------------------------------------------------------------
    def _slots(self, run_id: str) -> str:
        return f"run:{run_id}:slots"

    async def acquire_slot(self, run_id: str, call_id: str, limit: int, lease_s: int = 300) -> bool:
        key, peak_key = self._slots(run_id), f"run:{run_id}:peak"
        expiry = int((time.time() + lease_s) * 1000)
        for _ in range(20):
            async with self.r.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(key, peak_key)
                    active = await pipe.hlen(key)
                    if await pipe.hexists(key, call_id):
                        await pipe.unwatch()
                        return True
                    if active >= limit:
                        await pipe.unwatch()
                        return False
                    peak = int(await pipe.get(peak_key) or 0)
                    pipe.multi()
                    pipe.hset(key, call_id, expiry)
                    if active + 1 > peak:
                        pipe.set(peak_key, active + 1)
                    await pipe.execute()
                    return True
                except WatchError:
                    continue
        return False

    async def renew_slot(self, run_id: str, call_id: str, lease_s: int = 300) -> None:
        await self.r.hset(self._slots(run_id), call_id, int((time.time() + lease_s) * 1000))

    async def release_slot(self, run_id: str, call_id: str) -> None:
        await self.r.hdel(self._slots(run_id), call_id)

    async def active(self, run_id: str) -> int:
        return int(await self.r.hlen(self._slots(run_id)))

    async def peak(self, run_id: str) -> int:
        return int(await self.r.get(f"run:{run_id}:peak") or 0)

    async def expired_slots(self, run_id: str) -> list[str]:
        now = int(time.time() * 1000)
        slots = await self.r.hgetall(self._slots(run_id))
        return [cid for cid, exp in slots.items() if int(exp) < now]

    # -- abort, spend, conditions --------------------------------------------------------------------
    async def set_abort(self, run_id: str) -> None:
        await self.r.set(f"run:{run_id}:abort", "1", ex=86_400)

    async def aborted(self, run_id: str) -> bool:
        return bool(await self.r.exists(f"run:{run_id}:abort"))

    async def add_spend(self, run_id: str, usd: float) -> float:
        return float(await self.r.incrbyfloat(f"run:{run_id}:spend", float(usd)))

    async def spend(self, run_id: str) -> float:
        return float(await self.r.get(f"run:{run_id}:spend") or 0.0)

    async def set_conditions(self, run_id: str, epoch: int, parameters: dict[str, Any]) -> None:
        await self.r.set(f"run:{run_id}:conditions", json.dumps({"epoch": epoch, "parameters": parameters}), ex=86_400)

    async def get_conditions(self, run_id: str) -> tuple[int, dict[str, Any]] | None:
        raw = await self.r.get(f"run:{run_id}:conditions")
        if not raw:
            return None
        d = json.loads(raw)
        return int(d["epoch"]), d["parameters"]

    # -- live events (EVT-01..13) ---------------------------------------------------------------------
    def _events(self, run_id: str) -> str:
        return f"run:{run_id}:events"

    async def publish(self, run_id: str, kind: str, payload: dict[str, Any]) -> str:
        seq = await self.r.incr(f"run:{run_id}:seq")
        payload = {**payload, "ts": int(time.time() * 1000)}  # wall ms, for display and labelled replay only
        return await self.r.xadd(self._events(run_id), {"kind": kind, "seq": str(seq),
                                                        "payload": json.dumps(payload, default=str)},
                                 maxlen=20_000, approximate=True)

    async def read_events(self, run_id: str, last_id: str, block_ms: int = 15_000,
                          count: int = 200) -> list[tuple[str, str, int, dict[str, Any]]]:
        key = {self._events(run_id): last_id or "0"}
        if self.in_process:
            res = await self._poll(lambda: self.r.xread(key, count=count), block_ms)
        else:
            res = await self.r.xread(key, count=count, block=block_ms)
        out = []
        for _, entries in res or []:
            for eid, f in entries:
                out.append((eid, f["kind"], int(f.get("seq", 0)), json.loads(f.get("payload") or "{}")))
        return out

    async def retain_events(self, run_id: str, seconds: int = 3600) -> None:
        for k in (self._events(run_id), f"run:{run_id}:seq"):
            await self.r.expire(k, seconds)

    # -- rate limiting (ARC-050): fixed-window counters ----------------------------------------------
    async def hit(self, key: str, limit: int, window_s: int) -> tuple[bool, int, int]:
        bucket = int(time.time() // window_s)
        k = f"rl:{key}:{bucket}"
        n = await self.r.incr(k)
        if n == 1:
            await self.r.expire(k, window_s + 1)
        reset = (bucket + 1) * window_s
        return n <= limit, max(0, limit - n), reset

    # -- idempotency ---------------------------------------------------------------------------------
    async def remember(self, key: str, value: str, ttl_s: int = 86_400) -> str | None:
        """SET NX: returns the existing value if the key was already set, else None."""
        ok = await self.r.set(key, value, nx=True, ex=ttl_s)
        return None if ok else await self.r.get(key)
