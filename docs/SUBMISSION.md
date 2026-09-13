# Submission kit — lablab.ai × AI Infra Summit

Everything needed to submit. Every number below is traced to a committed file; if a number is not in this
document, it does not go into the video, the deck or the description.

| Number | Label | Source |
|---|---|---|
| 3.897 ms measurement error bound (80 loopback repetitions) | MEASURED | `calibration/results.csv`, `calibration/summary.json` |
| 8 concurrent calls sustained in one process; saturates at 12 | MEASURED | `benchmarks/rig-2026-09-11.csv`, `benchmarks/summary.json` |
| Tuned agent · mobile: grade A, 100.0, latency p95 786 ms | MEASURED | `benchmarks/runs-2026-09-11/tuned-mobile.md` |
| Slow-endpointing agent · mobile: grade C, 76.17, latency p95 1,639.5 ms, dead air 15.6 % | MEASURED | `benchmarks/runs-2026-09-11/slow-mobile.md` |
| Gate failed: score −23.83, latency p95 +853 ms, time to first response +849 ms, dead air +15.6 pts | MEASURED | `benchmarks/runs-2026-09-11/gate-slow-vs-tuned.md` |
| 50 ms calibration acceptable maximum; 1,500 ms p95 latency threshold | THRESHOLD | `calibration/run_calibration.py`, `suites/thresholds-default.yaml` |
| ≥ 10 concurrent calls | TARGET — not met on the laptop | PRD MET-22 |

Caveat that must travel with the run numbers: they come from a laptop with the bundled synthetic agent in
scripted mode and no provider keys, so task success was not scored. Say so wherever they appear.

## Title

**GAUNTLET — the infrastructure crash-test rig for real-time voice AI**

## Short description (≤ 255 characters)

GAUNTLET dials voice agents with synthetic callers, measures latency and turn-taking from the caller's ear
under seeded network chaos, and returns a deterministic readiness score that can fail a pull request.

## Long description

Voice agents rarely fail by saying the wrong thing. They fail by answering 1.9 s late, by talking over a
caller who interrupts, by leaving dead air, or by degrading under load — none of which shows up in an APM
trace, a transcript evaluation, or an HTTP load test.

GAUNTLET is a load generator and profiler for real-time voice inference. It connects to an agent over a
WebSocket PCM protocol or a LiveKit (WebRTC) room, drives goal-directed conversations with synthetic callers,
and measures every interaction acoustically: one caller process holds both audio directions on one
high-resolution clock, so latencies carry no clock skew and the agent needs no instrumentation.

Adverse conditions are applied deterministically from seeded, per-stage streams — frame loss (Gilbert
model), jitter, added delay, background noise at a target SNR, seeded interruptions and hesitant callers —
and can be changed mid-run. Results become a deterministic readiness score against a versioned threshold
profile (no language model assigns it), two runs can be compared with a documented recommendation rule, and
a GitHub Action fails a pull request when a metric regresses.

The rig publishes its own accuracy: a calibration harness measured a 3.897 ms error bound over 80 loopback
repetitions, and a rig benchmark measured 8 sustained concurrent calls on the development laptop. In a full
benchmark of two tunings of the bundled agent, the well-tuned one graded A and the one with slow endpointing
graded C, and the gate failed it on four breaches.

**Metric definitions**

- **Response latency p50/p95/p99** — caller's last voiced sample to the agent's first audio, per turn, nearest
  rank, excluding turns censored by the turn timeout.
- **Time to first response** — median across calls of the first caller turn's latency.
- **Barge-in stop time p95** — caller interruption onset to agent speech offset; a non-yield is censored at
  2,000 ms and kept in the percentile.
- **Yield rate** — interruptions where the agent stopped within 2,000 ms.
- **Talk-over** — total simultaneous speech per call.
- **Dead-air ratio** — agent-side silences longer than 1.5 s divided by conversation duration.
- **Call completion / session error rate** — calls ending without / with a transport, protocol or rig fault.
- **Task success** — goal checklist met with verbatim turn citations from an independent transcript, judged
  twice; disagreement is reported as needs-review.
- **Degradation ratio** — impaired-run latency p95 divided by the clean-run p95 on the same target and suite.
- **Cost per successful session** — rig cost measured from provider counters; target cost estimated from
  declared prices; never summed.

**Honest scope.** Impairment is application-layer and caller-outbound only; frame substitution approximates
packet loss; the error bound is a loopback bound; task success is model inference constrained by
citations; no hardware acceleration is claimed. Integrations with Speechmatics, Groq, ElevenLabs and LiveKit
are implemented and labelled unverified until they run against the services.

**Built with:** Python 3.12, FastAPI, NumPy, SQLAlchemy, Redis Streams, WebSockets, LiveKit SDK, React,
Vite, TanStack Query, Tailwind CSS, GitHub Actions.

## Video script (≤ 5 minutes, subtitles on)

Only one segment is live (step 4–5). Everything else shows stored runs and says so. The REPLAY badge must be
visible whenever a stored run plays through the live view.

| Time | Screen | Say |
|---|---|---|
| 0:00–0:20 | Call detail: paired waveforms, talk-over shaded, a turn marked `timeout` | "A voice agent rarely fails by saying the wrong thing. It fails on timing — and nothing in the standard stack measures that." |
| 0:20–0:45 | Landing page, then Targets | "GAUNTLET dials your agent with synthetic callers and measures from the caller's ear — one process, both audio directions, one clock. No access to the agent's code." |
| 0:45–1:05 | Suites and conditions page | "Scenarios, personas and network conditions are versioned data. Every impairment is seeded, so two runs with the same seed get the same schedule." |
| 1:05–1:35 | New run → Start; live view with LIVE badge, tiles filling | "This is live: calls connecting, per-turn latency against the 1.5-second threshold." |
| 1:35–2:05 | Press **⚡ hostile** mid-run; rolling p95 divider; tiles show timeouts | "Now I inject hostile conditions — café noise, loss, jitter. The agent's voice detector hears the noise as speech and stops answering. That is a real failure, caught in thirty seconds." |
| 2:05–2:35 | Results page of the stored tuned run; expand a sub-score | "The score is arithmetic, not a model's opinion — every input and weight is visible. This stored run of the tuned agent graded A." |
| 2:35–3:05 | Compare page: tuned vs slow endpointing | "Same suite, same seed, two configurations. The slow one graded C: p95 latency 786 to 1,640 milliseconds. The rule that decided is on screen." |
| 3:05–3:30 | `gate-slow-vs-tuned.md` rendered (or the PR comment once deployed) | "The gate fails on four breaches, with baseline, candidate and delta for each — this is what a pull request sees." |
| 3:30–3:55 | Calibration page | "A measurement tool has to publish its own error. Ours: 3.9 milliseconds over 80 loopback repetitions — a loopback bound, and we say so." |
| 3:55–4:15 | README integration table and limitations | "What is verified and what is not is written down. Impairment is application-layer; task success needs a referee key." |
| 4:15–4:30 | Closing card: URL, repository | "Real-time voice ships without load testing. GAUNTLET is the instrument for it." |

Failure line, rehearsed: "The live segment just failed — here is the stored run instead, labelled REPLAY."

## Deck — 12 slides

1. **GAUNTLET** — the infrastructure crash-test rig for real-time voice AI. URL, repository.
2. **The failure nobody measures** — late answers, talk-over, dead air, collapse under load; invisible to APM,
   transcript evals and HTTP load tests.
3. **Why voice is different** — stateful sessions, perceptual latency, continuous media, positive feedback
   into failure.
4. **What GAUNTLET does** — synthetic callers → real media → acoustic measurement → deterministic score → CI gate.
5. **How it measures** — one process, both directions, one clock; energy probe with sub-frame timing; metric
   definitions table.
6. **Controlled chaos** — loss, jitter, delay, noise, interruptions, hesitation; seeded per stage; mid-run epochs.
7. **The rig's own error** — 3.897 ms bound over 80 repetitions (MEASURED, loopback); 8 concurrent calls
   sustained on a laptop (MEASURED); aim of 10 not yet met (TARGET).
8. **Result** — tuned A (100.0) vs slow endpointing C (76.17); gate failed on four breaches (MEASURED,
   laptop, scripted agent, task success unscored).
9. **Models only where judgement is unavoidable** — caller words and task-success judge use models; conditions,
   measurement, score, gate and cost are deterministic code.
10. **Adjacent tools, stated carefully** — voice-eval platforms (conversation quality), observability
    (passive), HTTP load tools (no media); GAUNTLET's claim is the media path, turn-taking and determinism
    "based on public positioning".
11. **Business** — free / team / usage / enterprise; revenue follows synthetic call minutes; no margin claimed
    because rig cost is not yet measured with real prices.
12. **Honest scope and next** — limitations list; next: verified providers, SIP, bidirectional impairment,
    public benchmark.

## Checklist for submission day

| Item | Owner | Status |
|---|---|---|
| Public URL (Render Free + free PostgreSQL, `render.yaml`) with `/healthz` 200 | Hamza creates the Blueprint; then verify | Pending |
| Provider keys in Render (optional) | Hamza | Pending |
| Repository public, contributors = hamzaahmad3006 only | — | Done |
| README, LIMITATIONS, TRACEABILITY, SUBMISSION | — | Done |
| Calibration and rig benchmark committed | — | Done |
| Real pull request with a failing check | needs the public URL + an API key secret | Pending |
| Video recorded (≤ 5 min, subtitles) | Hamza records, script above | Pending |
| 12-slide PDF deck | generated from `docs/deck/` | See `docs/deck/` |
| Claim audit: every number in video/deck/description is in the table at the top | — | Do before submitting |
