# Traceability — PRD/SRS P0 requirements against the build

Every P0 requirement from PRD §9.1, its implementation, the test that proves it, and an honest status.
Status values:

- **Done** — implemented and covered by an automated test or a committed artefact.
- **Done · manual** — implemented and verified by hand (commands recorded), no automated test yet.
- **Implemented · unverified** — code path exists but has not yet run against the real external service.
- **Partial** — part of the requirement is missing; the gap is stated.
- **Pending** — not done yet.

Test ids refer to SRS §32. Deviations (D-nn) are explained in [`DECISIONS.md`](DECISIONS.md).

## Identity, targets, suites

| PRD | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| FR-001 | GitHub sign-in, workspace on first sign-in | `middleware/auth.py`, `db/repo.py ensure_user`, `db/seed.py` | TC-001 (guest/dev path) | Implemented · unverified (Supabase OAuth not yet configured); guest mode Done (D-29) |
| FR-002 | Workspace isolation, cross-tenant 404 | `db/repo.py` | TC-002 | Done |
| FR-003 | Scoped, hashed API keys | `controllers/keys_controller.py`, `common/crypto.py` | TC-003 | Done |
| FR-010 | Register a target, adapter immutable | `controllers/targets_controller.py` | TC-010 | Done |
| FR-011 | LiveKit room adapter | `caller/adapters/livekit.py` | import check only | Implemented · unverified |
| FR-012 | WebSocket PCM adapter + protocol doc | `caller/adapters/websocket_pcm.py`, `docs/ADAPTERS.md` | TC-012, every calibration run | Done |
| FR-013 | Ownership verification | nonce echo in `targets_controller.verify` | TC-013 | Done |
| FR-014 | Single-call diagnostic, four statuses | `targets_controller.diagnose`, fixture `mode=silent` | TC-012, TC-014 | Done |
| FR-015 | Pipeline and unit-price declaration | `schemas`, `cost/calculator.py` | TC-081 | Done |
| FR-020 | Scenario YAML schema with line numbers | `suites/loader.py`, `suites/schema/` | TC-020 | Done |
| FR-021 | Bundled suite, 6 scenarios × 4 tags | `suites/booking-core.yaml` | TC-021 | Done |
| FR-022 | Personas with measurable effect | `suites/personas.yaml` | TC-022 | Done |
| FR-023 | Content-hashed immutable suites | `suites/loader.py suite_hash` | TC-023, TC-093 | Done |

## Demo surfaces (beyond the SRS)

| Feature | Implementation | Evidence | Status |
|---|---|---|---|
| Browser softphone (*Talk to agent*) | `frontend/src/Pages/Dashboard/TalkToAgent/`, fixture transcript markers | driven in a real browser with a fake microphone; greeting and reply verified | Done (D-34) |
| One-click 1-call demo | `Pages/Dashboard/NewRun/useNewRun.ts` | driven in a real browser | Done |
| Live conversation in the run view | `Pages/Dashboard/LiveRun/Conversation.tsx`, `transcript.line` events | TC-037 event stream; browser run | Done |
| Agent output stays sample-contiguous under pacing jitter | `fixtures/calibration_target/session.py` | `tests/unit/test_fixture_render.py` (fails on the old code) | Done (D-33) |
| Reference agent greets through room noise | `fixtures/calibration_target/session.py` | `tests/unit/test_fixture_render.py` | Done |

## Runs and the synthetic caller

| PRD | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| FR-030 | Create a run with seed | `controllers/runs_controller.create` | TC-030 | Done |
| FR-031 | Pre-run estimate | `runs_controller.estimate` | API test (no side effects) | Done |
| FR-032 | Concurrency control, peak measured | `orchestrator/broker.py acquire_slot` | `benchmarks/rig-2026-09-11.csv`: 8 sustained (MEASURED) | Done (PRD aim of 10 not met on this machine) |
| FR-034 | Deterministic seeding | `common/seeds.py` | TC-034, TC-043 | Done |
| FR-035 | Spend ceiling enforcement | `worker/executor.py budget_ok`, `orchestrator/lifecycle.py` | TC-035 (`tests/api/test_spend_ceiling.py`) | Done |
| FR-036 | Abort within 10 s | `runs_controller.abort`, poller | TC-036 | Done |
| FR-037 | Live streaming, lossless resume | `runs_controller._sse`, `api/client.ts stream` | TC-037 | Done (server-side coalescing of `metric.updated` not implemented — event rates are low) |
| FR-038 | Mid-run condition injection with epochs | `runs_controller.inject_conditions`, `transmit.apply_params_at_next_utterance` | TC-038, browser session | Done |
| FR-039 | Run history with filters | `runs_controller.list_runs` | TC-039 | Done |
| FR-040 | LLM-driven goal-directed caller | `caller/brain.py`, `caller/session.py` | scripted path in media tests; live call `benchmarks/providers-2026-09-13/` (0 % fallback) | Done |
| FR-041 | Caller latency bound with fallback | `brain.next_utterance` | TC-041 | Done (bound 800 ms hosted, D-28) |
| FR-042 | Utterance cache | `caller/tts.py` | TC-042 | Done |
| FR-043 | Deterministic interruption | `caller/interrupts.py`, `transmit` sample-accurate start | TC-043, barge-in media test | Done |
| FR-044 | Hesitation, correction, silence, repetition | `caller/policies.py` | TC-044, premature-speech detection in runs | Done |

## Conditions and measurement

| PRD | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| FR-050 | Condition profile format and limits | `media/chaos.py ChaosParams` | TC-050 | Done |
| FR-051 | Frame loss (Gilbert, substitution) | `ChaosPipeline._draw_loss/_conceal` | TC-051 | Done (approximation, D-05) |
| FR-052 | Jitter | `ChaosPipeline._draw_jitter_ms` | TC-052 | Done |
| FR-053 | Noise at target SNR | `media/noise.py`, `ChaosPipeline` | TC-053 | Done (synthesised beds, D-13) |
| FR-054 | Added delay, subtracted from attributed latency | release time; `raw_latency_ms` | TC-054 (unit and real-time) | Done |
| FR-055 | Speech-rate variation | `caller/tts.py`, `media/audio.time_stretch` | TC-055 | Done |
| FR-056 | Impairment disclosure in three places | `metrics/disclosures.py` | TC-056 | Done |
| FR-060 | Acoustic probe, sub-frame timing | `media/probe.py` | TC-060 | Done |
| FR-061 | Response latency percentiles | `metrics/compute.py`, `aggregate.py` | TC-061 | Done |
| FR-062 | Barge-in stop time, censored no-yield | `compute.classify_interruption` | TC-062 (unit and real-time) | Done |
| FR-063 | Talk-over | `compute.intersection_ns` | TC-063 | Done |
| FR-064 | Dead-air ratio | `compute.dead_air` | TC-064 | Done (agent-side only, D-15) |
| FR-065 | One terminal status and reason per call | DB check constraints, executor, sweeper | TC-065 (`tests/api/test_worker_loss.py`), lifecycle tests | Done |
| FR-066 | Rig overhead separated | `TurnRecord.rig_overhead_ms` | TC-066 | Done |
| FR-067 | Calibration harness and bound | `calibration/run_calibration.py` | `calibration/results.csv`: 3.897 ms (MEASURED); CI gate | Done |

## Referee, cost, scoring, gate, reports

| PRD | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| FR-070 | Independent referee transcription | `referee/transcribe.py` (Speechmatics RT) | live call `benchmarks/providers-2026-09-13/` | Done |
| FR-071 | Independence disclosure and warning | `referee/transcribe.independence`, report, run summary | TC-071 | Done |
| FR-072 | Task success with turn citations | `referee/evaluate.py` | 15 tests with a stubbed provider (TC-072); live verdict `benchmarks/providers-2026-09-13/` | Done |
| FR-073 | Two-pass agreement, needs-review | `Evaluator.evaluate` | TC-073 | Done |
| FR-080 | Rig cost from counters | `cost/calculator.rig_cost` | TC-080 | Done |
| FR-081 | Estimated target cost | `estimate_target_cost` | TC-081 | Done |
| FR-082 | Cost per successful session | `metrics/aggregate.py` | TC-082 | Done |
| FR-090 | Threshold profiles | `scoring/profile.py`, `suites/thresholds-default.yaml` | TC-090 | Done (`strict` deferred, D-07) |
| FR-091 | Deterministic readiness score | `scoring/score.py` | TC-091 (property test) | Done |
| FR-092 | Hard-breach caps, missing data | `score.score` | TC-092 | Done (D-14) |
| FR-093 | Run comparison, blocked on mismatch | `scoring/compare.py` | TC-093 | Done |
| FR-094 | Recommendation with rule id | `compare.recommend` | TC-094 | Done |
| FR-095 | Baseline promotion | `targets_controller.promote_baseline` | TC-095 | Done |
| FR-096 | Gate evaluation with Markdown | `scoring/gate.py` | TC-096; full local runs: tuned A (100) vs slow C (76.2) failed on 4 breaches | Done |
| FR-097 | GitHub Action fails a real PR | `.github/actions/gauntlet-gate/action.yml` | gate verdict committed in `benchmarks/runs-2026-09-11/gate-slow-vs-tuned.md` | Partial: the gate fails on real measured breaches; no demo pull request has run it, which needs a hosted rig |
| FR-098 | CLI with distinct exit codes | `cli/main.py` | TC-098 (`tests/unit/test_cli_exit_codes.py`): every code 0–5 through its own path | Done |
| FR-110 | Report with evidence labels and limitations | `reports/render.py` | TC-110 | Done |
| FR-111 | Revocable share link, no workspace ids | `reports_controller.share` | TC-111 (found and fixed an unreachable JSON route) | Done |
| FR-112 | Markdown export | `render.to_markdown` | TC-112 | Done |

## Non-functional

| PRD | Requirement | Status |
|---|---|---|
| NFR-001 | Secrets never in source control | Done (`.gitignore`, `.env.example` names only) |
| NFR-002 | Target credentials write-only | Done (AES-256-GCM, no response field) |
| NFR-003 | Hashed API keys | Done (TC-003) |
| NFR-004 | TLS everywhere | Platform-provided at deployment |
| NFR-005 | Workspace isolation | Done (TC-002) |
| NFR-006/007 | Audio and transcript retention | Done (sweeper, 7-day default) |
| NFR-008 | Log hygiene | Done (TC-121) |
| NFR-009 | SSRF protection | Done (TC-120) |
| NFR-010 | Public availability | Partial: the project page is public (GitHub Pages); the rig itself is not hosted — every free container host now requires a payment method |
| NFR-011 | Abuse prevention | Done (verification, ceilings) |
| NFR-012 | Rate limiting | Done (fixed-window counters) |
| NFR-013 | Synthetic-only data | Done |
| NFR-014 | Share-link safety | Done (TC-111) |
| NFR-015 | Dependency hygiene (P1) | Partial: lock file for the dashboard; Python pins are lower bounds |
| SRS §30 | Operational metrics | Done (`/metrics`) |

## Product-level definition of done (PRD §26.2)

| # | Item | Status |
|---|---|---|
| 1 | All P0 requirements implemented and deployed | Implemented as above; deployed locally and reproducible from `infra/Dockerfile`, not hosted |
| 2 | Public URL loads from a clean browser | Done — <https://hamzaahmad3006.github.io/gauntlet/> (project page; the dashboard runs locally) |
| 3 | Full run at concurrency ≥ 10 producing a grade | Graded full runs done at the measured concurrency; 10 not sustained on this machine |
| 4 | A run against a target not written by the developer | Pending (needs a third-party agent endpoint) |
| 5 | `calibration/results.csv` committed and shown in the product | Done |
| 6 | A real pull request with a failing check | Pending |
| 7 | Comparison of two real configurations with rule | Done locally |
| 8 | README with architecture, metrics, calibration, integrations, limitations | Done |
| 9 | `docs/LIMITATIONS.md` complete | Done |
| 10–12 | Video, deck, submission | Done — video recorded, `docs/deck/gauntlet-deck.pdf`, submitted 16 September 2026 |
