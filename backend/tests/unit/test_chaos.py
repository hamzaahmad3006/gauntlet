"""Chaos engine: achieved vs configured, determinism, safety limits (TC-050..054, TC-034)."""

import numpy as np
import pytest

from gauntlet.media.audio import FRAME_NS, FRAME_SAMPLES, tone
from gauntlet.media.chaos import ChaosParams, ChaosPipeline, ConditionError
from gauntlet.suites.loader import SuiteValidationError, load_condition_profiles


def drive(params: ChaosParams, seed: int, n: int = 1000, voiced: bool = True):
    pipe = ChaosPipeline(params, seed)
    frame = tone(440, 20, -20)[:FRAME_SAMPLES]
    pipe.begin_utterance(frame)
    out = [pipe.process(frame, i * FRAME_NS, voiced) for i in range(n)]
    return pipe, out


def test_tc051_achieved_loss_within_one_point():
    pipe, _ = drive(ChaosParams(loss_probability=0.05), seed=7, n=10_000)
    achieved = pipe.stats.achieved(pipe.params)
    assert abs(achieved["achieved_loss_rate"] - 0.05) <= 0.01


def test_tc034_identical_seed_identical_schedule():
    p = ChaosParams(loss_probability=0.08, burst_length=3, jitter_mean_ms=40, jitter_stddev_ms=20, jitter_max_ms=160)
    _, a = drive(p, seed=123, n=500)
    _, b = drive(p, seed=123, n=500)
    assert [(r, s) for _, r, s in a] == [(r, s) for _, r, s in b]
    _, c = drive(p, seed=124, n=500)
    assert [(r, s) for _, r, s in a] != [(r, s) for _, r, s in c]


def test_stages_draw_from_independent_streams():
    base = ChaosParams(loss_probability=0.05)
    with_jitter = ChaosParams(loss_probability=0.05, jitter_mean_ms=30, jitter_stddev_ms=10, jitter_max_ms=100)
    _, a = drive(base, seed=9, n=800)
    _, b = drive(with_jitter, seed=9, n=800)
    assert [s for _, _, s in a] == [s for _, _, s in b]  # enabling jitter never shifts the loss schedule


def test_tc052_jitter_distribution_reported():
    pipe, out = drive(ChaosParams(jitter_mean_ms=40, jitter_stddev_ms=20, jitter_max_ms=160), seed=3, n=2000)
    a = pipe.stats.achieved(pipe.params)
    assert 35 < a["achieved_jitter_mean_ms"] < 45
    assert a["achieved_jitter_max_ms"] <= 160
    assert all(0 <= (rel - i * FRAME_NS) <= 160 * 1_000_000 for i, (_, rel, _) in enumerate(out))


def test_tc054_fixed_delay_applied_to_release_time():
    _, out = drive(ChaosParams(delay_ms=300), seed=1, n=10)
    assert all(rel - i * FRAME_NS == 300_000_000 for i, (_, rel, _) in enumerate(out))


def test_tc053_achieved_snr_close_to_configured():
    pipe, _ = drive(ChaosParams(noise_bed="cafe", snr_db=15), seed=5, n=400)
    a = pipe.stats.achieved(pipe.params)
    assert abs(a["achieved_snr_db"] - 15) <= 2.0


def test_substituted_frames_fade_instead_of_click():
    pipe, out = drive(ChaosParams(loss_probability=0.2, burst_length=1), seed=11, n=300)
    lost = [f for f, _, s in out if s]
    assert lost
    for f in lost:
        assert np.abs(f[40:-40]).max() == 0  # body is silence, edges carry only the fades


def test_tc050_profile_over_ceiling_rejected():
    with pytest.raises(ConditionError) as e:
        ChaosParams.from_profile({"frame_loss": {"loss_probability": 0.5}})
    assert e.value.parameter == "loss_probability"
    with pytest.raises(SuiteValidationError) as e2:
        load_condition_profiles("profiles:\n  bad:\n    frame_loss: {loss_probability: 0.5}\n")
    assert "loss_probability" in str(e2.value) and e2.value.line == 3
