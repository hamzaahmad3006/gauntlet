# GAUNTLET report — Bella Tavola — synthetic (tuned)

**Run** `01a09bbb-2d48-7f27-87a3-43099fd7ea35` · status **completed** · grade **—**

> Grade not emitted: insufficient_sample: 1 completed calls, minimum 20


## Metrics

| Metric | Value | Threshold | Status | n | Evidence |
|---|---|---|---|---|---|
| MET-02 Response latency p95 | 3,816.643 ms | 1500 ms (THRESHOLD) | breach | 6 | MEASURED |
| MET-04 Time to first response p50 | 3,309.486 ms | 1200 ms (THRESHOLD) | breach | 1 | MEASURED |
| MET-08 Dead-air ratio | 18.213% | 5% (THRESHOLD) | breach | 1 | MEASURED |
| - Caller fallback rate | 0% | — (THRESHOLD) | — | 6 | MEASURED |
| - Premature speech rate | 0% | — (THRESHOLD) | — | 6 | MEASURED |
| - Reconnect rate | 0% | — (THRESHOLD) | — | 1 | MEASURED |
| MET-01 Response latency p50 | 2,498.577 ms | — (THRESHOLD) | — | 6 | MEASURED |
| MET-03 Response latency p99 | 3,816.643 ms | — (THRESHOLD) | — | 6 | MEASURED |
| MET-07 Talk-over per call | 0 ms | 1200 ms (THRESHOLD) | pass | 1 | MEASURED |
| MET-09 Call completion rate | 100% | 97% (THRESHOLD) | pass | 1 | MEASURED |
| MET-10 Session error rate | 0% | 3% (THRESHOLD) | pass | 1 | MEASURED |
| MET-11 Task success rate | 100% | 85% (THRESHOLD) | pass | 1 | MEASURED |
| MET-12 Needs-review rate | 0% | — (THRESHOLD) | — | 1 | MEASURED |
| MET-21 Caller turnaround overhead p95 | 1,721.654 ms | — (THRESHOLD) | — | 6 | MEASURED |
| MET-23 Utterance cache hit rate | 0% | — (THRESHOLD) | — | 6 | MEASURED |

## Sub-scores

| Sub-score | Score | Weight | Effective weight |
|---|---|---|---|
| SC-01 Responsiveness | 0 | 0.3 | 0.0 |
| SC-02 Turn-taking | 63.34 | 0.25 | 0.0 |
| SC-03 Reliability | 100 | 0.2 | 0.0 |
| SC-04 Task quality | 100 | 0.15 | 0.0 |
| SC-05 Resilience | unavailable | 0.1 | 0.0 |

## Configuration

- Suite: Booking core `a9fe9d44b7a5f605…`
- Seed: `13`
- Conditions: `clean` {}
- Thresholds: `default` `b997684a40cdf31e…`
- Concurrency: requested 1, measured peak 1
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
