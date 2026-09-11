"""Rig performance benchmark (SRS 33, task T-060): what concurrency can GAUNTLET itself sustain?

The subject is the rig, not an agent. N calls run simultaneously in one process against the synthetic
agent fixture, which reports the exact instant each response's first sample left (marker messages on
the shared clock). For every turn, measurement error = probe onset − reported emit instant. A rig that
is saturated shows it as growing error, late frames or dropped frames — not as a slower "agent".

Saturation (SRS 33.4) is the lowest level where any holds: p95 |error| exceeds the level-1 value by more
than 50 ms; the transmitter falls more than 40 ms behind its 20 ms schedule; any receive overflow.
The concurrency figure quoted anywhere is the highest level *below* saturation from the newest
committed file — never the configured maximum.

    python benchmarks/run_rig_benchmark.py [--levels 1,2,4,8,12,16] [--turns 4]
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import csv
import json
import platform
import socket
import statistics
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from fixtures.calibration_target.server import serve  # noqa: E402
from gauntlet.caller.adapters.websocket_pcm import WebSocketPCMTransport  # noqa: E402
from gauntlet.caller.brain import CallerBrain  # noqa: E402
from gauntlet.caller.session import CallPlan, CallSession, SessionConfig  # noqa: E402
from gauntlet.caller.tts import SpeechSynth  # noqa: E402
from gauntlet.common import rt, seeds  # noqa: E402
from gauntlet.media.chaos import ChaosParams  # noqa: E402
from gauntlet.suites.loader import bundled_suite  # noqa: E402

QUERY = "mode=agent&endpoint_ms=450&delay_ms=250&yield_ms=220"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def p95(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return s[max(0, -(-95 * len(s) // 100) - 1)]


async def one_call(url: str, i: int, turns: int, synth: SpeechSynth) -> dict:
    suite = bundled_suite()
    sc = dict(suite.scenario("book_table_basic"))
    sc["timing"] = {"max_turns": turns, "max_duration_s": 90, "turn_timeout_ms": 6000}
    persona = suite.persona("calm_standard")
    transport = WebSocketPCMTransport(url)
    plan = CallPlan(f"bench-{i}", seeds.call_seed(1, "book_table_basic", "calm_standard", i), sc, persona, ChaosParams())
    session = CallSession(plan, transport, synth, CallerBrain(), config=SessionConfig(greeting_wait_ms=800, record_audio=False))
    out = await session.run()
    markers = []
    while not transport.markers.empty():
        m = transport.markers.get_nowait()
        if m.get("kind") == "response_start":
            markers.append(int(m["t_ns"]))
    errors = []
    for t in out.turns:
        if t.t_agent_first_audio_ns is None:
            continue
        near = [m for m in markers if abs(t.t_agent_first_audio_ns - m) < 150_000_000]
        if near:
            m = min(near, key=lambda x: abs(t.t_agent_first_audio_ns - x))
            errors.append((t.t_agent_first_audio_ns - m) / 1e6)
    tx = session.media.tx
    return {"ended": out.ended, "reason": out.reason_code, "errors": errors,
            "lateness_ms": tx.lateness_max_ms if tx else None, "rx_overflow": transport.stats.get("rx_overflow", 0),
            "latencies": [t.latency_ms for t in out.turns if t.latency_ms is not None]}


async def level(url: str, n: int, turns: int, synth: SpeechSynth) -> dict:
    res = await asyncio.gather(*(one_call(url, i, turns, synth) for i in range(n)))
    errs = [abs(e) for r in res for e in r["errors"]]
    return {
        "level": n, "calls": n, "completed": sum(1 for r in res if r["ended"] == "conversation"),
        "turns_measured": len(errs), "error_p50_ms": round(statistics.median(errs), 3) if errs else None,
        "error_p95_ms": round(p95(errs), 3) if errs else None, "error_max_ms": round(max(errs), 3) if errs else None,
        "tx_lateness_max_ms": round(max(r["lateness_ms"] or 0 for r in res), 3),
        "rx_overflow": sum(r["rx_overflow"] for r in res),
        "latency_p50_ms": round(statistics.median([x for r in res for x in r["latencies"]]), 3) if any(r["latencies"] for r in res) else None,
    }


async def main(levels: list[int], turns: int) -> list[dict]:
    port = free_port()
    server = await serve("127.0.0.1", port)
    synth = SpeechSynth(cache_dir=Path(tempfile.mkdtemp()))
    try:
        # warm the synthesis cache so the benchmark measures the media path, not babble generation
        await one_call(f"ws://127.0.0.1:{port}/?{QUERY}", 0, turns, synth)
        rows = []
        for n in levels:
            r = await level(f"ws://127.0.0.1:{port}/?{QUERY}", n, turns, synth)
            rows.append(r)
            print(f"  level {n:>3}: {r['completed']}/{n} completed, error p95 {r['error_p95_ms']} ms, "
                  f"max {r['error_max_ms']} ms, tx lateness {r['tx_lateness_max_ms']} ms, overflow {r['rx_overflow']}",
                  flush=True)
        return rows
    finally:
        server.close()
        with contextlib.suppress(Exception):
            await server.wait_closed()


def cli() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", default="1,2,4,8,12,16")
    ap.add_argument("--turns", type=int, default=4)
    args = ap.parse_args()
    levels = [int(x) for x in args.levels.split(",")]
    print(f"GAUNTLET rig benchmark — levels {levels}, one process, loopback synthetic agent")
    rows = rt.run(main(levels, args.turns))
    base = rows[0]["error_p95_ms"] or 0.0
    saturation = None
    for r in rows:
        if ((r["error_p95_ms"] or 0) - base > 50) or r["tx_lateness_max_ms"] > 40 or r["rx_overflow"] > 0 \
                or r["completed"] < r["calls"]:
            saturation = r["level"]
            break
    sustained = max((r["level"] for r in rows if saturation is None or r["level"] < saturation), default=None)
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        sha = "0" * 40
    env = f"{platform.system()} {platform.release()} / Python {platform.python_version()} / {platform.machine()} / " \
          f"{__import__('os').cpu_count()} logical CPUs"
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    out = ROOT / "benchmarks" / f"rig-{stamp}.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) + ["git_sha", "environment"])
        w.writeheader()
        for r in rows:
            w.writerow({**r, "git_sha": sha, "environment": env})
    summary = {"sustained_concurrency": sustained, "saturation_level": saturation, "levels": levels, "git_sha": sha,
               "environment": env, "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
               "rule": "saturation = first level where p95 |error| exceeds level-1 by > 50 ms, transmit lateness > 40 ms, "
                       "any receive overflow, or any call fails to complete",
               "scope": "one process on one machine against a loopback synthetic agent; the rig's own limit, not a target's"}
    (ROOT / "benchmarks" / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"sustained concurrency {sustained} (saturation at {saturation}); wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(cli())
