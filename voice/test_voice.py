"""Tests for the parts of Tomi that run without LiveKit: call states, keypad, caller recognition and the mock backend.

Run from the repository root:  python -m pytest voice
"""

import asyncio

import pytest

from backend_client import MockBackend
from call_controller import CallController, CallState, InvalidTransition, Keypad, language_code


def test_language_code_accepts_names_and_codes():
    assert language_code("Hausa") == "ha"
    assert language_code("yo") == "yo"
    assert language_code("Pidgin") == "en"
    assert language_code(None, default="") == ""


def test_known_caller_goes_straight_to_the_conversation():
    call = CallController(call_id="c-1", direction="inbound")
    call.to(CallState.ANSWERED)
    call.patient_id = "p-zainab"
    call.to(CallState.VERIFIED, "caller's number")
    call.to(CallState.LISTENING)
    call.to(CallState.SAFETY_AND_ACTION)
    call.to(CallState.SPEAKING)
    call.to(CallState.LISTENING)
    call.to(CallState.COMPLETED)
    assert call.outcome() == "completed"
    assert [entry["state"] for entry in call.log][:2] == ["answered", "verified"]


def test_unknown_caller_chooses_a_language_then_hears_about_careloop():
    call = CallController(call_id="c-1", direction="inbound")
    call.to(CallState.ANSWERED)
    with pytest.raises(InvalidTransition):
        call.to(CallState.LISTENING)  # never straight into a conversation without the menu or a known number
    call.to(CallState.MENU)
    assert call.choose_language("2") == "yo"
    call.to(CallState.LISTENING, "unknown caller")
    call.to(CallState.SAFETY_AND_ACTION)
    call.to(CallState.SPEAKING)
    call.to(CallState.COMPLETED)
    assert not call.verified and call.outcome() == "unknown_caller"


def test_wrong_menu_key_counts_as_a_repeat():
    call = CallController(call_id="c-1", direction="inbound")
    assert call.choose_language("9") is None
    assert call.menu_repeats == 1
    assert call.menu_timed_out() is False
    assert call.menu_timed_out() is True


def test_escalation_is_reachable_from_any_state():
    call = CallController(call_id="c-1", direction="browser")
    call.to(CallState.ANSWERED)
    call.to(CallState.VERIFIED)
    call.patient_id = "p-zainab"
    call.to(CallState.LISTENING)
    call.to(CallState.SAFETY_AND_ACTION)
    call.to(CallState.ESCALATED, "possible_chest_pain")
    assert call.escalated and call.outcome() == "escalated"


def test_keypad_collects_digits():
    async def run():
        keypad = Keypad()
        for digit in "1*12#":
            keypad.press(digit)
        first = await keypad.digit(1)
        return first, await keypad.digits(4, first_timeout=1, between_timeout=0.1)

    assert asyncio.run(run()) == ("1", "12")


def test_keypad_times_out():
    assert asyncio.run(Keypad().digit(0.05)) is None


def test_mock_knows_callers_by_number():
    async def run():
        backend = MockBackend()
        known = await backend.start_call(direction="inbound", phone_e164="+2348000000101", patient_id=None)
        unknown = await backend.start_call(direction="inbound", phone_e164="+2348000000999", patient_id=None)
        return known, unknown

    known, unknown = asyncio.run(run())
    assert known["known"] is True and known["patient_id"] == "p-zainab" and known["language"] == "Hausa"
    assert unknown["known"] is False and unknown["patient_id"] is None and unknown["language"] is None


def test_mock_safety_check_escalates_red_flags():
    async def run():
        backend = MockBackend()
        calm = await backend.check_turn(call_id="c-1", patient_id="p-zainab", text="I took the morning one", language="en")
        flag = await backend.check_turn(call_id="c-1", patient_id="p-zainab", text="My chest hurts and I can't breathe", language="en")
        return calm, flag, backend.events

    calm, flag, events = asyncio.run(run())
    assert calm == {"action": "continue"}
    assert flag["action"] == "escalate" and flag["escalation"]["rule_id"] == "possible_chest_pain"
    assert events[0]["type"] == "escalation_opened"


def test_mock_context_matches_the_frontend_sample_patient():
    context = MockBackend()._context("p-zainab")
    assert context["patient"]["language"] == "Hausa"
    assert context["consent"]["voice"] is True
    assert {task["id"] for task in context["tasks"]} == {"t-z1", "t-z3", "t-z4"}


def test_unclear_transcripts_are_spotted():
    from call_controller import transcript_unclear
    assert all(transcript_unclear(text) for text in ["", "mm... ba...", "hmm", "uh uh"])
    assert not any(transcript_unclear(text) for text in ["Eh", "Yes", "I took it", "Na sha", "Rara"])


def test_every_language_has_every_line():
    import json
    from pathlib import Path
    lines = json.loads((Path(__file__).parent / "prompts" / "lines.json").read_text(encoding="utf-8"))
    keys = set(lines["en"])
    assert {"not_clear", "handover"} <= keys
    assert all(set(lines[code]) == keys for code in ("ha", "yo", "ig"))
