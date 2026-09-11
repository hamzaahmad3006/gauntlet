"""Probe accuracy against synthetic fixtures with known onset/offset (TC-060)."""

import numpy as np

from gauntlet.media.audio import FRAME_NS, FRAME_SAMPLES, SAMPLE_NS, frames_of, silence_ms, tone
from gauntlet.media.probe import PlayoutClock, Probe


def run_probe(pcm: np.ndarray, t0: int = 0) -> Probe:
    p = Probe()
    for i, f in enumerate(frames_of(pcm)):
        p.process(f, t0 + i * FRAME_NS)
    p.flush()
    return p


def test_tc060_onset_and_offset_within_budget_across_subframe_positions():
    worst = 0.0
    for lead_ms in (1000.0, 1003.1, 1007.9, 1012.5, 1019.6):
        pcm = np.concatenate([silence_ms(lead_ms), tone(1000, 600, -18), silence_ms(1200)])
        p = run_probe(pcm)
        onsets = [e for e in p.events if e.kind == "speech_onset"]
        offsets = [e for e in p.events if e.kind == "speech_offset"]
        assert len(onsets) == 1 and len(offsets) == 1
        true_on = int(round(len(silence_ms(lead_ms)) * SAMPLE_NS))
        true_off = true_on + int(round(len(tone(1000, 600, -18)) * SAMPLE_NS))
        worst = max(worst, abs(onsets[0].t_ns - true_on) / 1e6, abs(offsets[0].t_ns - true_off) / 1e6)
    assert worst < 2.0, f"worst error {worst:.3f} ms"  # TARGET under 30 ms; sub-frame gets ~1 ms


def test_noisy_floor_adapts_and_detects_speech():
    rng = np.random.default_rng(1)
    noise = (rng.standard_normal(16000 * 4) * 32768 * 10 ** (-55 / 20)).astype(np.int16)
    speech = tone(300, 800, -20)
    pcm = noise.copy()
    pcm[32000 : 32000 + len(speech)] += speech
    p = run_probe(pcm)
    onsets = [e for e in p.events if e.kind == "speech_onset"]
    assert len(onsets) == 1
    assert abs(onsets[0].t_ns - 2 * 1_000_000_000) / 1e6 < 5
    assert "floor_fallback" not in p.flags


def test_short_click_is_not_speech():
    pcm = np.concatenate([silence_ms(500), tone(1000, 30, -10), silence_ms(1000)])
    assert [e for e in run_probe(pcm).events if e.kind == "speech_onset"] == []


def test_continuous_loud_channel_flags_floor_fallback():
    pcm = tone(200, 5000, -20)
    p = run_probe(pcm)
    assert "floor_fallback" in p.flags


def test_offset_is_not_ended_by_long_speech():
    pcm = np.concatenate([silence_ms(500), tone(400, 6000, -20), silence_ms(1000)])
    p = run_probe(pcm)
    assert [e.kind for e in p.events] == ["speech_onset", "speech_offset"]


def test_playout_clock_spreads_bursts_and_drains_in_silence():
    clock = PlayoutClock()
    t = [clock.stamp(0, quiet=False) for _ in range(5)]  # five speech frames arriving at once
    assert t == [0, FRAME_NS, 2 * FRAME_NS, 3 * FRAME_NS, 4 * FRAME_NS]
    later = 5 * FRAME_NS
    q = [clock.stamp(later, quiet=True) for _ in range(3)]
    assert q[0] == later and q[1] == later + FRAME_NS // 2
    assert FRAME_SAMPLES == 320
