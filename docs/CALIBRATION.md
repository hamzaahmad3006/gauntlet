# Calibration

A measurement product that cannot demonstrate its own accuracy has produced opinions. The calibration
harness bounds GAUNTLET's own measurement error (SRS-FR-067, deviations D-06 and D-19).

## Method

1. Caller and calibration target run on **one host sharing one clock** (`perf_counter_ns`), so ground
   truth is exact. By default the target runs in-process on a loopback WebSocket.
2. The caller sends a 1 kHz, 300 ms tone through the ordinary media path (transmitter → chaos pipeline
   with the clean profile → WebSocket PCM adapter).
3. The target detects the tone's last sample at sample resolution, waits the programmed delay `D` on
   the shared clock, and emits a response tone. It reports, as a `marker` message, the instant the
   response's first sample left.
4. The caller measures the response onset through the **ordinary probe path** — playout clock, adaptive
   energy detector, sub-frame interpolation — the same code that measures every real call.
5. `error = probe onset − reported emit instant`. The nominal `D` is reported alongside
   (`nominal_error_ms`), and the target's own scheduling overshoot is reported separately.
6. Sweep: delays 200, 500, 1000, 2000 ms × 20 repetitions (the runner refuses fewer).

```bash
python calibration/run_calibration.py        # writes calibration/results.csv and summary.json
```

The runner exits **5** if the bound exceeds `CALIBRATION_MAX_ACCEPTABLE_MS` (50, THRESHOLD), and CI runs
it on every push.

## Result

Committed in `calibration/results.csv` (80 raw rows) and `calibration/summary.json`:

| | Value |
|---|---|
| Error bound (max \|error\|) | **3.897 ms** — MEASURED |
| Repetitions | 80 (4 delays × 20) |
| Mean error per delay | 2.26 – 2.58 ms |
| Environment | Windows 11, Python 3.12.10, AMD64 |
| Commit | `61ef2ea` |

Diagnosis of the ~2.3 ms mean: roughly 0–2 ms is the playout clock absorbing the target's pacing jitter
and about 1 ms is in-process transport latency. Both are genuine pipeline error and are counted.

## What the bound covers — and does not

It bounds **probe and local pipeline error on a loopback path**. It does **not** bound wide-area network
variance, provider variance, or a target's internal jitter. Every place the number appears says so.
