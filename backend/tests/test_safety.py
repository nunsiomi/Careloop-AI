# backend/tests/test_safety.py
# Section 17 "Red flags": positive, negative, negated and indirect phrases per language, and uncertain speech.
# The rules are a draft until the clinical mentor signs docs/clinical-safety-review.md.
from unittest.mock import AsyncMock, patch

import pytest

from app.agents import barrier, escalation
from app.safety import number_check, rules


@pytest.mark.parametrize("text, rule_id", [
    ("My chest hurts", "possible_chest_pain"),
    ("there is pressure in my chest since morning", "possible_chest_pain"),
    ("I cannot breathe properly", "possible_breathing_problem"),
    ("I passed out in the kitchen", "possible_fainting"),
    ("her face is drooping on one side", "possible_stroke"),
    ("I have been vomiting blood", "possible_heavy_bleeding"),
    ("I want to end my life", "possible_self_harm"),
    ("Ƙirjina yana ciwo, kuma numfashi yana min wuya", "possible_chest_pain"),   # Hausa with hooked letters
    ("kirjina yana ciwo", "possible_chest_pain"),                              # Hausa typed without them
    ("Àyà mi ń dùn", "possible_chest_pain"),                                   # Yoruba with tone marks
    ("aya mi n dun", "possible_chest_pain"),                                   # Yoruba typed without them
    ("enweghi m ike iku ume", "possible_breathing_problem"),                   # Igbo
    ("I took the medicine but my chest hurts", "possible_chest_pain"),          # mixed with a routine report
])
def test_red_flags_escalate(text, rule_id):
    result = rules.check(text)
    assert result.action == "escalate" and result.rule_id == rule_id and result.severity == "red"


@pytest.mark.parametrize("text", [
    "I took my morning tablet", "I took my blood test today", "I feel fit and well", "The pharmacy is out of stock",
    "Can I change my visit?", "my wife is fine", "Na sha maganin safe", "Mo ti lo oogun naa",
])
def test_everyday_messages_do_not_escalate(text):
    assert rules.check(text).action == "continue"


@pytest.mark.parametrize("text", ["I have no chest pain today", "I do not have any chest pain", "Ba ni da ciwon kirji"])
def test_negated_mentions_are_checked_not_ignored(text):
    result = rules.check(text)
    assert result.action == "confirm" and result.rule_id == "possible_chest_pain"
    assert "nearest hospital" in result.confirm_line()


def test_not_breathing_is_never_read_as_a_negation():
    assert rules.check("he is not breathing").action == "escalate"


def test_unclear_speech_with_a_danger_word_takes_the_safe_path():
    assert rules.check("mm... chest ... ba", confidence=0.4).action == "escalate"
    assert rules.check("mm... ba...", confidence=0.31).action == "clarify"
    assert rules.check("mm... ba...", confidence=0.9).action == "continue"


def test_rules_file_is_marked_as_a_draft_until_signed_off():
    loaded = rules.load()
    assert loaded["approved_by"] is None
    assert all(rule["checked"]["en"] for rule in loaded["rules"])
    assert not any(rule["checked"]["ha"] for rule in loaded["rules"])


# ----- number check

def test_number_check_blocks_new_or_changed_numbers():
    source = ["Amlodipine 5 mg tablet, one tablet every evening at 20:00 for 30 days"]
    assert number_check.check("Take one tablet at 8pm", source).passed
    assert number_check.check("Take 2 tablets at 20:00", source).unexpected == ["2"]
    assert number_check.check("Your next dose is at 21:00", source).unexpected == ["21:00"]
    assert number_check.check("Thank you for telling me.", source).passed


# ----- Barrier Resolution Agent

@pytest.mark.asyncio
async def test_barrier_options_come_only_from_approved_resources():
    result = await barrier.run({"type": "stock_out", "facility": "Kestrel General Hospital", "attempts": 1, "care_team_phone": "+2348000000000"})
    assert result["type"] == "stock" and not result["escalate"]
    assert {option["name"] for option in result["options"]} == {"Allen Junction Pharmacy", "Wuse Market Pharmacy"}
    assert all("not guaranteed" in option["note"].lower() for option in result["options"])


@pytest.mark.asyncio
async def test_barrier_falls_back_to_the_care_team_and_escalates_after_two_tries():
    result = await barrier.run({"type": "transport", "facility": "Ibis Family Clinic", "attempts": 2, "care_team_phone": "+2348000000000"})
    assert [option["name"] for option in result["options"]] == ["Your care team"]
    assert result["escalate"] is True


# ----- Escalation Summary Agent

ESCALATION = {"channel": "voice", "rule_label": "Possible chest pain", "original_text": "Ƙirjina yana ciwo", "english_text": "My chest hurts",
              "confidence": 0.71, "severity": "red"}


def test_rule_written_brief_is_factual():
    brief = escalation.build_brief(ESCALATION, ["stock barrier open since 02 Nov"], "09:24")
    assert '"Ƙirjina yana ciwo"' in brief and "My chest hurts" in brief and "0.71" in brief
    assert not escalation.FORBIDDEN.search(brief)


@pytest.mark.asyncio
@pytest.mark.parametrize("model_brief, accepted", [
    ('At 09:24 the patient said "Ƙirjina yana ciwo" (my chest hurts). Rule: possible chest pain. Open: stock barrier.', True),
    ('The patient said "Ƙirjina yana ciwo", likely a heart attack.', False),        # names a diagnosis
    ('The patient said "Ƙirjina yana ciwo". An ambulance is on the way.', False),   # implies help was sent
    ('The patient said "Ƙirjina yana ciwo" 3 times since 07:00.', False),           # numbers not in the facts
    ("The patient reported chest pain.", False),                                    # does not quote the patient
])
async def test_model_brief_is_kept_only_if_it_passes_every_check(model_brief, accepted):
    with patch("app.agents.escalation.ask_groq_json", AsyncMock(return_value={"brief": model_brief})):
        result = await escalation.run({"escalation": ESCALATION, "open_items": ["stock barrier open"], "when": "09:24"})
    assert result["model_used"] is accepted
    assert result["brief"] == (model_brief if accepted else escalation.build_brief(ESCALATION, ["stock barrier open"], "09:24"))
