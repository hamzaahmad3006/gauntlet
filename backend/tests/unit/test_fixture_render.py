"""The bundled agent's output must be the reply audio sample for sample, however late the pacing loop wakes.
Indexing frames by the wall clock dropped and repeated samples on every late wake-up, which made the agent's
voice sound torn in the browser softphone and in call recordings."""

import random

import numpy as np

from fixtures.calibration_target.session import FixtureConfig, FixtureSession, _Track
from gauntlet.media.audio import FRAME_NS, FRAME_SAMPLES


async def _noop(_):
    return None


def test_reply_audio_is_contiguous_under_pacing_jitter():
    session = FixtureSession(FixtureConfig(mode="agent"), _noop, _noop)
    t = np.arange(16000 * 2)
    pcm = (8000 * np.sin(2 * np.pi * 440 * t / 16000)).astype(np.int16)
    t0 = 1_000_000_000
    session._track = _Track(pcm, t0, "reply")
    rng = random.Random(7)
    out = []
    for i in range(len(pcm) // FRAME_SAMPLES):
        target = t0 + i * FRAME_NS
        late = rng.randint(0, 9) * 1_000_000  # a Windows timer waking up to 9 ms late
        out.append(session._render(target + late, target))
    rendered = np.concatenate(out)
    assert np.array_equal(rendered, pcm[: len(rendered)])


def test_start_marker_reports_the_actual_send_instant():
    session = FixtureSession(FixtureConfig(mode="agent"), _noop, _noop)
    pcm = np.full(FRAME_SAMPLES * 5, 1000, dtype=np.int16)
    session._track = _Track(pcm, 2_000_000_000, "reply")
    session._render(2_000_000_000 + 4_000_000, 2_000_000_000)  # frame due at t, sent 4 ms late
    start = next(m for m in session._markers if m["kind"] == "response_start")
    assert start["t_ns"] == 2_004_000_000
