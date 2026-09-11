# Decisions

Dated records of every place the code deliberately differs from the SRS text, and why. SRS deviations
D-01 to D-07 are defined in the SRS itself; this file continues the numbering.

## 2026-09-11

**D-08 — measurement clock is `perf_counter_ns`, not `monotonic_ns`.** On Windows with Python 3.12,
`time.monotonic` is `GetTickCount64` with a 15.625 ms resolution — alone larger than half the
calibration budget. `time.perf_counter_ns` is QueryPerformanceCounter on Windows (100 ns) and
CLOCK_MONOTONIC on Linux, i.e. the clock the SRS intended, and it is system-wide on both, which the
same-host calibration (D-06) requires. For the same reason the real-time event loop on Windows keeps
time with `perf_counter` and raises the system timer resolution to 1 ms (`gauntlet/common/rt.py`).

**D-09 — per-call seeds use scenario/persona keys and are 63-bit.** Keys are covered by the suite hash,
so identical suites derive identical seeds across workspaces. Clearing the top bit lets every seed
round-trip through a PostgreSQL `bigint` unchanged; a seed that cannot be stored exactly cannot be reused
exactly.

**D-10 — repository layout follows the project folder convention.** The SRS §36 layout (`apps/`,
`packages/`) is replaced by `backend/gauntlet/` (server.py, routes/, controllers/, middleware/, and the
SRS-named packages media, metrics, scoring, cost, suites, caller, referee, common, worker, cli, db) and
`frontend/src/` (api/, components/ui/, Pages/, Routes.tsx). Component ids (ARC-nnn) are unchanged.

**D-11 — the dashboard is a Vite + React single-page app, not Next.js.** The folder convention is an SPA
shape (main.tsx → App.tsx → Routes.tsx). Reports that must render without JavaScript are rendered as
HTML by the backend (API-041, API-044), so nothing that needed server rendering is lost.

**D-12 — development mode needs no external service.** With `ENVIRONMENT=development` and empty
`DATABASE_URL`/`REDIS_URL`, the backend uses SQLite and an in-process queue, and runs the worker inside
the API process. Production uses PostgreSQL and Redis exactly as specified. The data layer uses
SQLAlchemy Core types that map to the SRS's PostgreSQL types.

**D-13 — noise beds are synthesised, not recorded.** `cafe` and `street` are generated deterministically
from fixed seeds (shaped noise, modulated babble bands, transients, traffic swells). They are
distinguishable engineered conditions, not reproductions of real places; the repository carries no binary
audio and every run mixes bit-identical noise.

**D-14 — a missing scoring input redistributes within its sub-score.** SRS 19.6 marks a whole sub-score
unavailable when any input is missing. That makes every clean-profile run (no interruptions, therefore no
barge-in value) lose turn-taking entirely. Instead a missing input's intra-weight is redistributed across
the sub-score's remaining inputs, the run is flagged `partial_scoring`, and the missing metric is named. A
sub-score with no inputs at all is still unavailable, and two unavailable sub-scores still suppress the
grade.

**D-15 — dead air counts agent-side silence only.** The SRS counts every gap over 1.5 s. The caller's own
think time (transcript finalisation, inference, synthesis) would then be reported as the target's dead
air. Dead air is therefore measured inside agent windows — from the caller's last word to the caller's next
utterance — as the wait for a response plus pauses within the response.

**D-16 — received audio is timed on a playout clock.** A speech frame cannot be heard before the previous
one finished, so a target that bursts audio faster than real time is measured as heard, not as delivered.
Silent frames compress 2x so accumulated lag drains between utterances.

**D-17 — jitter `max_ms` may not exceed `depth × 20 ms`.** Reorder-buffer overflow is therefore
impossible by construction instead of counted after the fact.

**D-18 — time to first response is scored at its median across calls.** MET-04's threshold (1200 ms)
sits between the p50 (800 ms) and p95 (1500 ms) thresholds of general latency, consistent with a
per-run median of first-turn latencies.

**D-19 — calibration error is measured against the target's exact emit time.** The calibration target
reports, on the shared clock, the instant its response tone's first sample was sent. Error = probe-measured
onset − that instant, which isolates probe and pipeline error from the target's own scheduling. The
nominal programmed delay is reported alongside.

**D-20 — submission moved to 13 September 2026.** The build plan is compressed to three days; the PRD 9.4
cut order applies unchanged.
