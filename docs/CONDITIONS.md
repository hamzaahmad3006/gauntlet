# Adverse conditions

All impairment is applied **at the application layer, inside the caller process, to the caller's
outbound audio** (PRD 13.1). Fixed stage order: `noise → jitter → frame substitution → fixed delay →
transmit`. Each stage draws from its own seeded stream, so enabling one stage never shifts another's
schedule, and two runs with the same seed apply identical schedules.

| Id | Condition | Mechanism | Parameters | Safety limit |
|---|---|---|---|---|
| CH-01 | Clean | identity | — | — |
| CH-02 | Frame loss | two-state Gilbert model; lost frames become silence (2 ms raised-cosine fades) or a faded repeat — an **approximation** of loss (D-05) | `loss_probability`, `burst_length`, `concealment` | ≤ 0.20 |
| CH-03 | Jitter | truncated-normal release-time variation | `mean_ms`, `stddev_ms`, `max_ms`, `depth` | `max_ms` ≤ 500 and ≤ depth × 20 ms (D-17) |
| CH-04 | Added delay | fixed delay on release time; subtracted from attributed latency | `delay_ms` | ≤ 2000 |
| CH-05 | Background noise | continuous additive noise at a target SNR computed from the utterance's voiced RMS; synthesised `cafe` and `street` beds (D-13) | `noise_bed`, `snr_db` | 5–30 dB |
| CH-06 | Interruption | seeded schedule: turn indices and offsets drawn before dialling; caller starts talking at agent onset + offset | `interruptions_per_call`, `offset_range_ms` | ≤ 5 per call, 200–4000 ms |
| CH-07 | Slow caller | seeded mid-utterance pause and speech-rate multiplier | `pause_ms`, `speech_rate` | ≤ 3000 ms, 0.7–1.3 |

Achieved values are measured and reported beside configured ones: achieved loss rate (flagged when more
than 1 point off), achieved jitter mean/stddev/max, the transmit inter-frame interval histogram,
achieved SNR, injected delay.

## Profiles (`suites/conditions.yaml`)

| Profile | Composition | Intent |
|---|---|---|
| `clean` | CH-01 | baseline for every comparison and the degradation ratio |
| `mobile` | 3 % loss (bursts of 2), jitter 40 ± 20 ms (max 160), 60 ms delay | a plausible mobile path |
| `hostile` | 8 % loss (bursts of 3), jitter 80 ± 40 ms (max 300), café noise at 12 dB SNR, 2 interruptions per call | stress |
| `turn_taking` | 3 interruptions per call (300–1200 ms), 900 ms mid-utterance pause, 0.9× rate | isolates turn-taking from network effects |

These values are **engineering choices made to produce distinguishable conditions**, not claims about the
statistical distribution of real networks. 3 % / 8 % bracket "noticeable" and "bad" loss; 40/80 ms jitter
sits either side of typical jitter-buffer targets; 12 dB SNR is a loud room; a 900 ms pause is longer
than common endpointing windows (300–800 ms), which is exactly what CH-07 probes.

## Mid-run changes

`POST /v1/runs/{id}/conditions` starts a new epoch. Calls adopt it at their next utterance boundary, so
no turn is measured under two regimes; every turn records its epoch and results break latency down by
epoch.

## Not simulated

Codec renegotiation, ICE failure, bandwidth-estimation collapse, receiver-side concealment artefacts,
agent-to-caller impairment, OS-level network emulation. See LIMITATIONS.md.
