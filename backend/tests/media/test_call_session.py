"""A full synthetic call over a real loopback WebSocket against the synthetic agent fixture.

No external provider: scripted caller lines, local synthesiser, no referee. The fixture's latency and
yield behaviour are programmed, so the measured values have a known expectation.
"""

import asyncio
import socket

import pytest

from fixtures.calibration_target.server import serve
from gauntlet.caller.adapters.websocket_pcm import WebSocketPCMTransport
from gauntlet.caller.brain import CallerBrain
from gauntlet.caller.interrupts import schedule
from gauntlet.caller.session import CallPlan, CallSession, SessionConfig
from gauntlet.caller.tts import SpeechSynth
from gauntlet.media.chaos import ChaosParams
from gauntlet.suites.loader import bundled_suite

pytestmark = pytest.mark.realtime


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def one_call(tmp_path, query: str, chaos: ChaosParams, scenario_key: str = "book_table_basic",
                   interruptions: int = 0):
    port = free_port()
    server = await serve("127.0.0.1", port)
    try:
        suite = bundled_suite()
        sc = dict(suite.scenario(scenario_key))
        sc["timing"] = {"max_turns": 6, "max_duration_s": 60, "turn_timeout_ms": 5000}
        persona = suite.persona("calm_standard")
        plan = CallPlan("call-test", 42, sc, persona, chaos,
                        schedule(42, interruptions, (300, 600), 6) if interruptions else [])
        session = CallSession(plan, WebSocketPCMTransport(f"ws://127.0.0.1:{port}/?{query}"),
                              SpeechSynth(cache_dir=tmp_path), CallerBrain(),
                              config=SessionConfig(greeting_wait_ms=1500))
        return await asyncio.wait_for(session.run(), 90)
    finally:
        server.close()


async def test_full_call_measures_programmed_latency(tmp_path):
    out = await one_call(tmp_path, "mode=agent&endpoint_ms=500&delay_ms=300&greeting=1", ChaosParams())
    assert out.ended == "conversation", (out.reason_code, out.events[-5:])
    lat = [t.latency_ms for t in out.turns if t.latency_ms is not None]
    assert len(lat) >= 4
    # fixture answers endpoint (500) + processing (300) after the caller's last voiced sample
    assert all(760 <= v <= 900 for v in lat), lat
    assert out.turns[0].idx == 0 and out.turns[0].t_agent_first_audio_ns is not None  # greeting captured
    assert out.metrics is not None and out.metrics.talkover_ms is not None
    assert out.wav and out.peaks


async def test_barge_in_yield_is_measured(tmp_path):
    out = await one_call(tmp_path, "mode=agent&endpoint_ms=400&delay_ms=200&yield_ms=250",
                         ChaosParams(interruptions_per_call=2), interruptions=2)
    applied = [i for i in out.interruptions if i.status == "applied"]
    assert applied, [(i.status, i.turn_idx) for i in out.interruptions]
    # the fixture's probe needs ~60 ms to confirm onset, then stops 250 ms later
    assert all(200 <= i.barge_stop_ms <= 450 for i in applied), [i.barge_stop_ms for i in applied]
    assert not any(i.no_yield for i in applied)


async def test_injected_delay_is_excluded_from_attributed_latency(tmp_path):
    out = await one_call(tmp_path, "mode=agent&endpoint_ms=500&delay_ms=300", ChaosParams(delay_ms=300))
    turns = [t for t in out.turns if t.latency_ms is not None and t.raw_latency_ms is not None]
    assert turns
    for t in turns:
        assert 760 <= t.latency_ms <= 900, t.latency_ms  # attributed: unchanged by the injected delay
        assert 280 <= t.raw_latency_ms - t.latency_ms <= 330  # raw carries the 300 ms (TC-054)
