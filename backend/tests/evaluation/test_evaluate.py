"""Evidence-citing task scoring (TC-072, TC-073, SRS 18.4-18.5). The provider is stubbed: no test ever
calls a real model."""

import json

import httpx
import pytest

from gauntlet.referee.evaluate import (
    SYSTEM,
    Evaluator,
    TranscriptTurn,
    build_transcript,
    success_of,
    validate_steps,
)

CHECKLIST = [{"id": "g1", "text": "Agent confirms Friday"}, {"id": "g2", "text": "Agent confirms 7pm"}]
TRANSCRIPT = [
    TranscriptTurn(0, "caller", "Table for Friday at seven please"),
    TranscriptTurn(1, "agent", "Certainly, Friday at 7pm. What name shall I put it under?"),
]


def steps(*entries):
    return {"steps": list(entries)}


def met(step_id, idx, quote):
    return {"step_id": step_id, "met": True, "turn_index": idx, "quote": quote}


def stub(*payloads):
    """Answer each pass with the next payload; a payload may be a raw string (malformed output)."""
    seen = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = min(seen["n"], len(payloads) - 1)
        seen["n"] += 1
        body = payloads[i]
        content = body if isinstance(body, str) else json.dumps(body)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                         "usage": {"prompt_tokens": 100, "completion_tokens": 20}})

    return httpx.MockTransport(handler), seen


def evaluator(transport):
    return Evaluator("test-key", "https://provider.invalid/v1", "test-model", transport=transport)


def test_tc072_fabricated_quote_is_demoted():
    out = validate_steps(steps(met("g1", 1, "Friday at 7pm"), met("g2", 1, "I have booked your table")),
                         CHECKLIST, TRANSCRIPT)
    assert out[0]["met"] and out[0]["turn_index"] == 1
    assert not out[1]["met"] and out[1]["demoted"] == "citation_invalid" and out[1]["quote"] is None


def test_uncited_and_caller_cited_steps_cannot_count_as_success():
    out = validate_steps(steps({"step_id": "g1", "met": True, "turn_index": None, "quote": None},
                               met("g2", 0, "Table for Friday at seven please")), CHECKLIST, TRANSCRIPT)
    assert [s["met"] for s in out] == [False, False]
    assert out[0]["demoted"] == "uncited" and out[1]["demoted"] == "citation_invalid"


def test_quote_matching_ignores_whitespace_and_case_only():
    out = validate_steps(steps(met("g1", 1, "  friday   AT 7PM ")), CHECKLIST, TRANSCRIPT)
    assert out[0]["met"]


def test_success_criteria_modes():
    both = [{"met": True}, {"met": True}]
    one = [{"met": True}, {"met": False}]
    assert success_of(both, {"mode": "all_steps"}) and not success_of(one, {"mode": "all_steps"})
    assert success_of(one, {"mode": "minimum_steps", "minimum_steps": 1})
    assert not success_of(one, {"mode": "minimum_steps", "minimum_steps": 2})


def test_build_transcript_interleaves_and_caps_length():
    rows = [{"idx": i, "caller_text": f"c{i}", "agent_text": f"a{i}"} for i in range(30)]
    t = build_transcript(rows)
    assert len(t) == 40 and t[0].speaker in ("caller", "agent")
    assert [x.speaker for x in t[-2:]] == ["caller", "agent"]
    assert all(t[i].index < t[i + 1].index for i in range(len(t) - 1))


async def test_two_agreeing_passes_score_the_call():
    transport, seen = stub(steps(met("g1", 1, "Friday at 7pm"), met("g2", 1, "7pm")))
    v = await evaluator(transport).evaluate(CHECKLIST, TRANSCRIPT, {"mode": "all_steps"})
    assert v.status == "scored" and v.task_success is True and v.agreement == 1.0
    assert seen["n"] == 2 and v.prompt_tokens == 200


async def test_tc073_disagreement_becomes_needs_review():
    transport, _ = stub(steps(met("g1", 1, "Friday at 7pm"), met("g2", 1, "7pm")),
                        steps(met("g1", 1, "Friday at 7pm"), {"step_id": "g2", "met": False}))
    v = await evaluator(transport).evaluate(CHECKLIST, TRANSCRIPT, None)
    assert v.status == "needs_review" and v.needs_review and v.task_success is None and v.agreement == 0.5


async def test_malformed_output_is_repaired_once_then_scored():
    transport, seen = stub("not json at all", steps(met("g1", 1, "Friday at 7pm"), met("g2", 1, "7pm")))
    v = await evaluator(transport).evaluate(CHECKLIST, TRANSCRIPT, None)
    assert v.status in ("scored", "needs_review") and seen["n"] >= 3


async def test_two_malformed_outputs_fail_scoring_rather_than_guessing():
    transport, _ = stub("garbage")
    v = await evaluator(transport).evaluate(CHECKLIST, TRANSCRIPT, None)
    assert v.status == "scoring_failed" and v.task_success is None and v.steps == []


async def test_a_transcript_without_agent_speech_is_never_scored():
    transport, seen = stub(steps(met("g1", 1, "anything")))
    v = await evaluator(transport).evaluate(CHECKLIST, [TranscriptTurn(0, "caller", "hello")], None)
    assert v.status == "scoring_failed" and seen["n"] == 0


async def test_transcript_is_sent_as_delimited_data_with_no_metrics(monkeypatch):
    """SRS-SEC-006: the judge sees the checklist and the transcript, never the run's purpose or numbers."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(steps(met("g1", 1, "Friday at 7pm")))}}]})

    v = await evaluator(httpx.MockTransport(handler)).evaluate(CHECKLIST, TRANSCRIPT, None)
    user = captured["body"]["messages"][1]["content"]
    assert "<transcript>" in user and "</transcript>" in user
    assert "latency" not in user and "threshold" not in user and "readiness" not in user
    assert captured["body"]["messages"][0]["content"] == SYSTEM
    assert captured["body"]["temperature"] == 0.2 and v.model == "test-model"


@pytest.mark.parametrize("bad", [{"nope": []}, [], "text", {"steps": "no"}])
def test_malformed_shapes_raise_rather_than_pass_silently(bad):
    with pytest.raises(ValueError):
        validate_steps(bad, CHECKLIST, TRANSCRIPT)
