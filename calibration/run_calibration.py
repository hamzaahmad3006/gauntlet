"""ARC-070 calibration runner (SRS-FR-067, deviations D-06 and D-19).

Caller and calibration target run on one host and share one clock. For each programmed delay the caller
sends a 1 kHz tone through the ordinary media path; the target detects the tone's end at sample
resolution, waits the programmed delay and emits a response tone, reporting the instant its first
sample was sent. The caller measures the response with the *ordinary probe path* (playout clock + VAD +
sub-frame interpolation) — the same code that measures every real call.

    error_ms = measured_ms - actual_ms
    actual_ms   = target's reported emit instant - caller's last transmitted tone sample
    measured_ms = probe onset                    - caller's last transmitted tone sample

The published bound is max |error_ms| — a loopback probe-and-pipeline bound, never a wide-area claim.
Exit codes: 0 pass, 5 bound above CALIBRATION_MAX_ACCEPTABLE_MS, 1 usage error.

    python calibration/run_calibration.py [--delays 200,500,1000,2000] [--repetitions 20]
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import csv
import json
import os
import platform
import socket
import statistics
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from fixtures.calibration_target.server import serve  # noqa: E402
from gauntlet.caller.adapters.websocket_pcm import WebSocketPCMTransport  # noqa: E402
from gauntlet.caller.media_session import MediaSession  # noqa: E402
from gauntlet.caller.transmit import Utterance  # noqa: E402
from gauntlet.common import rt  # noqa: E402
from gauntlet.media.audio import tone  # noqa: E402
from gauntlet.media.chaos import ChaosParams  # noqa: E402

MIN_REPETITIONS = 20
TONE_MS = 300
RESPONSE_MS = 300


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              timeout=5, check=True).stdout.strip()
    except Exception:
        return "0" * 40


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def next_marker(transport: WebSocketPCMTransport, kind: str, after_ns: int, timeout: float) -> dict | None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while (remaining := deadline - loop.time()) > 0:
        try:
            m = await asyncio.wait_for(transport.markers.get(), remaining)
        except asyncio.TimeoutError:
            return None
        if m.get("kind") == kind and m.get("t_ns", 0) >= after_ns:
            return m
    return None


async def sweep_level(url: str, delay_ms: int, reps: int, profile: ChaosParams, seed: int) -> list[dict]:
    transport = WebSocketPCMTransport(f"{url}/?mode=calibration&delay_ms={delay_ms}&response_ms={RESPONSE_MS}")
    media = MediaSession(transport, profile, seed, record=False)
    await media.start()
    assert media.tx is not None and media.rx is not None
    rows = []
    try:
        await asyncio.sleep(0.6)  # let the probe establish its floor on the target's silence
        for rep in range(reps):
            utt = media.tx.say(Utterance.from_pcm(tone(1000, TONE_MS, -12), text="tone", kind="tone"))
            if not await utt.wait(5):
                raise RuntimeError("tone utterance was never fully transmitted")
            t_last = utt.last_voiced_ns
            assert t_last is not None
            onset = await media.rx.wait_onset(t_last, timeout_s=delay_ms / 1000 + 2.0)
            marker = await next_marker(transport, "response_start", t_last, timeout=2.0)
            if onset is None or marker is None:
                raise RuntimeError(f"no response detected at delay {delay_ms} ms, repetition {rep}")
            measured = (onset.t_ns - t_last) / 1e6
            actual = (int(marker["t_ns"]) - t_last) / 1e6
            rows.append({"injected_ms": delay_ms, "actual_ms": round(actual, 3), "measured_ms": round(measured, 3),
                         "error_ms": round(measured - actual, 3), "nominal_error_ms": round(measured - delay_ms, 3),
                         "repetition": rep})
            await media.rx.wait_offset(onset.t_ns, timeout_s=RESPONSE_MS / 1000 + 1.0)
            await asyncio.sleep(0.25)
    finally:
        await media.stop()
    return rows


async def run(delays: list[int], reps: int, url: str | None, profile_key: str) -> list[dict]:
    server = None
    if url is None:
        port = free_port()
        server = await serve("127.0.0.1", port)
        url = f"ws://127.0.0.1:{port}"
    profile = ChaosParams()  # clean path: calibration bounds the probe, not an impairment
    try:
        rows: list[dict] = []
        for i, d in enumerate(delays):
            print(f"  delay {d:>5} ms x {reps} ...", end="", flush=True)
            level = await sweep_level(url, d, reps, profile, seed=1000 + i)
            rows += level
            errs = [abs(r["error_ms"]) for r in level]
            print(f" max |error| {max(errs):.3f} ms, median {statistics.median(errs):.3f} ms", flush=True)
        for r in rows:
            r["condition_profile"] = profile_key
        return rows
    finally:
        if server is not None:
            server.close()
            with contextlib.suppress(Exception):
                await server.wait_closed()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--delays", default="200,500,1000,2000")
    ap.add_argument("--repetitions", type=int, default=MIN_REPETITIONS)
    ap.add_argument("--url", default=None, help="external calibration target (default: start one in-process)")
    ap.add_argument("--out", default=str(ROOT / "calibration" / "results.csv"))
    ap.add_argument("--max-ms", type=float, default=float(os.environ.get("CALIBRATION_MAX_ACCEPTABLE_MS", "50")))
    args = ap.parse_args()
    delays = [int(x) for x in args.delays.split(",") if x.strip()]
    if args.repetitions < MIN_REPETITIONS or len(delays) < 4:
        print(f"refused: need at least 4 delay values and {MIN_REPETITIONS} repetitions each", file=sys.stderr)
        return 1

    print(f"GAUNTLET calibration — {len(delays)} delays x {args.repetitions} repetitions, loopback")
    rows = rt.run(run(delays, args.repetitions, args.url, "clean"))
    sha, run_at = git_sha(), datetime.now(UTC).isoformat(timespec="seconds")
    env = f"{platform.system()} {platform.release()} / Python {platform.python_version()} / {platform.machine()}"
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["injected_ms", "actual_ms", "measured_ms", "error_ms", "nominal_error_ms", "repetition",
            "condition_profile", "git_sha", "run_at", "environment"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({**r, "git_sha": sha, "run_at": run_at, "environment": env})

    errors = [abs(r["error_ms"]) for r in rows]
    bound = max(errors)
    per_level = {}
    for d in delays:
        e = [r["error_ms"] for r in rows if r["injected_ms"] == d]
        a = [r["actual_ms"] - d for r in rows if r["injected_ms"] == d]
        per_level[str(d)] = {"n": len(e), "max_abs_error_ms": round(max(abs(x) for x in e), 3),
                             "mean_error_ms": round(statistics.fmean(e), 3),
                             "stdev_error_ms": round(statistics.pstdev(e), 3),
                             "mean_target_overshoot_ms": round(statistics.fmean(a), 3)}
    summary = {
        "bound_ms": round(bound, 3),
        "acceptable_max_ms": args.max_ms,
        "passed": bound <= args.max_ms,
        "n": len(rows),
        "delays_ms": delays,
        "repetitions": args.repetitions,
        "method": "loopback, caller and calibration target on one host sharing perf_counter; error = probe onset - "
                  "target-reported emit instant (D-06, D-19)",
        "scope": "probe-and-pipeline bound on a loopback path; not a wide-area network bound",
        "per_level": per_level,
        "git_sha": sha,
        "run_at": run_at,
        "environment": env,
    }
    (out.parent / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    verdict = "PASS" if summary["passed"] else "FAIL"
    print(f"bound {bound:.3f} ms (acceptable max {args.max_ms:g} ms) -> {verdict}; wrote {out}")
    return 0 if summary["passed"] else 5


if __name__ == "__main__":
    sys.exit(main())
