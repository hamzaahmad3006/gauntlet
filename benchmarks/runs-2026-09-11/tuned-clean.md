# GAUNTLET report — Bella Tavola — synthetic (tuned)

**Run** `01a0914e-e659-7a74-9737-168853882c9b` · status **completed** · grade **—**

> Grade not emitted: two_or_more_subscores_unavailable: SC-04 Task quality, SC-05 Resilience


## Metrics

| Metric | Value | Threshold | Status | n | Evidence |
|---|---|---|---|---|---|
| - Caller fallback rate | 55.814% | — (THRESHOLD) | — | 172 | MEASURED |
| - Premature speech rate | 27.907% | — (THRESHOLD) | — | 172 | MEASURED |
| - Reconnect rate | 0% | — (THRESHOLD) | — | 24 | MEASURED |
| MET-01 Response latency p50 | 745.661 ms | — (THRESHOLD) | — | 172 | MEASURED |
| MET-02 Response latency p95 | 757.96 ms | 1500 ms (THRESHOLD) | pass | 172 | MEASURED |
| MET-03 Response latency p99 | 787.633 ms | — (THRESHOLD) | — | 172 | MEASURED |
| MET-04 Time to first response p50 | 750.174 ms | 1200 ms (THRESHOLD) | pass | 24 | MEASURED |
| MET-07 Talk-over per call | 571.226 ms | 1200 ms (THRESHOLD) | pass | 24 | MEASURED |
| MET-08 Dead-air ratio | 0% | 5% (THRESHOLD) | pass | 24 | MEASURED |
| MET-09 Call completion rate | 100% | 97% (THRESHOLD) | pass | 24 | MEASURED |
| MET-10 Session error rate | 0% | 3% (THRESHOLD) | pass | 24 | MEASURED |
| MET-21 Caller turnaround overhead p95 | 267.165 ms | — (THRESHOLD) | — | 172 | MEASURED |
| MET-23 Utterance cache hit rate | 11.818% | — (THRESHOLD) | — | 220 | MEASURED |

## Sub-scores

| Sub-score | Score | Weight | Effective weight |
|---|---|---|---|
| SC-01 Responsiveness | 100 | 0.3 | 0.0 |
| SC-02 Turn-taking | 100 | 0.25 | 0.0 |
| SC-03 Reliability | 100 | 0.2 | 0.0 |
| SC-04 Task quality | unavailable | 0.15 | 0.0 |
| SC-05 Resilience | unavailable | 0.1 | 0.0 |

## Configuration

- Suite: Booking core `a9fe9d44b7a5f605…`
- Seed: `20260913`
- Conditions: `clean` {}
- Thresholds: `default` `b997684a40cdf31e…`
- Concurrency: requested 8, measured peak 4
- Rig cost (MEASURED): 0 USD pricing_not_configured

## Calibration

Measurement error bound **3.897 ms** over 80 loopback repetitions (commit `61ef2ea2`, Windows 11 / Python 3.12.10 / AMD64). The calibration bound is a loopback probe-and-pipeline bound: caller and calibration target share one host and one clock. It does not bound wide-area network variance, provider variance, or the target's own internal jitter.

## Limitations

- Adverse conditions are applied at the application layer, inside the GAUNTLET caller process, to the caller's outbound audio only. The agent-to-caller direction is not impaired and the operating-system network stack is not manipulated. Frame substitution approximates packet loss; it does not reproduce receiver-side concealment. Jitter is transmit-side release-time variation. The deployment occupies a single region, so results reflect one network path.
- The calibration bound is a loopback probe-and-pipeline bound: caller and calibration target share one host and one clock. It does not bound wide-area network variance, provider variance, or the target's own internal jitter.
- Task success is a language-model judgement constrained by mandatory turn citations and two-pass agreement. It is inference, not measurement; disagreements are reported as needs-review, not resolved.
- Timing, condition schedules and interruption offsets are deterministic by construction for a given seed. Caller wording is not: inference providers do not guarantee identical output.
- Time-to-first-token is not measurable in black-box mode; GAUNTLET measures time to first audio.
- Dead air counts agent-side silence only; the caller's own think time is excluded by design.
- Energy-based voice activity detection can detect late or fail on agents with continuous background audio.
