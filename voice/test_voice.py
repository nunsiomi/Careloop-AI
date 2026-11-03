"""Tests for the parts of Tomi that run without LiveKit: call states, keypad, PIN gate and the mock backend.

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


def test_inbound_happy_path():
    call = CallController(call_id="c-1", direction="inbound")
    call.to(CallState.ANSWERED)
    call.to(CallState.MENU)
    assert call.choose_language("1") == "ha"
    call.to(CallState.VERIFICATION_GATE)
    assert call.pin_result(True, "p-zainab") == "verified"
    call.to(CallState.LISTENING)
    call.to(CallState.SAFETY_AND_ACTION)
    call.to(CallState.SPEAKING)
    call.to(CallState.LISTENING)
    call.to(CallState.COMPLETED)
    assert call.outcome() == "completed"
    assert [entry["state"] for entry in call.log][:3] == ["answered", "menu", "verification_gate"]


def test_cannot_skip_the_pin():
    call = CallController(call_id="c-1", direction="inbound")
    call.to(CallState.ANSWERED)
    with pytest.raises(InvalidTransition):
        call.to(CallState.LISTENING)


def test_wrong_menu_key_counts_as_a_repeat():
    call = CallController(call_id="c-1", direction="inbound")
    assert call.choose_language("9") is None
    assert call.menu_repeats == 1
    assert call.menu_timed_out() is False
    assert call.menu_timed_out() is True


def test_pin_locks_when_backend_says_no_tries_left():
    call = CallController(call_id="c-1", direction="inbound")
    call.to(CallState.ANSWERED)
    call.to(CallState.VERIFICATION_GATE)
    assert call.pin_result(False, tries_left=2) == "retry"
    assert call.pin_result(False, tries_left=0) == "locked"
    assert call.state == CallState.UNVERIFIED
    assert call.outcome() == "unverified"


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


def test_mock_pin_does_not_reveal_unknown_numbers():
    async def run():
        backend = MockBackend()
        call = await backend.start_call(direction="inbound", phone_e164="+2348000000999", patient_id=None)
        unknown = await backend.verify_pin(call_id=call["id"], phone_e164="+2348000000999", pin="1234")
        wrong = await backend.verify_pin(call_id=call["id"], phone_e164="+2348000000101", pin="0000")
        right = await backend.verify_pin(call_id=call["id"], phone_e164="+2348000000101", pin="1234")
        return unknown, wrong, right

    unknown, wrong, right = asyncio.run(run())
    assert unknown.keys() == wrong.keys() == {"ok", "tries_left"}
    assert unknown["ok"] is False and wrong["ok"] is False
    assert right == {"ok": True, "patient_id": "p-zainab"}


def test_mock_pin_locks_after_five_wrong_tries():
    async def run():
        backend = MockBackend()
        results = [await backend.verify_pin(call_id="c-x", phone_e164="+2348000000101", pin="0000") for _ in range(5)]
        results.append(await backend.verify_pin(call_id="c-x", phone_e164="+2348000000101", pin="1234"))
        return results

    results = asyncio.run(run())
    assert [r["tries_left"] for r in results[:5]] == [4, 3, 2, 1, 0]
    assert results[5]["ok"] is False


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
