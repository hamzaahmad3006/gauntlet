# Methodology

GAUNTLET is a black-box benchmark harness. It connects to a voice agent through a media adapter,
drives a real conversation with a synthetic caller, and measures the interaction **acoustically** — from
the audio the caller actually receives — so it works on agents whose internals are unavailable.

## Principles

1. **One clock, one process.** The caller process owns both audio directions; every latency is a
   difference of two readings of one monotonic high-resolution clock.
2. **Deterministic conditions.** Impairment schedules and interruption offsets are derived from the run
   seed before anything is dialled. Caller *wording* is not reproducible across runs (providers are not
   bit-identical); timing, conditions and offsets are.
3. **Language models only where judgement or generation is unavoidable.** The caller model writes words
   (the state machine decides when to speak, interrupt or hang up); the evaluator judges task success
   with mandatory verbatim citations and two passes. Condition injection, measurement, scoring, gating
   and cost are deterministic code.
4. **Independence of the referee.** Agent speech is transcribed by a recogniser independent of the
   target's own. Speaker attribution is structural (separate channels), not acoustic diarization (D-01).
5. **Honest scope.** See the measured / controlled / simulated / injected / inferred table in
   METRICS.md, the calibration scope in CALIBRATION.md, and LIMITATIONS.md.

## Evidence labels

Every number is **MEASURED** (produced by a stored run or a committed artefact), **THRESHOLD** (a policy
boundary), **TARGET** (an aim), or **ESTIMATED** (a model over declared prices). Live views are labelled
LIVE or REPLAY.

## Reproducibility

Two runs with the same seed, suite hash, condition profile and target apply byte-identical condition
schedules and interruption offsets. Runs store the suite hash, threshold profile version and metric
definitions version; comparison across any mismatch is refused.
