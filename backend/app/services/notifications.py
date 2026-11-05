"""Notification dispatcher: consent/quiet hours, retries, provider status.

The same rules as the frontend mock (frontend/shared/mock-server.js), which the scheduler and routes must match:
- Messages are generic templates. They never name a medicine, condition or test.
- One message 30 minutes before each pending task, and one at 18:00 the evening before each visit.
- Nothing is sent between 21:00 and 07:00 in the patient's time zone; those move to 07:00.
- Only on channels the patient agreed to, checked again at send time, so a withdrawal stops queued messages.
- SMS (Termii) and email (SMTP) are the channels. SMS joins once adapters/sms.py is set up (sms_available()).
"""

import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.adapters import SendResult
from app.adapters.email import send_email
from app.adapters import termii
from app.adapters.sms import send_sms, sms_available

QUIET_START, QUIET_END = 21, 7
REMINDER_LEAD = timedelta(minutes=30)
VISIT_EVE_HOUR = 18
ACTIVE_VISITS = {"scheduled", "confirmed", "rescheduled", "reschedule_requested"}
RETRY_WAITS = (30, 120)          # seconds before the 2nd and 3rd tries
EMAIL_SUBJECT = "A reminder from your care team"


def _settings() -> dict[str, str]:
    return {
        "facility": os.getenv("CARELOOP_FACILITY_NAME") or "your care team",
        "tomi_line": os.getenv("TOMI_PHONE_DISPLAY") or "the Tomi number in the app",
        "app_url": os.getenv("APP_URL") or "https://careloop.app",
    }


TEMPLATES: dict[str, tuple[str, str]] = {
    # id: (title, body); {first}, {facility}, {tomi_line} are filled in. Wording matches the frontend mock.
    "medicine": ("Medicine reminder", "CareLoop: Hello {first}, you have a reminder from {facility}. Open the CareLoop app or call Tomi on {tomi_line}. Do not reply."),
    "test": ("Test reminder", "CareLoop: Hello {first}, you have a reminder from {facility}. Open the CareLoop app or call Tomi on {tomi_line}. Do not reply."),
    "visit": ("Visit reminder", "CareLoop: Hello {first}, you have a care visit soon. Open the CareLoop app for the time and place, or call Tomi on {tomi_line}. Do not reply."),
    "visit_moved": ("Visit time changed", "CareLoop: Hello {first}, your visit time has changed. Open the CareLoop app to see the new time, or call Tomi on {tomi_line}. Do not reply."),
    "support": ("Contact that may help", "CareLoop: Hello {first}, your care team shared a contact that may help. Open the CareLoop app to see it, or call Tomi on {tomi_line}. Do not reply."),
    "missed_call": ("Tomi tried to call", "CareLoop: Hello {first}, Tomi tried to call you. Call Tomi back on {tomi_line} when you can, or open the CareLoop app. Do not reply."),
    "call_clinic": ("Please contact your care team", "CareLoop: Hello {first}, your care team at {facility} would like to hear from you. Call Tomi on {tomi_line} or open the CareLoop app. Do not reply."),
}


def render(template: str, patient: dict, channel: str) -> tuple[str, str]:
    """(subject, body) for one message. Email gets a link back to the app; SMS stays short."""
    title, body = TEMPLATES[template]
    settings = _settings()
    facility = patient.get("facility") or settings["facility"]
    text = body.format(first=patient["name"].split()[0], facility=facility, tomi_line=settings["tomi_line"])
    if channel == "email":
        text = f"{text}\n\nOpen CareLoop: {settings['app_url']}\n\nThis email never says what your medicine is for. You can turn email reminders off in the app."
    return (EMAIL_SUBJECT if channel == "email" else title), text


def message_channels(patient: dict) -> list[str]:
    """Reminder channels this patient agreed to and can receive, in order of preference."""
    live = (["sms"] if sms_available() else []) + ["email"]
    agreed = patient.get("channels") or []
    return [channel for channel in live if channel in agreed and (channel != "email" or patient.get("email"))]


def patient_zone(patient: dict) -> ZoneInfo:
    return ZoneInfo(patient.get("timezone") or os.getenv("CARELOOP_TIMEZONE") or "Africa/Lagos")


def outside_quiet_hours(when: datetime, zone: ZoneInfo) -> datetime:
    local = when.astimezone(zone)
    if local.hour >= QUIET_START:
        local = (local + timedelta(days=1)).replace(hour=QUIET_END, minute=0, second=0, microsecond=0)
    elif local.hour < QUIET_END:
        local = local.replace(hour=QUIET_END, minute=0, second=0, microsecond=0)
    return local


@dataclass
class Reminder:
    patient_id: str
    channel: str
    template: str
    send_at: datetime
    task_id: str | None = None
    appointment_id: str | None = None


def plan_reminders(patient: dict, tasks: list[dict], appointments: list[dict], now: datetime) -> list[Reminder]:
    """Reminders to queue for one patient. Call after plan approval and consent, and again when anything changes;
    the caller skips ones already queued (same task or visit, template and channel)."""
    if not patient.get("consent_at"):
        return []
    channels = message_channels(patient)
    zone = patient_zone(patient)
    reminders: list[Reminder] = []

    for task in tasks:
        due = _as_datetime(task["due_at"])
        if task.get("status") != "pending" or due <= now:
            continue
        send_at = outside_quiet_hours(max(due - REMINDER_LEAD, now + timedelta(minutes=1)), zone)
        template = "medicine" if task.get("type") == "medication" else "test"
        reminders += [Reminder(patient["id"], channel, template, send_at, task_id=task["id"]) for channel in channels]

    for visit in appointments:
        starts = _as_datetime(visit["starts_at"])
        if visit.get("status") not in ACTIVE_VISITS or starts <= now:
            continue
        eve = (starts.astimezone(zone) - timedelta(days=1)).replace(hour=VISIT_EVE_HOUR, minute=0, second=0, microsecond=0)
        if eve <= now:
            continue
        reminders += [Reminder(patient["id"], channel, "visit", eve, appointment_id=visit["id"]) for channel in channels]
    return reminders


@dataclass
class DispatchResult:
    status: str                      # "sent" | "failed" | "cancelled"
    attempts: int = 0
    provider_id: str | None = None
    failure_reason: str | None = None
    errors: list[str] = field(default_factory=list)


Sender = Callable[[str, str, str], Awaitable[SendResult]]


async def dispatch(
    reminder: Reminder,
    load_patient: Callable[[], Awaitable[dict]],
    *,
    send_mail: Sender | None = None,
    send_text: Callable[[str, str], Awaitable[SendResult]] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> DispatchResult:
    """Send one due reminder. Consent is read fresh first (load_patient), then up to three tries for errors the
    provider says are temporary. The caller records the result as a notification status and a care event."""
    patient = await load_patient()
    if reminder.channel not in message_channels(patient):
        return DispatchResult("cancelled", failure_reason="Not sent. The patient turned this channel off.")

    send_mail = send_mail or send_email
    send_text = send_text or send_sms
    subject, text = render(reminder.template, patient, reminder.channel)
    result = DispatchResult("failed")
    for attempt, wait in enumerate((0, *RETRY_WAITS), start=1):
        if wait:
            await sleep(wait)
        sent = await (send_mail(patient["email"], subject, text) if reminder.channel == "email" else send_text(patient["phone_e164"], text))
        result.attempts = attempt
        if sent.ok:
            result.status, result.provider_id = "sent", sent.provider_id
            return result
        result.errors.append(sent.error or "unknown error")
        if not sent.retryable:
            break
    result.failure_reason = f"Not delivered. {result.errors[-1]}"
    return result


SMS_CODE_TEXT = "{code} is your CareLoop sign-in code. It works for 5 minutes. Never share it, not even with your care team."


async def send_sign_in_code_sms(to_e164: str, code: str) -> SendResult:
    """Patient and caregiver sign-in codes by text message. Same wording as the mock."""
    return await send_sms(to_e164, SMS_CODE_TEXT.format(code=code))


async def send_code_email(to_email: str, code: str, subject: str, text: str, *, send_mail: Sender | None = None) -> SendResult:
    """Any sign-in code by email: Termii's email OTP when it is set up (wording from the Termii template), else SMTP."""
    if send_mail is None and termii.email_codes_ready():
        return await termii.email_code(to_email, code)
    return await (send_mail or send_email)(to_email, subject, text)


def greeting(name: str | None) -> str:
    first = (name or "").strip().split(" ")[0]
    return f"Hello {first}," if first else "Hello,"


async def send_sign_in_code(to_email: str, code: str, name: str | None = None, *, send_mail: Sender | None = None) -> SendResult:
    """Patient and caregiver sign-in codes by email. Same wording as the mock."""
    text = (f"{greeting(name)}\n\nHere is your code to sign in to CareLoop:\n\n    {code}\n\n"
            "It works for 5 minutes. Never share it, not even with your care team. "
            "If you did not ask for it, you can ignore this email.\n\nThe CareLoop team")
    return await send_code_email(to_email, code, "Your CareLoop sign-in code", text, send_mail=send_mail)


def _as_datetime(value: datetime | str) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
