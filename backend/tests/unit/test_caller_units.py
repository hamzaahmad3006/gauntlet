"""Caller-side determinism and behaviour (TC-022, TC-041, TC-042, TC-043, TC-044, TC-055, TC-066, TC-071)."""

import asyncio

import numpy as np

from gauntlet.caller.brain import BrainContext, CallerBrain, ScriptedLines
from gauntlet.caller.interrupts import schedule
from gauntlet.caller.local_synth import babble
from gauntlet.caller.policies import join_with_pause, split_for_pause
from gauntlet.caller.tts import SpeechSynth
from gauntlet.media.audio import time_stretch, voiced_span
from gauntlet.referee.transcribe import independence
from gauntlet.suites.loader import bundled_suite


def test_tc043_interruption_schedule_is_byte_identical_for_a_seed():
    a = schedule(123456789, 3, (300, 1200), 12)
    b = schedule(123456789, 3, (300, 1200), 12)
    assert a == b and len(a) == 3
    assert schedule(123456790, 3, (300, 1200), 12) != a
    assert all(300 <= e["offset_ms"] <= 1200 for e in a)


def test_tc022_personas_produce_different_durations_for_identical_text():
    text = "I would like to book a table for four people on Friday evening."
    durations = {p["key"]: len(babble(text, p["voice_id"], p["speech_rate"])) for p in bundled_suite().personas}
    assert len(set(durations.values())) == len(durations), durations


def test_tc055_rate_changes_duration_measurably():
    pcm = babble("Saturday at eight for two people under the name Sara.", "v", 1.0)
    slow, fast = time_stretch(pcm, 0.8), time_stretch(pcm, 1.2)
    assert len(slow) > len(pcm) * 1.2 and len(fast) < len(pcm) * 0.9


def test_tc044_hesitation_lengthens_the_utterance_and_keeps_two_voiced_segments():
    text = "Hello I would like to book a table for Sunday lunch"
    a, b = split_for_pause(text)
    pa, pb = babble(a, "v"), babble(b, "v")
    plain = babble(text, "v")
    joined, segments = join_with_pause([pa, pb], 1200)
    assert len(joined) > len(plain) + 16000  # the 1.2 s pause is really in the audio
    assert len(segments) == 2 and segments[1][0] - segments[0][1] >= 1200 * 16


async def test_tc041_forced_timeout_uses_a_scripted_fallback_every_time():
    brain = CallerBrain(api_key="unused", base_url="http://127.0.0.1:9", timeout_ms=1)
    lines = ScriptedLines(["first line", "second line"])
    ctx = BrainContext("book a table", {}, [], "pursue", 1, 10)
    replies = [await brain.next_utterance(ctx, lines) for _ in range(2)]
    await brain.aclose()
    assert [r.text for r in replies] == ["first line", "second line"]
    assert all(r.fallback_used for r in replies)


async def test_tc042_repeated_utterance_is_served_from_cache(tmp_path):
    synth = SpeechSynth(cache_dir=tmp_path)
    first = await synth.synthesize("Friday at seven, for four, under Idris.", "voice-x", 1.0)
    second = await synth.synthesize("Friday at seven, for four, under Idris.", "voice-x", 1.0)
    assert not first.cached and second.cached
    assert np.array_equal(first.pcm, second.pcm)


def test_tc066_caller_last_voiced_sample_excludes_trailing_silence():
    pcm = np.concatenate([babble("the name is Sara", "v"), np.zeros(8000, dtype=np.int16)])
    start, end = voiced_span(pcm)
    assert end <= len(pcm) - 8000 + 160  # the half second of silence is not "still speaking"


def test_tc071_same_recogniser_family_warns():
    same = independence({"speechmatics-rt"}, {"stt": "Speechmatics enhanced"})
    assert same["independent"] is False and "Independence not satisfied" in same["warning"]
    diff = independence({"speechmatics-rt"}, {"stt": "deepgram nova-2"})
    assert diff["independent"] is True and diff["warning"] is None
    assert independence(set(), None)["independent"] is None


def test_scripted_lines_walk_in_order_and_report_exhaustion():
    lines = ScriptedLines(["a", "b"])
    assert [lines.next(), lines.exhausted, lines.next(), lines.exhausted] == ["a", False, "b", True]


def test_event_loop_friendly_local_synth():
    async def main():
        synth = SpeechSynth()
        return await asyncio.wait_for(synth.synthesize("hello there", "v", 1.0), 10)
    assert len(asyncio.run(main()).pcm) > 1600
