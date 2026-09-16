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
| Live call with every provider: AI caller 0 % fallback, Speechmatics transcript, task success judged true (4/4 steps, judges agreed); the hosted agent pipeline answered in 2.3–3.8 s from a laptop in Pakistan | MEASURED, one call | `benchmarks/providers-2026-09-13/` |
| 50 ms calibration acceptable maximum; 1,500 ms p95 latency threshold | THRESHOLD | `calibration/run_calibration.py`, `suites/thresholds-default.yaml` |
| ≥ 10 concurrent calls | TARGET — not met on the laptop | PRD MET-22 |

Caveat that must travel with the run numbers: they come from a laptop with the bundled synthetic agent in
scripted mode and no provider keys, so task success was not scored. Say so wherever they appear.
The live provider call is a single call: it proves the integrations work end to end; its latency is the
reference agent's hosted pipeline over a long network path, not a benchmark of any provider.

## Submission form copy (lablab.ai)

**Title** (47 / 50)

`GAUNTLET: Crash-Test Rig for Real-Time Voice AI`

**Short description** (211 / 255)

> GAUNTLET dials voice AI agents with synthetic callers, measures latency and turn-taking from the caller's
> ear under seeded network chaos, and returns a deterministic readiness score that can fail a pull request.

**Technologies to tick:** ElevenLabs, Groq, and Speechmatics / LiveKit / FastAPI / React where the list
offers them. Not Anthropic Claude and not LangChain — neither runs in the product.

**Participation mode:** online.

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

## Video script (target 4:35, hard limit 5:00, subtitles on)

Record each scene separately and cut them together. Only scenes 1 and 4 are live; everything else shows
stored runs. Never speak a number that is not on screen or in the table at the top of this file.

| # | Time | Page | On screen | Say |
|---|---|---|---|---|
| 1 | 0:00–0:30 | Talk to agent | Pick the **slow** agent, press the microphone, ask for a table, let the silence run, then point at the reply's ⏱ badge | "That reply took [the ⏱ number] milliseconds. Did you feel that pause? That's how most voice agents fail — not by saying the wrong thing, but by answering late, talking over you, or leaving dead air. And nothing in the normal stack measures it. This is GAUNTLET." |
| 2 | 0:30–0:55 | Landing | Hero, then scroll to the four steps | "GAUNTLET is a crash-test rig for real-time voice AI. It dials your agent with synthetic callers over real audio, measures every turn from the caller's ear — with no code inside your agent — injects network chaos from a seed, and turns the result into a deterministic score that can fail a pull request." |
| 3 | 0:55–1:25 | New run | Scenarios, personas, the condition dropdown, then **Start a 1-call demo** | "Scenarios, caller personas and network conditions are all versioned data. Personas change how the caller speaks. Every impairment comes from a seed, so the same seed replays exactly the same chaos." |
| 4 | 1:25–2:10 | Live run | The live conversation filling in; hover a reply's answer time; press **⚡ hostile** mid-call | "This is live. Every reply shows how long the agent took to start answering, against a 1.5-second threshold. Now I inject hostile conditions — café noise, packet loss, jitter — mid-call." |
| 5 | 2:10–2:40 | Call detail | Paired waveforms, play a few seconds of the recording, transcript, verdict citations | "Every call is recorded on one clock. An independent Speechmatics transcript feeds a judge that must quote the exact agent turn for every goal it marks as met. Timing is measured; only task success uses a model." |
| 6 | 2:40–3:10 | Results (slow · mobile) | Grade C ring, the three red breach rows, one expanded sub-score | "A full 24-call benchmark on a mobile network profile. Slow endpointing: grade C, 76 out of 100. The score is plain arithmetic — every input and weight is on screen." |
| 7 | 3:10–3:35 | Compare | Tuned (A) against slow (C), the recommendation | "Same suite, same seed, same network. The tuned agent graded A with a 786 millisecond p95; the slow one, 1,640 milliseconds and 15 percent dead air. The rule says: keep A." |
| 8 | 3:35–3:55 | CI gate | The failed gate row, then the workflow YAML | "Drop this GitHub Action into your repo and a regression fails the pull request — here, four breaches, before any customer heard it." |
| 9 | 3:55–4:15 | Calibration | The 3.897 ms budget bar and the per-delay bars | "A measuring tool has to publish its own error. Ours: 3.897 milliseconds over 80 loopback repetitions — a loopback bound, and we say so." |
| 10 | 4:15–4:35 | Landing, closing banner | The banner, then the repository link | "Real-time voice ships without load testing. GAUNTLET is the instrument for it — open source, on GitHub." |

Rehearsed failure line: "The live call just failed — here is the stored run instead, labelled REPLAY."

Never say: winner, fastest, production-ready, any hardware claim, or "task success 100%" (the 24-call
benchmarks ran without provider keys, so task success was not scored there).

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
| Public URL (Render Free + free PostgreSQL, `render.yaml`) with `/healthz` 200 | Hamza creates the Blueprint; then verify | Pending — optional if the form accepts a repository link |
| Provider keys (local `.env` done and verified live; Render optional) | Hamza | Done locally |
| Repository public, contributors = hamzaahmad3006 only | — | Done |
| README, LIMITATIONS, TRACEABILITY, SUBMISSION | — | Done |
| Calibration and rig benchmark committed | — | Done |
| Real pull request with a failing check | needs the public URL + an API key secret | Pending |
| Video recorded (≤ 5 min, subtitles) | Hamza records, script above | Pending |
| 12-slide PDF deck | `docs/deck/gauntlet-deck.pdf`, light theme, every number traced | Done |
| Claim audit: every number in video/deck/description is in the table at the top | — | Do before submitting |
