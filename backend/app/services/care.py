"""Shared care logic for chat, voice and the dashboard: summaries, task reports, barriers and reschedules.

Ported from the frontend mock (frontend/shared/mock-server.js) so both behave the same. Every line Tomi says here
is a fixed, approved sentence; nothing here writes new medical content. Safety: app/safety/rules.py. Chat:
services/chat.py. Escalations: services/escalations.py.
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from app.agents import barrier as barrier_agent
from app.db import store
from app.safety import rules as safety
from app.services import outbox
from app.services.activity_log import log_event
from app.util import make_id, not_found, now_iso, parse_iso

SUPPORT = {"tomi_number": "+2348000000000", "emergency_number": "112", "emergency_text": "If you feel very unwell, go to the nearest hospital now."}
EMERGENCY_LINE = safety.emergency_line()
BARRIER_TYPES = ["cost", "transport", "stock", "understanding"]

# Plain-word hints for the four barrier types when the Check-in Agent is not available.
BARRIER_TERMS = {
    "cost": ["cost", "money", "afford", "price", "kudi"],
    "transport": ["transport", "travel", "bus", "far"],
    "stock": ["stock", "buy", "could not get", "not get", "pharmacy", "out of"],
    "understanding": ["understand", "confus"],
}


def zone() -> ZoneInfo:
    return ZoneInfo(os.getenv("CARELOOP_TIMEZONE") or "Africa/Lagos")


def local(iso_text: str) -> datetime:
    return parse_iso(iso_text).astimezone(zone())


LINES_PATH = Path(__file__).resolve().parents[3] / "voice" / "prompts" / "lines.json"
LANGUAGE_CODES = {"Hausa": "ha", "Yoruba": "yo", "Igbo": "ig", "English": "en"}


def emergency_in(language: str) -> dict:
    """The emergency line is never machine-translated: Tomi's prepared line in the patient's language (the same one
    she says on calls), then the approved English."""
    code = LANGUAGE_CODES.get(language, "en")
    try:
        prepared = json.loads(LINES_PATH.read_text(encoding="utf-8"))[code]["emergency"] if code != "en" else None
    except (OSError, ValueError, KeyError):
        prepared = None
    text = f"{prepared}\n\n{EMERGENCY_LINE}" if prepared else EMERGENCY_LINE
    return {"text": text, "language": language if prepared else "English", "number_check_passed": True, "uncertainty_flags": []}


def find_patient(patient_id: str) -> dict:
    patient = store().get("patients", patient_id)
    if not patient:
        raise not_found("Patient")
    return patient


def with_patient(item: dict) -> dict:
    patient = store().get("patients", item.get("patient_id"))
    return {**item, "patient_name": patient["name"] if patient else item.get("patient_id"), "patient_language": patient.get("language") if patient else None}


def public_patient(patient: dict) -> dict:
    """A patient record without secrets (PIN hash and the like)."""
    return {key: value for key, value in patient.items() if not key.startswith("pin_hash") and key != "pending_check"}


def patient_summary(patient: dict) -> dict:
    db = store()
    plan = db.first("plans", patient_id=patient["id"])
    tasks = db.where("tasks", patient_id=patient["id"])
    contact = sorted((event for event in db.where("events", patient_id=patient["id"]) if event["actor_type"] != "clinician"),
                     key=lambda event: event["reported_at"], reverse=True)
    return {
        **public_patient(patient),
        "plan_status": plan["status"] if plan else "not_created",
        "open_tasks": sum(task["status"] in ("pending", "overdue", "unable") for task in tasks),
        "task_counts": {
            "done": sum(task["status"] in ("patient_reported_done", "clinician_verified") for task in tasks),
            "due": sum(task["status"] == "pending" for task in tasks),
            "missed": sum(task["status"] in ("overdue", "unable") for task in tasks),
        },
        "overdue_critical": sum(task["status"] == "overdue" and task.get("criticality") == "high" for task in tasks),
        "open_barriers": sum(not barrier["status"].startswith("resolved") for barrier in db.where("barriers", patient_id=patient["id"])),
        "open_escalations": sum(item["status"] != "resolved" for item in db.where("escalations", patient_id=patient["id"])),
        "failed_messages": sum(item["status"] == "failed" and not item.get("retried") for item in db.where("notifications", patient_id=patient["id"])),
        "next_message": outbox.next_message(patient["id"]),
        "last_contact": {"at": contact[0]["reported_at"], "channel": contact[0]["source_channel"], "summary": contact[0]["summary"]} if contact else None,
    }


CHANNEL_WORDS = {"web": "chat in the app", "voice": "phone calls", "sms": "text messages", "email": "email"}


def channel_list(channels: list[str]) -> str:
    words = [CHANNEL_WORDS.get(channel, channel) for channel in channels]
    return f"{', '.join(words[:-1])} and {words[-1]}" if len(words) > 1 else (words[0] if words else "nothing")


def classify(text: str) -> dict:
    lower = text.lower()
    if safety.check(text).escalate:
        return {"kind": "red_flag"}
    for kind, terms in BARRIER_TERMS.items():
        if any(term in lower for term in terms):
            return {"kind": "barrier", "type": kind}
    if re.search(r"(appointment|visit|reschedule|new time|change.*time)", lower):
        return {"kind": "reschedule"}
    if re.match(r"^(done|yes|i took|took it|i have taken|eh|bẹ́ẹ̀ni|ee)", lower) or "took" in lower:
        return {"kind": "done"}
    if re.search(r"not yet|later|no\b", lower):
        return {"kind": "not_yet"}
    if "problem" in lower:
        return {"kind": "problem"}
    return {"kind": "other"}


def next_open_task(patient_id: str) -> dict | None:
    tasks = store().where("tasks", lambda task: task["status"] in ("pending", "overdue"), patient_id=patient_id)
    return min(tasks, key=lambda task: task["due_at"], default=None)


def open_barrier(patient: dict, kind: str, channel: str) -> dict:
    db = store()
    kind = barrier_agent.normalize_type(kind)
    task = next_open_task(patient["id"])
    barrier = db.first("barriers", lambda item: not item["status"].startswith("resolved"), patient_id=patient["id"], type=kind)
    if not barrier:
        barrier = db.add("barriers", {"id": make_id("b"), "patient_id": patient["id"], "task_id": task["id"] if task else None,
                                      "type": kind, "status": "open", "attempts": 0, "opened_at": now_iso(), "options": []})
    barrier["attempts"] += 1
    barrier["options"] = barrier_agent.options_for(kind, patient.get("facility"), SUPPORT["tomi_number"])
    barrier["status"] = "option_offered"
    log_event(patient["id"], actor_type="patient", actor_id=patient["name"], source_channel=channel, event_type="barrier_opened",
              summary=f"Reported a {kind} problem.", verification_status="self_reported")
    log_event(patient["id"], actor_type="agent", actor_id="Barrier Resolution Agent", source_channel=channel, event_type="barrier_option_offered",
              summary="Possible support option shared. Barrier not resolved.", verification_status="system_recorded")
    channels = outbox.notifications.message_channels(patient)
    if channels:
        outbox.queue_message(patient, channel=channels[0], template="support", created_by="Barrier Resolution Agent")
    return barrier


def request_reschedule(patient: dict, reason: str, channel: str, original_text: str) -> dict | None:
    now_text = now_iso()
    upcoming = store().where("appointments", lambda item: item["status"] in ("scheduled", "confirmed") and item["starts_at"] > now_text, patient_id=patient["id"])
    if not upcoming:
        return None
    appointment = min(upcoming, key=lambda item: item["starts_at"])
    appointment["status"] = "reschedule_requested"
    request = store().add("reschedule_requests", {"id": make_id("rr"), "appointment_id": appointment["id"], "patient_id": patient["id"], "reason": reason,
                                                  "original_text": original_text, "channel": channel, "requested_at": now_iso(), "status": "pending", "reviewer": None})
    log_event(patient["id"], actor_type="patient", actor_id=patient["name"], source_channel=channel, event_type="reschedule_requested",
              summary="Asked for a new appointment time.", verification_status="self_reported")
    return {"request": request, "appointment": appointment}


def report_task(patient: dict, task: dict | None, status: str, channel: str, actor: str | None = None) -> None:
    if not task:
        return
    task["status"] = {"done": "patient_reported_done", "unable": "unable"}.get(status, task["status"])
    task["last_reported_at"] = now_iso()
    summaries = {"done": f"{task['title']}: reported as done.", "not_yet": f"{task['title']}: reported as not yet done.", "unable": f"{task['title']}: reported as not possible."}
    log_event(patient["id"], actor_type="patient", actor_id=actor or patient["name"], source_channel=channel, event_type="task_reported",
              summary=summaries[status], verification_status="self_reported", target_id=task["id"])
    if status == "done":
        outbox.cancel_messages(patient["id"], lambda item: item.get("task_id") == task["id"], "Not needed. The patient already reported it done.")


def task_time(task: dict) -> str:
    return local(task["due_at"]).strftime("%H:%M")
