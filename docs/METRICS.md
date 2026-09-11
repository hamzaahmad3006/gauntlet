# Metrics

Every metric is computed by arithmetic over timestamps on one clock (`time.perf_counter_ns`, D-08).
Single source of truth: `backend/gauntlet/metrics/definitions.py` (`DEFINITIONS_VERSION` is stamped on
every run; runs with different versions cannot be compared). Percentiles are **nearest rank**, so a
reported p95 is always a value that was actually observed. Samples under 20 are flagged `low_sample`.

## Timeline convention

A frame stamped `t` covers `[t, t + 20 ms)`; sample `i` is at `t + i/16000`. Caller times are the
**actual transmit** times after every impairment stage. Agent times come from a **playout clock** on the
receive path (D-16): a speech frame cannot be heard before the previous one finished.

The acoustic probe (`media/probe.py`) uses frame RMS in dBFS, an adaptive floor (10th percentile of the
last 150 non-speech frames), threshold = floor + 12 dB, onset after 3 frames above, offset after 15
below, reported at the first/last sample crossing the threshold (sub-frame interpolation).

## Target metrics

| Id | Metric | Definition | Unit |
|---|---|---|---|
| MET-01..03 | Response latency p50/p95/p99 | `t_agent_first_audio − t_caller_last_voiced_sample` per caller turn, over turns not censored by the turn timeout and where the agent was not still talking when the caller finished | ms |
| MET-04 | Time to first response | median across calls of the latency of caller turn 1 (D-18) | ms |
| MET-05 | Barge-in stop time p95 | `t_agent_speech_offset − t_caller_interrupt_onset` for interruptions fired while the agent was speaking; no stop within 2000 ms is **censored at 2000** and flagged `no_yield` (included in the percentile, never dropped) | ms |
| MET-06 | Yield rate | applicable interruptions where the agent stopped within 2000 ms | % |
| MET-07 | Talk-over | total intersection of caller and agent speech intervals per call; mean over calls | ms |
| MET-08 | Dead-air ratio | agent-side silences longer than 1500 ms — the wait for a response and pauses inside it — divided by conversation duration; caller think time excluded (D-15); mean over calls | % |
| MET-09 | Call completion rate | calls not ending `errored` (transport, protocol or rig fault) | % |
| MET-10 | Session error rate | calls ending `errored` | % |
| MET-11 | Task success rate | calls whose goal checklist was met with valid turn citations, over scored calls excluding `needs_review` and `scoring_failed` | % |
| MET-12 | Needs-review rate | scored calls where the two scoring passes disagreed | % |
| MET-13/14 | Estimated target cost per session / per successful session | model over declared prices, see COST_MODEL.md; undefined (not zero) with no successes | USD |
| MET-15 | Degradation ratio | this run's latency p95 ÷ the latest clean-profile run's p95 on the same target, suite version and definitions | ratio |
| MET-16 | Readiness score | composite, below | 0–100 |

Also reported: premature speech rate (caller turns during which the agent started talking), caller
fallback rate, utterance cache hit rate, rig overhead p95 (caller inference + synthesis — it *precedes*
the measured interval and never contaminates it), reconnect rate, measured peak concurrency.

## What is measured, controlled, simulated, injected, inferred

| Class | Items |
|---|---|
| Measured | agent onset/offset, latency, barge-in stop, talk-over, dead air, duration, achieved impairment, caller inference and synthesis durations, provider token/character/second counts |
| Controlled | caller text and timing, interruption offsets, speech rate, voice, turn budget, concurrency, seeds, condition parameters |
| Simulated | packet loss (pre-encode substitution, D-05), jitter (transmit-side release times), noise (additive, synthesised beds, D-13) |
| Injected | frame substitution, release-time variation, fixed delay, noise mixing |
| Inferred | task success (model, with citations), target-side cost (declared prices) |

Time-to-first-token is **not** measurable in black-box mode; GAUNTLET measures time to first audio.

## Readiness score (deterministic)

Each metric is normalised piecewise-linearly: `ideal → 100`, `threshold → 70`, `limit → 0`, with
decimal arithmetic. Sub-scores (weights in `suites/thresholds-default.yaml`):

| Sub-score | Weight | Inputs |
|---|---|---|
| SC-01 Responsiveness | 0.30 | latency p95 (0.7), time to first response (0.3) |
| SC-02 Turn-taking | 0.25 | barge-in p95 (0.5), talk-over (0.3), dead air (0.2) |
| SC-03 Reliability | 0.20 | completion (0.6), error rate (0.4) |
| SC-04 Task quality | 0.15 | task success (1.0) |
| SC-05 Resilience | 0.10 | degradation ratio (1.0) |

Missing input → its weight is redistributed within the sub-score and the run is flagged
`partial_scoring` (D-14). A sub-score with no inputs is unavailable and its weight redistributed; **two
unavailable sub-scores suppress the grade**. Fewer than 20 completed calls → no grade
(`insufficient_sample`). Hard breaches cap the grade at F: completion < 90 %, yield < 80 %, task
success < 50 %. Grades: A ≥ 90, B ≥ 80, C ≥ 70, D ≥ 60, F below.

## Comparison and gate

Recommendation (A = baseline, B = candidate): R1 B has a hard breach and A does not → A; R2 B beats A
by more than 3 points → B; R3 within 3 points and costs known → cheaper; R4 no change. The rule id is
always shown. A gate fails on a score drop beyond tolerance, any metric crossing from pass to breach, or
a hard breach; aborted, budget-aborted or ungraded runs are *ungatable* (distinct exit code).
