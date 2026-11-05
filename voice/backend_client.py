"""How the Tomi worker talks to the CareLoop backend (owner: Nunsi, routes: Olamide).

The worker never touches the database. It calls FastAPI with a service token, and the backend decides
identity, consent, red flags and what gets recorded (project documentation, section 9).

`VOICE_USE_MOCKS=1` (the default until the backend exists) uses `MockBackend`, which holds the same sample
patient as the frontend mocks, so a call can be tested end to end with only LiveKit, Spitch and Groq keys.
Routes are listed in docs/api_shapes.md under "Voice worker".
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Protocol

import httpx

logger = logging.getLogger("tomi.backend")


class Backend(Protocol):
    async def start_call(self, *, direction: str, phone_e164: str | None, patient_id: str | None) -> dict: ...
    async def verify_pin(self, *, call_id: str, phone_e164: str | None, pin: str) -> dict: ...
    async def call_context(self, *, call_id: str, patient_id: str) -> dict: ...
    async def check_turn(self, *, call_id: str, patient_id: str, text: str, language: str, confidence: float | None = None) -> dict: ...
    async def log_turn(self, *, call_id: str, speaker: str, text: str, language: str) -> None: ...
    async def record_task_update(self, *, call_id: str, patient_id: str, task_id: str, status: str, patient_words: str) -> dict: ...
    async def report_problem(self, *, call_id: str, patient_id: str, kind: str, patient_words: str, task_id: str | None) -> dict: ...
    async def ask_care_team(self, *, call_id: str, patient_id: str, question: str) -> dict: ...
    async def end_call(self, *, call_id: str, outcome: str, log: list[dict]) -> None: ...


class HttpBackend:
    def __init__(self, base_url: str, token: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(8.0, connect=4.0),
        )

    async def _post(self, path: str, body: dict) -> dict:
        resp = await self._client.post(path, json=body)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    async def start_call(self, *, direction, phone_e164, patient_id):
        return (await self._post("/voice/calls", {"direction": direction, "phone_e164": phone_e164, "patient_id": patient_id}))["call"]

    async def verify_pin(self, *, call_id, phone_e164, pin):
        return await self._post(f"/voice/calls/{call_id}/verify-pin", {"phone_e164": phone_e164, "pin": pin})

    async def call_context(self, *, call_id, patient_id):
        resp = await self._client.get(f"/voice/calls/{call_id}/context")
        resp.raise_for_status()
        return resp.json()["context"]

    async def check_turn(self, *, call_id, patient_id, text, language, confidence=None):
        body = {"text": text, "language": language, **({"confidence": confidence} if confidence is not None else {})}
        return await self._post(f"/voice/calls/{call_id}/turns/check", body)

    async def log_turn(self, *, call_id, speaker, text, language):
        await self._post(f"/voice/calls/{call_id}/turns", {"speaker": speaker, "transcript": text, "language": language})

    async def record_task_update(self, *, call_id, patient_id, task_id, status, patient_words):
        return await self._post(f"/voice/calls/{call_id}/task-updates", {"task_id": task_id, "status": status, "original_text": patient_words})

    async def report_problem(self, *, call_id, patient_id, kind, patient_words, task_id):
        return await self._post(f"/voice/calls/{call_id}/barriers", {"type": kind, "original_text": patient_words, "task_id": task_id})

    async def ask_care_team(self, *, call_id, patient_id, question):
        return await self._post(f"/voice/calls/{call_id}/questions", {"original_text": question})

    async def end_call(self, *, call_id, outcome, log):
        await self._post(f"/voice/calls/{call_id}/end", {"outcome": outcome, "states": log})


def _at(days: int, hhmm: str) -> str:
    """Like `at()` in frontend/shared/mock-server.js: a time relative to today, in Lagos time."""
    lagos = timezone(timedelta(hours=1))
    hours, minutes = (int(part) for part in hhmm.split(":"))
    day = datetime.now(lagos).replace(hour=hours, minute=minutes, second=0, microsecond=0) + timedelta(days=days)
    return day.isoformat()


# Placeholder screen until Dorcas and the clinical mentor fill backend/app/safety/red_flags.json. English only:
# it will not catch a red flag said in Hausa, Yoruba or Igbo. The real check runs in the backend.
_MOCK_RED_FLAGS = {
    "possible_chest_pain": r"chest (pain|hurts?|tight)",
    "possible_breathing_problem": r"(can'?t|cannot|trouble|hard to) breath",
    "possible_fainting": r"faint|passed out|unconscious",
    "possible_heavy_bleeding": r"bleed(ing)? (a lot|heavily|won'?t stop)",
    "possible_self_harm": r"kill myself|end my life|hurt myself",
}


class MockBackend:
    """In-memory stand-in for the backend. Same people and plan as frontend/shared/mock-server.js."""

    PHONES = {"+2348000000101": "p-zainab"}
    PINS = {"p-zainab": "1234"}
    MAX_TRIES = 5

    def __init__(self) -> None:
        self.calls: dict[str, dict] = {}
        self.events: list[dict] = []
        self.pin_failures: dict[str, int] = {}
        # Your own phone, for test calls in and out: it then counts as Zainab's number (PIN 1234).
        if os.getenv("VOICE_TEST_PHONE"):
            self.PHONES = {**self.PHONES, os.environ["VOICE_TEST_PHONE"].replace(" ", ""): "p-zainab"}

    def _context(self, patient_id: str) -> dict:
        if patient_id != "p-zainab":
            raise KeyError(patient_id)
        return {
            "patient": {"id": "p-zainab", "first_name": "Zainab", "language": "Hausa", "timezone": "Africa/Lagos"},
            "consent": {"voice": True},
            "facility": "Kestrel General Hospital",
            "plan": {
                "status": "approved",
                "medications": [
                    {"name": "Amlodipine 5 mg tablet", "dose": "1 tablet", "frequency": "Every morning", "times": ["08:00"], "instructions": "Take with water"},
                    {"name": "Bisoprolol 5 mg tablet", "dose": "1 tablet", "frequency": "Every evening", "times": ["20:00"], "instructions": "Take with water"},
                ],
                "appointments": [{"what": "Cardiology follow-up", "where": "Heart Clinic, room 3", "starts_at": _at(2, "10:00")}],
                "tests": [{"name": "Kidney function blood test", "where": "Hospital laboratory", "due_at": _at(4, "09:00")}],
                "symptoms_to_watch": ["Chest pain", "Trouble breathing", "Fainting"],
            },
            "tasks": [
                {"id": "t-z1", "title": "Amlodipine 5 mg tablet", "detail": "1 tablet", "due_at": _at(0, "08:00"), "status": "patient_reported_done"},
                {"id": "t-z3", "title": "Bisoprolol 5 mg tablet", "detail": "1 tablet", "due_at": _at(0, "20:00"), "status": "pending"},
                {"id": "t-z4", "title": "Kidney function blood test", "detail": "Hospital laboratory", "due_at": _at(4, "09:00"), "status": "pending"},
            ],
            # Approved opening for this call, from the plan's templates. None lets Tomi open with a general check-in.
            "opening": None,
        }

    async def start_call(self, *, direction, phone_e164, patient_id):
        call = {"id": f"c-{uuid.uuid4().hex[:8]}", "direction": direction, "phone_e164": phone_e164, "patient_id": patient_id,
                "language": None, "turns": []}
        if direction == "outbound" and patient_id:
            call["language"] = self._context(patient_id)["patient"]["language"]
        self.calls[call["id"]] = call
        return {"id": call["id"], "language": call["language"]}

    async def verify_pin(self, *, call_id, phone_e164, pin):
        # The same answer for an unknown number and a wrong PIN, so a call never reveals who has an account.
        key = phone_e164 or "unknown"
        failures = self.pin_failures.get(key, 0)
        if failures >= self.MAX_TRIES:
            return {"ok": False, "tries_left": 0}
        # On an outgoing call the backend already knows whose PIN to expect.
        patient_id = self.calls.get(call_id, {}).get("patient_id") or self.PHONES.get(phone_e164 or "")
        if patient_id and self.PINS.get(patient_id) == pin:
            self.pin_failures.pop(key, None)
            self.calls.setdefault(call_id, {"turns": []})["patient_id"] = patient_id
            return {"ok": True, "patient_id": patient_id}
        self.pin_failures[key] = failures + 1
        return {"ok": False, "tries_left": self.MAX_TRIES - failures - 1}

    async def call_context(self, *, call_id, patient_id):
        return self._context(patient_id)

    async def check_turn(self, *, call_id, patient_id, text, language, confidence=None):
        lowered = text.lower()
        for rule_id, pattern in _MOCK_RED_FLAGS.items():
            if re.search(pattern, lowered):
                escalation = {"id": f"e-{uuid.uuid4().hex[:6]}", "rule_id": rule_id, "original_text": text, "call_id": call_id}
                self.events.append({"type": "escalation_opened", **escalation})
                logger.warning("red flag %s on call %s", rule_id, call_id)
                return {"action": "escalate", "escalation": escalation}
        if confidence is not None and confidence < 0.6:
            return {"action": "clarify"}
        return {"action": "continue"}

    async def log_turn(self, *, call_id, speaker, text, language):
        self.calls.setdefault(call_id, {"turns": []})["turns"].append({"speaker": speaker, "transcript": text, "language": language})

    async def record_task_update(self, *, call_id, patient_id, task_id, status, patient_words):
        event = {"type": "task_update", "task_id": task_id, "status": status, "original_text": patient_words, "verification_status": "patient_reported"}
        self.events.append(event)
        return {"ok": True}

    async def report_problem(self, *, call_id, patient_id, kind, patient_words, task_id):
        self.events.append({"type": "barrier_reported", "barrier_type": kind, "task_id": task_id, "original_text": patient_words})
        return {"ok": True}

    async def ask_care_team(self, *, call_id, patient_id, question):
        self.events.append({"type": "patient_question", "original_text": question})
        return {"ok": True}

    async def end_call(self, *, call_id, outcome, log):
        call = self.calls.get(call_id, {})
        logger.info("call %s ended: %s, %d turns, %d events", call_id, outcome, len(call.get("turns", [])), len(self.events))


def make_backend() -> Backend:
    if os.getenv("VOICE_USE_MOCKS", "1") != "0":
        logger.info("using the mock backend (VOICE_USE_MOCKS=1)")
        return MockBackend()
    return HttpBackend(os.environ["BACKEND_URL"], os.environ["VOICE_SERVICE_TOKEN"])
