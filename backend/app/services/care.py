"""Shared care logic for chat, voice and the dashboard: summaries, task reports, barriers, reschedules, escalations.

Ported from the frontend mock (frontend/shared/mock-server.js) so both behave the same. Every line Tomi says here
is a fixed, approved sentence; nothing here writes new medical content.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.db import store
from app.services import outbox
from app.services.activity_log import log_event
from app.util import make_id, not_found, now_iso, parse_iso

DATA = Path(__file__).resolve().parents[3] / "data"
SUPPORT = {"tomi_number": "+2348000000000", "emergency_number": "112", "emergency_text": "If you feel very unwell, go to the nearest hospital now."}
EMERGENCY_LINE = "This may need urgent care. Please go to the nearest hospital now, or call 112. I have sent this to your care team."
BARRIER_TYPES = ["cost", "transport", "stock", "understanding"]

# Placeholder screen until Dorcas and the clinical mentor fill backend/app/safety/red_flags.json (the same terms
# as the frontend mock). Substring match, so it errs towards escalating.
RED_FLAG_TERMS = ["chest", "breath", "breathe", "faint", "kirji", "ƙirji", "numfashi", "àyà", "mímí"]
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


def red_flag_terms() -> list[str]:
    """Terms from safety/red_flags.json once Dorcas fills it; until then the placeholder list above."""
    path = Path(__file__).resolve().parents[1] / "safety" / "red_flags.json"
    try:
        rules = json.loads(path.read_text(encoding="utf-8"))
        terms = [term for rule in rules.get("rules", []) for term in rule.get("terms", [])] if isinstance(rules, dict) else []
        return terms or RED_FLAG_TERMS
    except (OSError, ValueError):
        return RED_FLAG_TERMS


def resources(facility: str) -> dict[str, list[dict]]:
    """Approved contacts per barrier type (data/resources.json), in the shape the app shows."""
    try:
        listed = json.loads((DATA / "resources.json").read_text(encoding="utf-8"))["resources"]
    except (OSError, ValueError, KeyError):
        listed = []
    grouped: dict[str, list[dict]] = {}
    for item in listed:
        if item.get("facility") not in (facility, None):
            continue
        grouped.setdefault(item["type"], []).append(
            {"name": item["name"], "type": item["kind"], "distance": item["area"], "phone": item["phone_e164"], "note": item["note"]})
    return grouped


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
    return {key: value for key, value in patient.items() if not key.startswith("pin_hash")}


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
    if any(term in lower for term in red_flag_terms()):
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


def describe_outstanding(patient_id: str) -> str:
    db = store()
    barriers = sum(not item["status"].startswith("resolved") for item in db.where("barriers", patient_id=patient_id))
    moves = sum(item["status"] == "pending" for item in db.where("reschedule_requests", patient_id=patient_id))
    parts = ([f"{barriers} open barrier{'s' if barriers > 1 else ''}"] if barriers else []) + (["appointment move pending"] if moves else [])
    return f"{', '.join(parts)}." if parts else "None recorded."


def escalation_brief(escalation: dict) -> str:
    """Fact-only brief (Escalation Summary Agent's job, owner Dorcas). Quotes the patient and lists open items;
    it never chooses a diagnosis or urgency."""
    return (f'The patient wrote or said: "{escalation["original_text"]}". Approved emergency guidance was given. '
            f"Open items: {escalation['outstanding']}")


def create_escalation(patient: dict, text: str, channel: str, call_id: str | None = None, confidence: float | None = None,
                      rule_id: str = "possible_red_flag_phrase", rule_label: str = "Possible emergency phrase") -> dict:
    stamp = now_iso()
    escalation = {
        "id": make_id("e"), "patient_id": patient["id"], "rule_id": rule_id, "rule_label": rule_label, "severity": "red",
        "status": "delivered", "channel": channel, "call_id": call_id, "original_text": text, "english_text": text,
        "confidence": confidence, "brief": None, "brief_ready": False, "outstanding": describe_outstanding(patient["id"]),
        "created_at": stamp, "note": None,
        "history": [{"status": "created", "at": stamp, "by": None}, {"status": "notification_attempted", "at": stamp, "by": None},
                    {"status": "delivered", "at": stamp, "by": None}],
    }
    escalation["brief"], escalation["brief_ready"] = escalation_brief(escalation), True
    store().add("escalations", escalation)
    log_event(patient["id"], actor_type="system", actor_id="Safety engine", source_channel=channel, event_type="escalation_created",
              summary="Possible emergency phrase. Escalation created and care team notified.", verification_status="system_recorded")
    return escalation


def open_barrier(patient: dict, kind: str, channel: str) -> dict:
    db = store()
    kind = kind if kind in BARRIER_TYPES else "understanding"
    task = next_open_task(patient["id"])
    barrier = db.first("barriers", lambda item: not item["status"].startswith("resolved"), patient_id=patient["id"], type=kind)
    if not barrier:
        barrier = db.add("barriers", {"id": make_id("b"), "patient_id": patient["id"], "task_id": task["id"] if task else None,
                                      "type": kind, "status": "open", "attempts": 0, "opened_at": now_iso(), "options": []})
    approved = resources(patient.get("facility", ""))
    barrier["attempts"] += 1
    barrier["options"] = approved.get(kind) or approved.get("understanding") or [
        {"name": "Your care team", "type": "Care team", "distance": patient.get("facility", ""), "phone": SUPPORT["tomi_number"], "note": "Ask them to explain your plan again."}]
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


def chat_reply(patient: dict, payload: dict, actor: str | None = None) -> dict:
    """The app's chat. Safety first: a red flag skips everything else and opens an escalation."""
    text = str(payload.get("original_text") or "").strip()
    task = store().get("tasks", payload.get("task_id")) if payload.get("task_id") else next_open_task(patient["id"])
    kind = payload.get("quick_reply") or classify(text)["kind"]
    if classify(text)["kind"] == "red_flag":
        kind = "red_flag"  # a quick reply never hides a red flag typed alongside it
    result = {"reply": None, "barrier": None, "escalation": None, "reschedule": None}
    if kind == "red_flag":
        escalation = create_escalation(patient, text, "web")
        result["escalation"], result["reply"] = {**escalation, "call_number": SUPPORT["emergency_number"]}, EMERGENCY_LINE
    elif kind == "barrier" or kind in BARRIER_TYPES:
        barrier_type = kind if kind in BARRIER_TYPES else classify(text).get("type", "understanding")
        result["barrier"] = open_barrier(patient, barrier_type, "web")
        result["reply"] = "Thank you for telling me. Here is an option your care team shared. Please tell me if it worked."
    elif kind == "reschedule":
        moved = request_reschedule(patient, text, "web", text)
        result["reschedule"] = moved
        result["reply"] = ("I have asked the clinic for a new time. Your current visit stays booked until the clinic confirms a new one."
                           if moved else "You have no upcoming visit to move. Your care team can help.")
    elif kind == "done":
        report_task(patient, task, "done", "web", actor)
        result["reply"] = "Thank you. I have noted that you took it."
    elif kind == "not_yet":
        report_task(patient, task, "not_yet", "web", actor)
        result["reply"] = "Okay. I will remind you again later."
    elif kind in ("worked", "did_not_work"):
        barrier = store().first("barriers", patient_id=patient["id"], status="option_offered")
        if kind == "worked":
            if barrier:
                barrier["status"] = "resolved_patient_reported"
            log_event(patient["id"], actor_type="patient", actor_id=actor or patient["name"], source_channel="web", event_type="barrier_resolved",
                      summary="Said the support option worked.", verification_status="self_reported")
            result["reply"] = "I am glad it helped. I have noted it."
        else:
            if barrier:
                barrier["status"] = "escalated" if barrier["attempts"] >= 2 else "awaiting_response"
            log_event(patient["id"], actor_type="patient", actor_id=actor or patient["name"], source_channel="web", event_type="barrier_update",
                      summary="Said the support option did not work.", verification_status="self_reported")
            result["reply"] = "Thank you for telling me. I have told your care team so they can help."
    else:
        result["reply"] = "Thank you. Your message has been received. Your care team can see it."
    return result


def task_time(task: dict) -> str:
    return local(task["due_at"]).strftime("%H:%M")
