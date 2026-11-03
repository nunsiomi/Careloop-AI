"""Call state machine: verification gate, menu, keypad fallback, safe fallbacks (owner: Nunsi).

Pure Python with no LiveKit imports, so it can be unit tested. `tomi_agent.py` drives it.
States follow section 7.3 of the project documentation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class CallState(str, Enum):
    NEW = "new"
    RINGING = "ringing"
    ANSWERED = "answered"
    VERIFICATION_GATE = "verification_gate"
    VERIFIED = "verified"
    MENU = "menu"
    LISTENING = "listening"
    TRANSCRIPTION_REVIEW = "transcription_review"
    SAFETY_AND_ACTION = "safety_and_action"
    SPEAKING = "speaking"
    COMPLETED = "completed"
    # Any step can drop to one of these; each is logged and ends in a safe fallback.
    DISCONNECTED = "disconnected"
    UNCLEAR_INPUT = "unclear_input"
    PROVIDER_ERROR = "provider_error"
    UNVERIFIED = "unverified"
    OPT_OUT = "opt_out"
    ESCALATED = "escalated"


FALLBACK_STATES = {
    CallState.DISCONNECTED,
    CallState.UNCLEAR_INPUT,
    CallState.PROVIDER_ERROR,
    CallState.UNVERIFIED,
    CallState.OPT_OUT,
    CallState.ESCALATED,
}
END_STATES = {CallState.COMPLETED, CallState.DISCONNECTED, CallState.UNVERIFIED, CallState.OPT_OUT}

_NEXT = {
    CallState.NEW: {CallState.RINGING, CallState.ANSWERED},
    CallState.RINGING: {CallState.ANSWERED},
    # Browser voice skips the PIN: the patient already signed in to the app.
    CallState.ANSWERED: {CallState.MENU, CallState.VERIFICATION_GATE, CallState.VERIFIED},
    CallState.MENU: {CallState.VERIFICATION_GATE, CallState.LISTENING},
    CallState.VERIFICATION_GATE: {CallState.VERIFIED},
    CallState.VERIFIED: {CallState.LISTENING, CallState.SPEAKING, CallState.MENU},
    CallState.LISTENING: {CallState.TRANSCRIPTION_REVIEW, CallState.SAFETY_AND_ACTION, CallState.COMPLETED},
    CallState.TRANSCRIPTION_REVIEW: {CallState.SAFETY_AND_ACTION, CallState.LISTENING},
    CallState.SAFETY_AND_ACTION: {CallState.SPEAKING, CallState.LISTENING},
    CallState.SPEAKING: {CallState.LISTENING, CallState.COMPLETED},
    # After an escalation Tomi keeps the line open and repeats the emergency line.
    CallState.ESCALATED: {CallState.LISTENING, CallState.COMPLETED, CallState.DISCONNECTED},
    CallState.UNCLEAR_INPUT: {CallState.MENU, CallState.VERIFICATION_GATE, CallState.LISTENING},
    CallState.PROVIDER_ERROR: {CallState.COMPLETED, CallState.DISCONNECTED},
}

# Keypad language menu. Order matches the MVP language list in the frontend (shared/languages.js).
LANGUAGE_DIGITS = {"1": "ha", "2": "yo", "3": "ig", "4": "en"}
LANGUAGE_NAMES = {"ha": "Hausa", "yo": "Yoruba", "ig": "Igbo", "en": "English"}
NAME_TO_CODE = {name.lower(): code for code, name in LANGUAGE_NAMES.items()}

PIN_LENGTH = 4
MAX_PIN_TRIES = 5  # Same limit as PIN sign-in in the app (docs/api_shapes.md).
MAX_MENU_REPEATS = 3


class InvalidTransition(Exception):
    pass


def language_code(value: str | None, default: str = "en") -> str:
    """Accept 'ha' or 'Hausa' and return the code CareLoop uses for Spitch."""
    if not value:
        return default
    value = value.strip().lower()
    if value in LANGUAGE_NAMES:
        return value
    return NAME_TO_CODE.get(value, default)


def language_for_digit(digit: str) -> str | None:
    return LANGUAGE_DIGITS.get(digit)


@dataclass
class CallController:
    """Tracks one call's state and keeps a log the backend stores as the call record."""

    call_id: str
    direction: str  # outbound | inbound | browser
    state: CallState = CallState.NEW
    language: str | None = None
    patient_id: str | None = None
    pin_tries: int = 0
    menu_repeats: int = 0
    escalated: bool = False
    log: list[dict] = field(default_factory=list)

    def to(self, state: CallState, note: str | None = None) -> None:
        if state != self.state and state not in FALLBACK_STATES and state not in _NEXT.get(self.state, set()):
            raise InvalidTransition(f"{self.state.value} -> {state.value}")
        self.state = state
        if state == CallState.ESCALATED:
            self.escalated = True
        self.log.append({"state": state.value, "at": datetime.now(timezone.utc).isoformat(), "note": note})

    @property
    def verified(self) -> bool:
        return self.patient_id is not None

    @property
    def ended(self) -> bool:
        return self.state in END_STATES

    def choose_language(self, digit: str) -> str | None:
        """Returns the language for a menu digit, or None (and counts a repeat) for any other key."""
        code = language_for_digit(digit)
        if code:
            self.language = code
            self.menu_repeats = 0
        else:
            self.menu_repeats += 1
        return code

    def menu_timed_out(self) -> bool:
        """Counts a repeat after no key press. True when Tomi should stop repeating the menu."""
        self.menu_repeats += 1
        return self.menu_repeats >= MAX_MENU_REPEATS

    def pin_result(self, ok: bool, patient_id: str | None = None, tries_left: int | None = None) -> str:
        """Record a PIN check. Returns 'verified', 'retry' or 'locked'.

        The backend decides; `tries_left` from the backend wins over the local count, so the call and the
        app share one lock.
        """
        if ok and patient_id:
            self.patient_id = patient_id
            self.to(CallState.VERIFIED)
            return "verified"
        self.pin_tries += 1
        left = tries_left if tries_left is not None else MAX_PIN_TRIES - self.pin_tries
        if left <= 0:
            self.to(CallState.UNVERIFIED, "PIN tries used up")
            return "locked"
        return "retry"

    def outcome(self) -> str:
        if self.escalated:
            return "escalated"
        if self.state == CallState.UNVERIFIED:
            return "unverified"
        if not self.verified:
            return "not_reached"
        return "completed"


class Keypad:
    """Collects keypad (DTMF) presses from a phone call so the call flow can await them."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    def press(self, digit: str) -> None:
        self._queue.put_nowait(digit)

    def clear(self) -> None:
        while not self._queue.empty():
            self._queue.get_nowait()

    async def digit(self, timeout: float) -> str | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout)
        except asyncio.TimeoutError:
            return None

    async def digits(self, count: int, first_timeout: float, between_timeout: float = 6.0) -> str | None:
        """Wait for `count` digits. '#' ends early; '*' starts again. None if the caller stops typing."""
        typed = ""
        timeout = first_timeout
        while len(typed) < count:
            digit = await self.digit(timeout)
            if digit is None:
                return None if not typed else typed
            if digit == "#":
                break
            if digit == "*":
                typed = ""
                continue
            typed += digit
            timeout = between_timeout
        return typed
