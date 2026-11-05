"""Reminder and message records: queueing, the reminder schedule, and sending what is due.

The rules (templates, timing, quiet hours, consent) live in services/notifications.py; this module stores each
message as a notification record the dashboard shows (docs/api_shapes.md, "Email (and later SMS) reminders").
"""

from datetime import timedelta

from app.db import store
from app.services import notifications
from app.services.activity_log import log_event
from app.util import iso, make_id, mask_email, mask_phone, now, now_iso, parse_iso

ACTIVE = {"scheduled", "sent", "delivered"}
MANUAL_TEMPLATES = ["medicine", "visit", "call_clinic"]


def channel_noun(channel: str) -> str:
    return "text" if channel == "sms" else "email"


def queue_message(patient: dict, *, channel: str, template: str, scheduled_for: str | None = None, task_id=None,
                  appointment_id=None, created_by: str = "Reminder scheduler", status: str = "scheduled", **extra) -> dict:
    title = notifications.TEMPLATES[template][0]
    subject, body = notifications.render(template, patient, channel)
    message = {
        "id": make_id("n"), "patient_id": patient["id"], "channel": channel, "template": template, "title": title,
        "subject": subject if channel == "email" else None, "body": body,
        "to": mask_phone(patient.get("phone_e164")) if channel == "sms" else mask_email(patient.get("email")),
        "status": status, "scheduled_for": scheduled_for or now_iso(), "sent_at": None, "delivered_at": None,
        "failure_reason": None, "task_id": task_id, "appointment_id": appointment_id, "created_by": created_by, **extra,
    }
    return store().add("notifications", message)


def _has_active(patient_id: str, test) -> bool:
    return any(item["patient_id"] == patient_id and item["status"] in ACTIVE and test(item) for item in store().all("notifications"))


def schedule_reminders(patient: dict) -> None:
    """Queue any reminders this patient should have and does not yet (after consent, plan approval or changes)."""
    if not patient.get("consent_at"):
        return
    tasks = store().where("tasks", patient_id=patient["id"])
    visits = store().where("appointments", patient_id=patient["id"])
    for reminder in notifications.plan_reminders(patient, tasks, visits, now()):
        if reminder.task_id and _has_active(patient["id"], lambda item: item["task_id"] == reminder.task_id and item["channel"] == reminder.channel):
            continue
        if reminder.appointment_id and _has_active(patient["id"], lambda item: item["appointment_id"] == reminder.appointment_id and item["template"] == "visit" and item["channel"] == reminder.channel):
            continue
        queue_message(patient, channel=reminder.channel, template=reminder.template, scheduled_for=iso(reminder.send_at),
                      task_id=reminder.task_id, appointment_id=reminder.appointment_id)


def cancel_messages(patient_id: str, test, reason: str) -> None:
    for item in store().all("notifications"):
        if item["patient_id"] == patient_id and item["status"] == "scheduled" and test(item):
            item["status"], item["failure_reason"] = "cancelled", reason


async def send_due() -> int:
    """Send every scheduled message whose time has come. Returns how many were attempted."""
    due = [item for item in store().all("notifications") if item["status"] == "scheduled" and parse_iso(item["scheduled_for"]) <= now()]
    for message in due:
        message["status"] = "sending"  # so an overlapping run does not pick it up twice
        patient_id = message["patient_id"]

        async def load_patient(patient_id=patient_id):
            return store().get("patients", patient_id) or {"channels": []}

        reminder = notifications.Reminder(patient_id, message["channel"], message["template"], parse_iso(message["scheduled_for"]),
                                          message.get("task_id"), message.get("appointment_id"))
        result = await notifications.dispatch(reminder, load_patient)
        message["status"] = result.status
        message["failure_reason"] = result.failure_reason
        if result.status == "sent":
            message["sent_at"] = now_iso()
            message["provider_id"] = result.provider_id
            log_event(patient_id, actor_type="provider", actor_id="SMS provider" if message["channel"] == "sms" else "Email provider",
                      source_channel=message["channel"], event_type="notification_sent",
                      summary=f"{message['title']} {channel_noun(message['channel'])} sent.", verification_status="provider_status")
        elif result.status == "failed":
            log_event(patient_id, actor_type="provider", actor_id="Email provider", source_channel=message["channel"],
                      event_type="notification_failed", summary=f"{message['title']} {channel_noun(message['channel'])} not delivered.",
                      verification_status="provider_status")
    return len(due)


def next_message(patient_id: str) -> dict | None:
    upcoming = sorted((item for item in store().all("notifications") if item["patient_id"] == patient_id and item["status"] == "scheduled"),
                      key=lambda item: item["scheduled_for"])
    return {key: upcoming[0][key] for key in ("channel", "scheduled_for", "title")} if upcoming else None


def soon(minutes: int = 1) -> str:
    return iso(now() + timedelta(minutes=minutes))
