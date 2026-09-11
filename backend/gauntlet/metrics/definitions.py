"""Single source of truth for every product metric name, unit and aggregation (SRS 16.1).

DEFINITIONS_VERSION is stamped on every run. If any formula changes, bump it: comparison across
versions is then blocked exactly like a suite mismatch (SRS 38), because two numbers computed by
different formulas are not comparable.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFINITIONS_VERSION = "1"


@dataclass(frozen=True)
class MetricDef:
    name: str
    met_id: str
    label: str
    unit: str
    direction: str  # lower_is_better | higher_is_better | none
    definition: str


METRICS: dict[str, MetricDef] = {
    m.name: m
    for m in [
        MetricDef("response_latency_p50", "MET-01", "Response latency p50", "ms", "lower_is_better",
                  "Median of per-turn t_agent_first_audio - t_caller_last_voiced_sample, over turns that were not "
                  "censored by the turn timeout and where the agent was not still talking when the caller "
                  "finished. Nearest rank."),
        MetricDef("response_latency_p95", "MET-02", "Response latency p95", "ms", "lower_is_better",
                  "95th percentile of the same sample. Nearest rank."),
        MetricDef("response_latency_p99", "MET-03", "Response latency p99", "ms", "lower_is_better",
                  "99th percentile of the same sample. Nearest rank."),
        MetricDef("time_to_first_response_p50", "MET-04", "Time to first response p50", "ms", "lower_is_better",
                  "Median over calls of the response latency of caller turn 1."),
        MetricDef("barge_in_stop_p95", "MET-05", "Barge-in stop time p95", "ms", "lower_is_better",
                  "95th percentile of t_agent_speech_offset - t_caller_interrupt_onset over applicable "
                  "interruptions; non-yields are included censored at 2000 ms."),
        MetricDef("yield_rate", "MET-06", "Yield rate", "%", "higher_is_better",
                  "Applicable interruptions where the agent stopped within 2000 ms, as a percentage."),
        MetricDef("talkover_mean", "MET-07", "Talk-over per call", "ms", "lower_is_better",
                  "Mean over calls of the total intersection of caller and agent speech intervals."),
        MetricDef("dead_air_ratio", "MET-08", "Dead-air ratio", "%", "lower_is_better",
                  "Mean over calls of: agent-side silences longer than 1500 ms (awaiting a response, or "
                  "mid-response pauses) divided by conversation duration. Caller think time is excluded "
                  "because it is the rig's, not the target's."),
        MetricDef("call_completion_rate", "MET-09", "Call completion rate", "%", "higher_is_better",
                  "Calls terminating without a transport, protocol or rig fault, as a percentage."),
        MetricDef("session_error_rate", "MET-10", "Session error rate", "%", "lower_is_better",
                  "Calls terminating with status errored, as a percentage."),
        MetricDef("task_success_rate", "MET-11", "Task success rate", "%", "higher_is_better",
                  "Calls whose goal checklist was satisfied with valid turn citations, over scored calls "
                  "excluding needs_review and scoring_failed."),
        MetricDef("needs_review_rate", "MET-12", "Needs-review rate", "%", "lower_is_better",
                  "Scored calls where the two scoring passes disagreed."),
        MetricDef("est_cost_per_session", "MET-13", "Estimated target cost per session", "USD", "none",
                  "Estimated from declared unit prices; see docs/COST_MODEL.md."),
        MetricDef("est_cost_per_successful_session", "MET-14", "Estimated target cost per successful session",
                  "USD", "none", "Estimated total target cost divided by successful sessions."),
        MetricDef("degradation_ratio", "MET-15", "Degradation ratio", "ratio", "lower_is_better",
                  "Response latency p95 of this run divided by that of a clean-profile run on the same "
                  "target and suite version."),
        MetricDef("readiness", "MET-16", "Readiness score", "0-100", "higher_is_better",
                  "Deterministic composite, SRS 19."),
        MetricDef("rig_overhead_p95", "MET-21", "Caller turnaround overhead p95", "ms", "lower_is_better",
                  "Caller-side inference plus synthesis time per turn. Precedes the measured interval."),
        MetricDef("peak_concurrency", "MET-22", "Peak concurrency", "sessions", "none",
                  "Maximum simultaneously active calls, sampled at 1 Hz. Measured, never requested."),
        MetricDef("cache_hit_rate", "MET-23", "Utterance cache hit rate", "%", "none",
                  "Caller utterances served from the synthesis cache."),
        MetricDef("rig_cost_usd", "MET-24", "Rig cost per run", "USD", "none",
                  "GAUNTLET's own provider spend, from provider-returned counters x configured prices."),
        MetricDef("fallback_rate", "-", "Caller fallback rate", "%", "none",
                  "Turns whose utterance came from a scripted fallback line."),
        MetricDef("premature_speech_rate", "-", "Premature speech rate", "%", "lower_is_better",
                  "Caller turns during which the agent began speaking before the caller finished (CH-07)."),
        MetricDef("reconnect_rate", "-", "Reconnect rate", "%", "none", "Calls with attempt > 1."),
    ]
}
