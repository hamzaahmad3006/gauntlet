# GAUNTLET

**The infrastructure crash-test rig for real-time voice AI.**

GAUNTLET dials your voice agent with synthetic adversarial callers over real media transport, measures
latency, turn-taking, reliability and cost **from the caller's ear** under controlled, seeded adverse
conditions, and returns a deterministic production-readiness score that can fail a pull request.

It is a load generator and profiler for streaming inference — not a voice application. The audio
conversation is the workload; the artefacts are infrastructure artefacts: percentiles, a measured
concurrency ceiling, condition-by-condition degradation, cost per successful session, and a CI gate.

> **Evidence labels.** Every number in this repository is TARGET, THRESHOLD or MEASURED. A value is
> MEASURED only when the raw output of the run that produced it is committed (`calibration/`,
> `benchmarks/`). See [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## Why

A voice agent rarely fails by saying the wrong thing. It fails by taking 1.9 s to say the right thing, by
talking for 1.4 s after the caller interrupts, by leaving dead air, or by degrading at the twentieth
concurrent call. None of that is visible in an APM trace, a transcript evaluation, or an HTTP load test,
because the unit of latency is perceptual, the session is stateful, and the transport is continuous media.

## What makes it different

- **Acoustic and black-box.** One caller process owns both audio directions on one high-resolution clock,
  so no latency carries clock skew and no access to your agent's code or logs is needed.
- **Turn-taking is instrumented.** Barge-in stop time, yield rate, talk-over, dead air and premature
  speech are thresholded metrics, not impressions.
- **Seeded, reproducible chaos.** Frame loss, jitter, delay, noise, interruptions and caller hesitation
  come from per-stage seeded streams: same seed, byte-identical impairment and interruption schedules.
- **Arithmetic, not opinion.** The readiness score is a documented piecewise-linear function of measured
  values against a versioned threshold profile. No language model assigns it. Models are used in exactly
  two places — the caller's words and the task-success judgement (with verbatim citations, two passes).
- **It publishes its own error.** A calibration harness bounds the rig's measurement error.

## Measured so far

| What | Value | Evidence |
|---|---|---|
| Rig measurement error bound (loopback) | **3.897 ms** over 80 repetitions (200/500/1000/2000 ms × 20) | MEASURED — [`calibration/results.csv`](calibration/results.csv), [`summary.json`](calibration/summary.json) |
| Acceptable maximum for that bound | 50 ms | THRESHOLD — CI fails above it |
| Concurrent calls the rig sustains in one process | **8** (saturates at 12: transmit falls > 40 ms behind); timing error p95 7.1 ms at 8 calls | MEASURED — [`benchmarks/rig-2026-09-11.csv`](benchmarks/rig-2026-09-11.csv), [`summary.json`](benchmarks/summary.json) |
| Sustained concurrency aimed for | ≥ 10 | TARGET (PRD MET-22) — not yet met on this machine |

The bound covers probe and pipeline error on one host sharing one clock; it is not a wide-area network
bound ([`docs/CALIBRATION.md`](docs/CALIBRATION.md)). The concurrency figure comes from
[`benchmarks/run_rig_benchmark.py`](benchmarks/run_rig_benchmark.py) on an 8-thread Windows laptop, with the
synthetic agent sharing the rig's process — so it is conservative for an external target, and it is re-run
on any machine whose number is quoted. More workers scale it horizontally.

## Metrics

| Metric | Definition |
|---|---|
| Response latency p50/p95/p99 | caller's last voiced sample → agent's first audio, per turn, nearest rank |
| Time to first response | median across calls of the first caller turn's latency |
| Barge-in stop time p95 | interruption onset → agent speech offset; non-yields censored at 2000 ms, never dropped |
| Yield rate | interruptions the agent stopped for within 2000 ms |
| Talk-over | total simultaneous speech per call |
| Dead-air ratio | agent-side silences over 1.5 s ÷ conversation duration (caller think time excluded) |
| Completion / error rate | calls ending without / with a transport, protocol or rig fault |
| Task success | goal checklist met with verbatim turn citations, two-pass agreement |
| Degradation ratio | impaired-run p95 ÷ clean-run p95 on the same target and suite version |
| Cost per successful session | rig cost measured from provider counters; target cost estimated from declared prices — never summed |

Definitions, scoring weights, grades and hard-breach caps: [`docs/METRICS.md`](docs/METRICS.md).
Conditions and their parameters: [`docs/CONDITIONS.md`](docs/CONDITIONS.md).

## Architecture

A modular monolith with one worker role (FastAPI API + dashboard; workers holding media sessions),
PostgreSQL and Redis — or, for a single container, SQLite and an in-process queue.
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

```
backend/gauntlet/  server.py · routes/ · controllers/ · middleware/        the API
                   media/ metrics/ scoring/ cost/ suites/ caller/ referee/  the measurement engine
                   orchestrator/ worker/ db/ reports/ cli/ common/
frontend/src/      api/ · components/ui/ · Pages/{Frontend,Auth,Dashboard} · Routes.tsx
fixtures/          calibration target = synthetic agent = WebSocket reference server
suites/            6 scenarios · 4 personas · 4 condition profiles · default thresholds
calibration/       runner + committed results        benchmarks/  rig benchmark
.github/actions/gauntlet-gate/                        the CI gate for your repository
```

## Run it

**Local, no external services** (Python 3.12, Node 20+):

```bash
python -m venv .venv && .venv/bin/pip install -e "backend[dev]"      # Windows: .venv\Scripts\...
cd backend && ../.venv/bin/python -m gauntlet.serve                 # API + in-process worker on :8000
cd frontend && npm ci && npm run dev                                 # dashboard on :5173
```

Sign in as the local developer: the workspace comes with two bundled targets — two tunings of the
synthetic agent — so a run and a real two-configuration comparison work immediately. Without provider
keys the caller speaks scripted lines with a local synthesiser and task success is not scored (and the
dashboard says so).

**Docker:** `docker compose up --build` (PostgreSQL, Redis, API + dashboard on :8000, worker), or a single
container: `docker build -f infra/Dockerfile .` — see `render.yaml` and `infra/fly.toml`.

**Tests:** `cd backend && pytest` (unit, property, API, and real-time media tests over loopback);
`cd frontend && npm test`. **Calibration:** `python calibration/run_calibration.py`.

## Gate a pull request

```yaml
- uses: hamzaahmad3006/gauntlet/.github/actions/gauntlet-gate@main
  with:
    config: gauntlet.yaml
    api-key: ${{ secrets.GAUNTLET_API_KEY }}
```

The action runs the suite, compares against the target's baseline, posts (or updates) one pull-request
comment naming every breached metric with baseline, candidate and delta, and fails the check. CLI exit
codes: `0` pass, `2` genuine metric breach, `3` ungatable run, `4` infrastructure error — a pipeline can
tell a regression from an outage. `gauntlet run --wait`, `gauntlet gate`, `gauntlet report`,
`gauntlet calibrate`, `gauntlet ci`.

## Integration status

| Technology | Role | Status |
|---|---|---|
| WebSocket PCM (`gauntlet.pcm.v1`) | media adapter, calibration, bundled agent | **working** — exercised by every test and calibration run |
| WebRTC via LiveKit | media adapter | implemented; not yet verified against a LiveKit room |
| Speechmatics (real-time) | independent referee transcription | implemented; not yet verified against the service |
| Groq (OpenAI-compatible) | caller words, task-success evaluator | implemented; not yet verified against the service |
| ElevenLabs | caller voices (cached by content hash) | implemented; not yet verified against the service |
| espeak-ng / built-in babble | local fallback voice | working |
| PostgreSQL · Redis | datastore · queue, events, limits | implemented (docker compose); SQLite + in-process Redis verified |
| S3-compatible storage | call audio | implemented; local disk verified |
| GitHub Actions | CI gate | implemented |

A technology is called *working* only once its code path has executed against the real thing.
Speechmatics is used under publicly available developer access; no partnership is claimed. No hardware
acceleration is claimed.

## Limitations

Read [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) before trusting a number. In short: impairment is
application-layer and caller-outbound only; frame substitution approximates packet loss; the error bound
is a loopback bound; task success is model inference constrained by citations; noise beds are
synthesised; time-to-first-token is not observable in black-box mode.

Every departure from the specification is recorded in [`docs/DECISIONS.md`](docs/DECISIONS.md).

## License

MIT
