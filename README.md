# GAUNTLET

**The infrastructure crash-test rig for real-time voice AI.**

GAUNTLET dials your voice agent with fleets of synthetic adversarial callers over real media transport,
measures latency, turn-taking, reliability and cost **from the caller's ear** under controlled, seeded
adverse conditions, and returns a deterministic production-readiness score that can gate a pull request.

> Status: under active construction for the lablab.ai × AI Infra Summit hackathon (September 2026).
> Every number in this repository is labelled TARGET, THRESHOLD or MEASURED. A value is MEASURED only when
> the raw output of the run that produced it is committed under `calibration/` or `benchmarks/`.
> **No MEASURED value exists yet in this README.**

## Why

A voice agent rarely fails by saying the wrong thing. It fails by taking 1.9 s to say the right thing, by
talking for 1.4 s after the caller interrupts, by leaving dead air, or by degrading at the twentieth
concurrent call. None of that shows up in an APM trace, a transcript evaluation, or an HTTP load test.

## What it measures

| Metric | Definition |
|---|---|
| Response latency p50/p95/p99 | caller's last voiced sample → agent's first audio, per turn, nearest-rank |
| Time to first response | response latency of the first caller turn |
| Barge-in stop time p95 | caller interruption onset → agent speech offset; non-yields censored at 2000 ms |
| Yield rate | interruptions where the agent stopped within 2000 ms |
| Talk-over | total simultaneous speech per call |
| Dead-air ratio | agent-side silences longer than 1.5 s ÷ conversation duration |
| Completion / error rate | calls ending without / with a transport, protocol or rig fault |
| Task success | goal checklist satisfied with verbatim turn citations, two-pass agreement |
| Cost per successful session | rig cost (measured) and target cost (estimated) — never summed |

Full definitions: [`docs/METRICS.md`](docs/METRICS.md).

## How it works

- **Black-box and acoustic.** One caller process owns both audio directions on one high-resolution clock,
  so every latency is clock-skew-free. No access to the agent's code or logs is needed.
- **Deterministic, seeded conditions.** Frame loss (Gilbert model), jitter, added delay and noise are
  applied to the caller's outbound audio from per-stage seeded streams; two runs with the same seed apply
  identical impairment schedules and identical interruption offsets.
- **Arithmetic, not opinion.** The readiness score is a documented piecewise-linear function of measured
  values against a versioned threshold profile. No language model assigns it.
- **Self-calibrated.** A programmable-delay calibration target bounds the rig's own measurement error on a
  loopback path, and CI fails if the bound exceeds 50 ms (THRESHOLD).

## Repository layout

```
backend/     Python 3.12 — FastAPI server (routes/controllers/middleware) + the measurement engine
  gauntlet/  media/ metrics/ scoring/ cost/ suites/ caller/ referee/ common/ worker/ cli/ db/
  tests/
frontend/    Vite + React dashboard
fixtures/    calibration target / synthetic agent, reference agent
suites/      bundled scenarios, personas, condition and threshold profiles
calibration/ calibration runner and committed results
config/      rig pricing inputs
docs/        methodology, metrics, calibration, conditions, adapters, cost model, limitations, decisions
```

## Quick start (development, no external services)

```bash
python -m venv .venv && .venv/bin/pip install -e "backend[dev]"   # Windows: .venv\Scripts\...
cd backend && ../.venv/bin/python -m pytest -q
```

## Limitations

Read [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) before trusting any number. In short: impairment is
application-layer and caller-outbound only; frame substitution approximates packet loss; the calibration
bound is a loopback bound; task success is model inference constrained by citations.

## License

MIT
