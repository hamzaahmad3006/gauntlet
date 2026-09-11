"""Suite validation and hashing, cost arithmetic, seed derivation (TC-020..023, TC-080..082, TC-034)."""

import pytest

from gauntlet.common import seeds
from gauntlet.cost.calculator import Pricing, PriceEntry, RigCounters, SessionShape, estimate_target_cost, rig_cost
from gauntlet.suites.loader import (
    SuiteValidationError,
    bundled_conditions,
    bundled_suite,
    load_suite_text,
    suite_hash,
)


def test_tc021_bundled_suite_is_valid_and_complete():
    s = bundled_suite()
    tags = {sc["coverage_tag"] for sc in s.scenarios}
    assert len(s.scenarios) >= 6 and len(s.personas) >= 4
    assert tags == {"happy_path", "edge_case", "adversarial", "out_of_scope"}
    assert set(bundled_conditions()) == {"clean", "mobile", "hostile", "turn_taking"}


def test_tc020_invalid_scenario_reports_line_and_column():
    text = """key: broken
scenarios:
  - key: s1
    coverage_tag: happy_path
    objective: x
    goal_checklist: []
    opening_utterance: hi
    fallback_lines: [a, b]
personas:
  - {key: p1, voice_id: v, speech_rate: 1.0, patience_s: 5}
"""
    with pytest.raises(SuiteValidationError) as e:
        load_suite_text(text)
    assert e.value.line == 6 and "goal_checklist" in e.value.pointer


def test_tc023_hash_is_canonical():
    s = bundled_suite()
    reordered = dict(reversed(list(s.document.items())))
    assert suite_hash(reordered) == s.version_hash
    changed = dict(s.document, name="different")
    assert suite_hash(changed) != s.version_hash


def test_seed_derivation_is_stable_and_63_bit():
    a = seeds.call_seed(42, "book_table_basic", "calm_standard", 0)
    assert a == seeds.call_seed(42, "book_table_basic", "calm_standard", 0)
    assert a != seeds.call_seed(42, "book_table_basic", "calm_standard", 1)
    assert 0 <= a < 2**63
    assert seeds.rng(a, "x").random() == seeds.rng(a, "x").random()


def test_tc080_rig_cost_recomputes_exactly():
    pricing = Pricing({
        "caller_llm": {"prompt_tokens": PriceEntry(0.05, "per_1k_tokens"), "completion_tokens": PriceEntry(0.08, "per_1k_tokens")},
        "caller_tts": {"characters": PriceEntry(0.30, "per_1k_characters")},
        "referee_stt": {"audio_seconds": PriceEntry(0.02, "per_minute")},
        "media": {"participant_minutes": PriceEntry(0.001, "per_minute")},
    })
    c = RigCounters(llm_prompt_tokens=10_000, llm_completion_tokens=2_000, tts_characters=5_000,
                    stt_audio_seconds=600, media_participant_minutes=20)
    r1, r2 = rig_cost(c, pricing), rig_cost(RigCounters(**c.as_dict()), pricing)
    assert r1 == r2
    assert r1["total_usd"] == round(0.5 + 0.16 + 1.5 + 0.2 + 0.02, 6)


def test_unpriced_provider_cannot_bypass_ceiling():
    r = rig_cost(RigCounters(llm_prompt_tokens=100), Pricing({}, unknown_unit_cost_usd=0.01))
    assert r["total_usd"] > 0 and r["flags"] == ["pricing_not_configured"]


def test_tc081_no_declaration_no_estimate():
    shape = SessionShape(30, 20, 400, 300)
    assert estimate_target_cost(shape, None) is None
    est = estimate_target_cost(shape, {"llm": {"prompt_price_per_1k_tokens": 0.1, "completion_price_per_1k_tokens": 0.2}})
    assert est["undeclared_components"] == ["tts", "stt"] and "estimated" in est["label"]
