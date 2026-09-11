"""Mandatory disclosure constants (SRS-FR-056, SRS-FR-071, SRS 17.5).

These strings are rendered in the results view, in every exported report, and in docs/LIMITATIONS.md.
A test asserts all three render paths include IMPAIRMENT_DISCLOSURE. They cannot be dismissed,
collapsed away or disabled by configuration.
"""

IMPAIRMENT_DISCLOSURE = (
    "Adverse conditions are applied at the application layer, inside the GAUNTLET caller process, to the "
    "caller's outbound audio only. The agent-to-caller direction is not impaired and the operating-system "
    "network stack is not manipulated. Frame substitution approximates packet loss; it does not reproduce "
    "receiver-side concealment. Jitter is transmit-side release-time variation. The deployment occupies a "
    "single region, so results reflect one network path."
)

CALIBRATION_SCOPE = (
    "The calibration bound is a loopback probe-and-pipeline bound: caller and calibration target share one "
    "host and one clock. It does not bound wide-area network variance, provider variance, or the target's "
    "own internal jitter."
)

REFEREE_INDEPENDENCE = (
    "Agent speech is transcribed by a recogniser independent of the target's own, so recognition errors in "
    "the target are not hidden by correlated errors in the judge. Speaker attribution is structural: the "
    "caller worker holds both audio channels, and caller words are known exactly because GAUNTLET "
    "synthesised them."
)

TASK_SUCCESS_IS_INFERENCE = (
    "Task success is a language-model judgement constrained by mandatory turn citations and two-pass "
    "agreement. It is inference, not measurement; disagreements are reported as needs-review, not resolved."
)

TARGET_COST_ESTIMATED = "Estimated, based on your declared unit prices."

REPRODUCIBILITY = (
    "Timing, condition schedules and interruption offsets are deterministic by construction for a given seed. "
    "Caller wording is not: inference providers do not guarantee identical output."
)

ALL = {
    "impairment": IMPAIRMENT_DISCLOSURE,
    "calibration_scope": CALIBRATION_SCOPE,
    "referee_independence": REFEREE_INDEPENDENCE,
    "task_success": TASK_SUCCESS_IS_INFERENCE,
    "target_cost": TARGET_COST_ESTIMATED,
    "reproducibility": REPRODUCIBILITY,
}
