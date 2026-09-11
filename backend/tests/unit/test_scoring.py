"""Scoring engine determinism, caps, missing data, comparison rules, gate (TC-090..096)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from gauntlet.scoring.compare import IncompatibleRuns, RunSide, compare, recommend
from gauntlet.scoring.gate import Ungatable, evaluate
from gauntlet.scoring.normalise import normalise
from gauntlet.scoring.profile import Bound, ProfileError, ThresholdProfile
from gauntlet.scoring.score import score
from gauntlet.suites.loader import bundled_thresholds

PROFILE = bundled_thresholds()

GOOD = {
    "response_latency_p95": 900.0, "time_to_first_response_p50": 800.0, "barge_in_stop_p95": 400.0,
    "talkover_mean": 600.0, "dead_air_ratio": 3.0, "call_completion_rate": 100.0, "session_error_rate": 0.0,
    "task_success_rate": 96.0, "degradation_ratio": 1.2, "yield_rate": 100.0,
}


def test_normalisation_anchor_points():
    b = Bound(900, 1500, 3000, "lower_is_better")
    assert float(normalise(900, b)) == 100.0
    assert float(normalise(1500, b)) == 70.0
    assert float(normalise(3000, b)) == 0.0
    assert float(normalise(1200, b)) == 85.0
    h = Bound(95, 85, 50, "higher_is_better")
    assert float(normalise(85, h)) == 70.0 and float(normalise(40, h)) == 0.0


def test_perfect_run_scores_a():
    r = score(GOOD, PROFILE, completed_calls=24)
    assert r.overall == 100.0 and r.grade == "A" and not r.flags


def test_tc092_completion_below_hard_limit_caps_at_f():
    m = dict(GOOD, call_completion_rate=70.0)
    r = score(m, PROFILE, completed_calls=24)
    assert r.grade == "F" and r.caps and "call completion rate" in r.caps[0]


def test_insufficient_sample_emits_no_grade():
    r = score(GOOD, PROFILE, completed_calls=19)
    assert r.grade is None and r.overall is None and r.suppressed_reason.startswith("insufficient_sample")


def test_missing_input_redistributes_within_subscore_and_flags():
    m = dict(GOOD)
    del m["barge_in_stop_p95"]
    r = score(m, PROFILE, 24)
    assert "partial_scoring" in r.flags and "barge_in_stop_p95" in r.missing_metrics
    sc02 = next(s for s in r.subscores if s.id == "SC-02")
    assert sc02.available and sc02.score == 100.0


def test_two_unavailable_subscores_suppress_grade():
    m = dict(GOOD)
    del m["task_success_rate"]
    del m["degradation_ratio"]
    r = score(m, PROFILE, 24)
    assert r.grade is None and "two_or_more_subscores_unavailable" in r.suppressed_reason


def test_tc090_inverted_bounds_rejected():
    doc = dict(PROFILE.source)
    doc = {**doc, "metrics": {**doc["metrics"], "talkover_mean": {"ideal": 2000, "threshold": 1200, "limit": 4000,
                                                                   "direction": "lower_is_better"}}}
    with pytest.raises(ProfileError, match="talkover_mean"):
        ThresholdProfile.from_document(doc)


metric_values = st.fixed_dictionaries({k: st.floats(0, 5000, allow_nan=False) for k in GOOD})


@settings(max_examples=300)
@given(metric_values, st.integers(0, 60))
def test_tc091_score_is_a_pure_function(m, n):
    assert score(m, PROFILE, n).as_dict() == score(dict(m), PROFILE, n).as_dict()


def side(run_id, overall, hard=False, cost=None, metrics=None, suite="s1"):
    return RunSide(run_id, suite, PROFILE.version_hash, "1", metrics or dict(GOOD), overall, "A", hard,
                   cost_per_successful_session=cost)


def test_tc094_each_recommendation_rule_fires():
    assert recommend(side("a", 80), side("b", 90, hard=True), 3)["rule_id"] == "R1"
    assert recommend(side("a", 80), side("b", 85), 3)["rule_id"] == "R2"
    r3 = recommend(side("a", 80, cost=0.05), side("b", 81, cost=0.03), 3)
    assert r3["rule_id"] == "R3" and r3["recommendation"] == "B"
    assert recommend(side("a", 80), side("b", 81), 3)["rule_id"] == "R4"
    worse = recommend(side("a", 100), side("b", 76), 3)
    assert worse["rule_id"] == "R4" and "keep A" in worse["rationale"]


def test_tc093_comparison_blocked_across_suite_versions():
    with pytest.raises(IncompatibleRuns) as e:
        compare(side("a", 80, suite="hash-one"), side("b", 81, suite="hash-two"), PROFILE)
    assert e.value.code == "suite_mismatch" and e.value.a == "hash-one" and e.value.b == "hash-two"


def test_tc096_gate_names_breached_metric_with_delta():
    base = side("base", 95.0)
    cand = side("cand", 88.0, metrics=dict(GOOD, barge_in_stop_p95=1100.0))
    g = evaluate(cand, base, PROFILE)
    assert g.verdict == "failed"
    b = next(x for x in g.breaches if x["metric"] == "barge_in_stop_p95")
    assert b["baseline"] == 400.0 and b["candidate"] == 1100.0 and b["delta"] == 700.0
    assert "barge_in_stop_p95" in g.markdown and "<!-- gauntlet-gate -->" in g.markdown


def test_gate_refuses_aborted_candidate():
    with pytest.raises(Ungatable):
        evaluate(side("c", 90), side("b", 90), PROFILE, candidate_status="aborted_budget")
