"""Interval arithmetic and aggregation (TC-061, TC-062, TC-063, TC-064)."""

from hypothesis import given
from hypothesis import strategies as st

from gauntlet.metrics.aggregate import CallSummary, aggregate, nearest_rank
from gauntlet.metrics.compute import (
    AgentWindow,
    Interruption,
    TurnRecord,
    call_metrics,
    classify_interruption,
    intersection_ns,
    latency,
    merge,
    total_ns,
)

MS = 1_000_000


def test_tc063_talkover_known_overlap():
    caller = [(0, 2000 * MS), (5000 * MS, 6000 * MS)]
    agent = [(1500 * MS, 4000 * MS)]
    assert intersection_ns(caller, agent) == 500 * MS


def test_tc064_dead_air_one_three_second_gap_in_thirty_seconds():
    caller = [(0, 5000 * MS)]
    agent = [(8000 * MS, 30000 * MS)]  # agent answers 3 s after the caller's last word
    windows = [AgentWindow(5000 * MS, 30000 * MS)]
    m = call_metrics(caller, agent, windows)
    assert m.dead_air_ratio == 10.0


def test_caller_think_time_is_not_dead_air():
    caller = [(0, 2000 * MS), (9000 * MS, 10000 * MS)]
    agent = [(2500 * MS, 5000 * MS), (10500 * MS, 12000 * MS)]
    windows = [AgentWindow(2000 * MS, 9000 * MS), AgentWindow(10000 * MS, 12000 * MS)]
    m = call_metrics(caller, agent, windows)
    assert m.dead_air_ms == 0.0  # the 4 s after the agent finished was the caller's think time


def test_tc062_non_yield_censored_at_2000():
    agent = [(1000 * MS, 9000 * MS)]
    i = classify_interruption(Interruption(1, 800, onset_ns=2000 * MS), agent)
    assert i.status == "applied" and i.no_yield and i.barge_stop_ms == 2000.0
    y = classify_interruption(Interruption(1, 800, onset_ns=2000 * MS), [(1000 * MS, 2350 * MS)])
    assert not y.no_yield and y.barge_stop_ms == 350.0
    na = classify_interruption(Interruption(1, 800, onset_ns=5000 * MS), [(1000 * MS, 2350 * MS)])
    assert na.status == "not_applicable" and na.barge_stop_ms is None


def test_latency_premature_and_censored():
    t = TurnRecord(1, t_caller_last_sample_ns=1000 * MS, t_agent_first_audio_ns=1800 * MS,
                   t_caller_last_nominal_ns=900 * MS)
    latency(t)
    assert t.latency_ms == 800.0 and t.raw_latency_ms == 900.0
    p = TurnRecord(2, t_caller_last_sample_ns=1000 * MS, t_agent_first_audio_ns=700 * MS)
    latency(p)
    assert p.premature and p.latency_ms is None


def test_tc061_nearest_rank_returns_observed_values():
    vals = [float(v) for v in range(1, 101)]
    assert nearest_rank(vals, 95) == 95.0
    assert nearest_rank(vals, 50) == 50.0
    assert nearest_rank([3.0], 99) == 3.0
    assert nearest_rank([], 50) is None


def test_aggregate_excludes_errored_from_percentiles_but_counts_completion():
    calls = [CallSummary("completed", turn_latencies=[500.0, 700.0], first_turn_latency=500.0) for _ in range(19)]
    calls.append(CallSummary("errored", turn_latencies=[99999.0]))
    out = aggregate(calls)
    assert out["response_latency_p99"].value == 700.0
    assert out["call_completion_rate"].value == 95.0
    assert out["session_error_rate"].value == 5.0


def test_zero_successes_cost_per_success_undefined():
    calls = [CallSummary("failed", scored=True, task_success=False, est_target_cost_usd=0.02) for _ in range(3)]
    out = aggregate(calls)
    assert out["est_cost_per_successful_session"].value is None
    assert "undefined_no_successful_sessions" in out["est_cost_per_successful_session"].flags


interval = st.tuples(st.integers(0, 10_000), st.integers(1, 2_000)).map(lambda t: (t[0], t[0] + t[1]))


@given(st.lists(interval, max_size=30))
def test_property_merge_is_idempotent_and_total_bounded(xs):
    m = merge(xs)
    assert merge(m) == m
    assert total_ns(xs) <= sum(e - s for s, e in xs)
    assert all(m[i][1] < m[i + 1][0] for i in range(len(m) - 1))


@given(st.lists(interval, max_size=20), st.lists(interval, max_size=20))
def test_property_intersection_symmetric_and_bounded(a, b):
    x = intersection_ns(a, b)
    assert x == intersection_ns(b, a)
    assert x <= min(total_ns(a), total_ns(b))
