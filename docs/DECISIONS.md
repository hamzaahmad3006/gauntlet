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

**D-21 — schema is created idempotently at boot instead of by Alembic migrations.** The SRS names
Alembic. For a three-day build the schema is defined once in SQLAlchemy Core and `create_all` runs as
the release step (idempotent, forward-only by construction because nothing is ever dropped). Alembic
arrives with the first change to an existing table.

**D-22 — `Pages/Auth/` holds `Login/` and `Callback/` only.** Sign-in is GitHub OAuth, so there is no
password to register or reset; `Register/` and `ForgotPassword/` would be empty. `Callback/` receives the
OAuth redirect. The Callback hook is named `useAuthCallback` so it cannot shadow React's `useCallback`.

**D-23 — live call tiles show per-turn latency bars, not live waveforms.** Streaming audio to the browser
during a run would add a media path to the dashboard. Tiles show each turn's measured latency against the
threshold; the paired waveforms, overlap regions and audio are on the call detail page once a call ends.

**D-24 — shared formatting helpers live in `components/ui/format.ts`.** The folder convention has no
`lib/`; formatting is a presentation concern shared by every primitive, so it sits beside them rather
than in a new folder.

**D-25 — premature speech is an event, not a latency exclusion.** An agent that speaks into a caller's
pause is flagged and counted (premature speech rate), but the turn's response latency is still measured
to the agent's next onset after the caller finishes, unless the agent is still talking at that instant.

**D-26 — the example run is one click, not automatic.** New workspaces carry both bundled targets and the
suite, and the dashboard offers "Run suite" immediately. Auto-starting a run for every sign-in would spend
provider credit for every visitor.

**D-27 — the container runs as root on Render.** SRS 34.3 asks for a non-root user. Render mounts
persistent disks root-owned and the single-container deployment keeps SQLite on that disk, so the image
does not switch user. The unprivileged user exists for deployments with a volume it owns.

**D-28 — the hosted caller-inference bound is 800 ms, not 400 ms.** A 400 ms race against a hosted model
from a cloud region makes most turns fall back to scripted lines. The bound exists so the rig is never
the slow party; caller think time precedes the measured interval and is excluded from dead air (D-15), so
a longer bound does not contaminate any target metric. The fallback rate is still reported per run.

**D-29 — the deployment is one container with guest access.** The dashboard is served by the API from
its own origin, the worker runs in-process, and a shared rate-limited guest workspace (`ALLOW_GUEST`)
replaces GitHub OAuth for judging. PostgreSQL, Redis and OAuth remain configuration away.

**D-20 — submission moved to 13 September 2026.** The build plan is compressed to three days; the PRD 9.4
cut order applies unchanged.

**D-30 — the public deployment runs on Render's Free plan with free PostgreSQL.** The Free web plan has
no persistent disk, so run results move to a free Render PostgreSQL database (expires after 30 days, which
covers judging) and call audio lives on the ephemeral filesystem. Free instances get 0.1 CPU, so hosted
concurrency is capped at 2 calls; numbers from that deployment are not comparable with the committed
laptop benchmarks, and runs past the rig's capacity carry the rig-saturation flag. `plan: starter` restores
the higher limits.

**D-31 — Groq retired the Llama 3.x models; the caller and the reference agent use `qwen/qwen3.6-27b` and
the judge uses `openai/gpt-oss-120b`.** Every request to `llama-3.1-8b-instant` and
`llama-3.3-70b-versatile` now returns model_not_found. Stored targets and suites may still name them, so a
retired name resolves to its replacement (`common/llm.py`). Qwen runs with reasoning off (about 200 ms per
caller turn from Pakistan, measured 13 September); gpt-oss runs with low reasoning effort and never returns
its reasoning. The caller opens its provider connection before the first turn, because a cold TLS handshake
alone could exceed the 800 ms bound and push the opening line onto a scripted fallback.

**D-32 — the judge treats sound-alike values as confirmed (prompt `task-v2`).** The agent's words reach the
judge through speech recognition, so spelling carries no evidence: in the first live run the agent said
"Sara" and the transcript wrote "Sarah", and `task-v1` failed a correct booking. The rule accepts values
that sound the same and still rejects values that sound different; both directions were checked against
the live judge (Sandra and 9 p.m. still fail). ElevenLabs free plans cannot use library voices through
the API (HTTP 402); that response now counts as an unavailable voice, so the call substitutes the default
voice ("Laura") and records `voice_substituted` instead of dropping to the local synthesiser.

**D-33 — bundled targets are refreshed at startup, and local runs default to two concurrent calls.** A
workspace seeded by an earlier build kept its old fixture query, so its bundled agent ran in scripted mode
and spoke babble even with provider keys. At API startup, bundled targets whose stored connection differs
from the current definition are rewritten; user-created targets are never touched. The free Speechmatics
plan closes a third simultaneous real-time session with `quota_exceeded`, which leaves those calls without
a referee transcript and the caller hearing "silence", so the new-run default concurrency is 2 and the
local `.env` caps calls per worker at 2.
