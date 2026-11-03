# backend/tests/test_notifications.py
# Email reminders (doc v2, section 8): generic wording, quiet hours, consent at send time, retries.
import re
from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from app.adapters import SendResult
from app.adapters import email as email_adapter
from app.services import notifications

LAGOS = ZoneInfo("Africa/Lagos")
NOW = datetime(2026, 11, 3, 10, 0, tzinfo=LAGOS)


def patient(**changes) -> dict:
    base = {"id": "p-tola", "name": "Tola Adeyemi", "email": "tola.adeyemi@kestrelmail.ng", "phone_e164": "+2348000000102",
            "channels": ["web", "email", "voice"], "consent_at": "2026-11-01T14:00:00+01:00"}
    return {**base, **changes}


def task(due: datetime, **changes) -> dict:
    return {"id": "t-1", "type": "medication", "due_at": due.isoformat(), "status": "pending", **changes}


def test_reminder_30_minutes_before_each_task_by_email():
    reminders = notifications.plan_reminders(patient(), [task(NOW + timedelta(hours=4))], [], NOW)

    assert [(item.channel, item.template, item.send_at) for item in reminders] == [("email", "medicine", NOW + timedelta(hours=3, minutes=30))]


def test_no_reminders_without_consent_or_email():
    assert notifications.plan_reminders(patient(consent_at=None), [task(NOW + timedelta(hours=4))], [], NOW) == []
    assert notifications.plan_reminders(patient(email=None), [task(NOW + timedelta(hours=4))], [], NOW) == []
    assert notifications.plan_reminders(patient(channels=["web", "voice"]), [task(NOW + timedelta(hours=4))], [], NOW) == []


def test_sms_stays_off_until_set_up(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "termii")
    monkeypatch.setenv("SMS_API_KEY", "x")

    reminders = notifications.plan_reminders(patient(channels=["sms", "email"]), [task(NOW + timedelta(hours=4))], [], NOW)

    assert [item.channel for item in reminders] == ["email"]


def test_quiet_hours_move_to_seven_in_the_morning():
    late = NOW.replace(hour=22, minute=30)       # reminder would go at 22:00
    early = NOW.replace(hour=6, minute=0) + timedelta(days=1)

    reminders = notifications.plan_reminders(patient(), [task(late, id="t-late"), task(early, id="t-early")], [], NOW)

    assert {item.task_id: item.send_at for item in reminders} == {
        "t-late": NOW.replace(hour=7, minute=0) + timedelta(days=1),
        "t-early": NOW.replace(hour=7, minute=0) + timedelta(days=1),
    }


def test_visit_reminder_the_evening_before():
    visit = {"id": "a-1", "starts_at": (NOW + timedelta(days=2)).isoformat(), "status": "confirmed"}
    cancelled = {"id": "a-2", "starts_at": (NOW + timedelta(days=3)).isoformat(), "status": "cancelled"}

    reminders = notifications.plan_reminders(patient(), [], [visit, cancelled], NOW)

    assert [(item.appointment_id, item.template, item.send_at) for item in reminders] == [("a-1", "visit", NOW.replace(hour=18) + timedelta(days=1))]


def test_done_and_past_tasks_get_no_reminder():
    tasks = [task(NOW + timedelta(hours=2), status="patient_reported_done"), task(NOW - timedelta(hours=1), id="t-old")]

    assert notifications.plan_reminders(patient(), tasks, [], NOW) == []


@pytest.mark.parametrize("template", sorted(notifications.TEMPLATES))
def test_messages_never_name_a_medicine_or_condition(template):
    subject, body = notifications.render(template, patient(), "email")

    assert body.startswith("CareLoop: Hello Tola,")
    assert not re.search(r"\b(mg|tablet|capsule|amlodipine|metformin|diabetes|heart|blood test|hypertension)\b", f"{subject} {body}", re.I)
    assert "careloop" in body.lower() and "Open CareLoop:" in body


@pytest.mark.asyncio
async def test_dispatch_sends_by_email():
    send = AsyncMock(return_value=SendResult(ok=True, provider_id="<m1@careloop.app>"))
    reminder = notifications.Reminder("p-tola", "email", "medicine", NOW)

    result = await notifications.dispatch(reminder, AsyncMock(return_value=patient()), send_mail=send)

    assert (result.status, result.attempts, result.provider_id) == ("sent", 1, "<m1@careloop.app>")
    to, subject, _ = send.await_args.args
    assert (to, subject) == ("tola.adeyemi@kestrelmail.ng", "A reminder from your care team")


@pytest.mark.asyncio
async def test_dispatch_checks_consent_at_send_time():
    send = AsyncMock()
    reminder = notifications.Reminder("p-tola", "email", "medicine", NOW)

    result = await notifications.dispatch(reminder, AsyncMock(return_value=patient(channels=["web"])), send_mail=send)

    assert result.status == "cancelled"
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_retries_temporary_errors_only():
    flaky = AsyncMock(side_effect=[SendResult(ok=False, error="timeout", retryable=True), SendResult(ok=True, provider_id="m2")])
    refused = AsyncMock(return_value=SendResult(ok=False, error="Address refused"))
    sleep = AsyncMock()
    reminder = notifications.Reminder("p-tola", "email", "visit", NOW)

    retried = await notifications.dispatch(reminder, AsyncMock(return_value=patient()), send_mail=flaky, sleep=sleep)
    gave_up = await notifications.dispatch(reminder, AsyncMock(return_value=patient()), send_mail=refused, sleep=sleep)

    assert (retried.status, retried.attempts) == ("sent", 2)
    assert (gave_up.status, gave_up.attempts, gave_up.failure_reason) == ("failed", 1, "Not delivered. Address refused")


@pytest.mark.asyncio
async def test_sign_in_code_email():
    send = AsyncMock(return_value=SendResult(ok=True))

    await notifications.send_sign_in_code("tola.adeyemi@kestrelmail.ng", "482913", send_mail=send)

    to, subject, text = send.await_args.args
    assert (to, subject) == ("tola.adeyemi@kestrelmail.ng", "Your CareLoop sign-in code")
    assert "482913" in text and "Never share it" in text


@pytest.mark.asyncio
async def test_console_provider_sends_nothing(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)

    result = await email_adapter.send_email("tola.adeyemi@kestrelmail.ng", "Subject", "Body")

    assert result.ok and result.provider_id
