# Known limitations

Maintained continuously: a limitation is added here in the same commit that discovers it. Each item also
appears in the results view where relevant and in every exported report.

## Mandatory disclosure (rendered verbatim in the product and every report)

> Adverse conditions are applied at the application layer, inside the GAUNTLET caller process, to the
> caller's outbound audio only. The agent-to-caller direction is not impaired and the operating-system
> network stack is not manipulated. Frame substitution approximates packet loss; it does not reproduce
> receiver-side concealment. Jitter is transmit-side release-time variation. The deployment occupies a
> single region, so results reflect one network path.

## List

1. **Impairment is application-layer and unidirectional.** Conditions are applied inside the caller process
   to caller-outbound audio. The agent-to-caller direction is not impaired. The OS network stack is not
   manipulated. No codec renegotiation, ICE failure, or bandwidth-estimation collapse is simulated.
2. **Frame substitution approximates packet loss; it does not reproduce it.** Real loss triggers
   receiver-side concealment with characteristic artefacts; substituted silence or a faded repeat does not.
3. **Jitter is transmit-side release-time variation.** It does not reproduce real network variance meeting
   a receiver's adaptive jitter buffer.
4. **The calibration bound is a loopback probe bound.** Caller and calibration target share one host and
   one clock. It does not bound wide-area network variance, provider variance, or the target's own jitter.
5. **Time-to-first-token is not measurable in black-box mode.** GAUNTLET measures time to first audio.
6. **Single-region deployment.** Network measurements reflect one path between one region and the target.
7. **Energy-based voice activity detection has failure cases.** Agents with continuous background audio,
   very quiet output, or speech starting below the adaptive floor may be detected late or flagged
   `floor_fallback`. The margin is configurable per target and printed in the report.
8. **Overlapping-speech agents confound turn-taking metrics.** An agent that talks over callers by design
   produces talk-over that reflects a design choice rather than a defect.
9. **Caller wording is not reproducible across runs.** Timing, conditions and interruption offsets are
   deterministic; provider output is not.
10. **Task success is a model judgement,** constrained by mandatory citations and two-pass agreement.
11. **Target-side cost is an estimate over declared prices** (4 characters per token, configurable
    context factor). Rig cost is measured from provider-returned counters.
12. **No telephony coverage.** The SIP adapter is not built.
13. **No hardware acceleration and no measurement on specialised accelerators.** None was available.
14. **Single-user workspaces.** No teams, roles or invitations.
15. **Self-service account deletion is not implemented.** Deletion is performed by the operator on request.
16. **The reference agent and the synthetic agent are test fixtures, not products.**
17. **Noise beds are synthesised** (D-13): engineered, distinguishable conditions, not recordings of real
    places.
18. **A target that sends audio faster than real time is timed on a playout clock** (D-16). Its
    reported offsets are as heard, which can differ from when bytes were delivered.
19. **Dead air counts agent-side silence only** (D-15). Caller think time is excluded by design.
20. **The local fallback synthesiser produces speech-shaped audio, not intelligible speech.** Without a
    configured synthesis provider, a real speech-recognising agent will not understand the caller; the
    fallback exists for rig testing against energy-based fixtures.
