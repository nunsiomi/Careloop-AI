"""APScheduler jobs for due reminders and follow-ups.

Every 30 seconds: send due reminders (email now, SMS once set up), mark missed critical tasks overdue, top up
reminder schedules, and clear expired codes and sessions. Runs inside the API process (one Uvicorn worker).
A missed task is never treated as a missed dose; it shows as overdue for the care team to follow up.
"""

import asyncio
import logging
import os
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db import store
from app.services import escalations, identity, outbox
from app.services.activity_log import log_event
from app.util import iso, now, now_iso

log = logging.getLogger("careloop.scheduler")
OVERDUE_AFTER = timedelta(hours=2)
INVITE_FOLLOW_UP = timedelta(hours=24)
_lock = asyncio.Lock()
_scheduler: AsyncIOScheduler | None = None


def mark_overdue() -> int:
    cutoff = iso(now() - OVERDUE_AFTER)
    late = store().where("tasks", lambda task: task["status"] == "pending" and task["due_at"] < cutoff)
    for task in late:
        task["status"] = "overdue"
        escalations.missed_critical_task(task)
        log_event(task["patient_id"], actor_type="system", actor_id="Scheduler", source_channel="system", event_type="task_overdue",
                  summary=f"{task['title']}: no report 2 hours after it was due. Not treated as a missed dose.", verification_status="system_recorded")
    return len(late)


async def invite_followups() -> None:
    """Patients who have not joined 24 hours after their invite: one reminder email, or, with no email address,
    a note on the timeline so the care team can call them."""
    cutoff = iso(now() - INVITE_FOLLOW_UP)
    pending = store().where("invites", lambda item: item.get("created_at", "9") < cutoff and not item.get("followed_up_at"), kind="patient", status="pending")
    for invite in pending:
        invite["followed_up_at"] = now_iso()
        patient = store().get("patients", invite["patient_id"])
        if not patient or patient.get("consent_at"):
            continue
        emailed = await identity.send_welcome(patient, invite, reminder=True)
        log_event(patient["id"], actor_type="system", actor_id="Scheduler", source_channel="email" if emailed else "system", event_type="invite_follow_up",
                  summary="Not joined 24 hours after the invite. Reminder email sent." if emailed else
                          "Not joined 24 hours after the invite, and there is no email address. Please contact the patient.",
                  verification_status="system_recorded")


def clear_expired() -> None:
    stamp = now_iso()
    for name in ("challenges", "mfa_tokens", "resets", "signups", "patient_sessions", "staff_sessions"):
        store().remove(name, lambda item: item.get("expires_at") and item["expires_at"] < stamp)


async def tick() -> None:
    if _lock.locked():
        return
    async with _lock:
        try:
            for patient in store().where("patients", lambda item: bool(item.get("consent_at"))):
                outbox.schedule_reminders(patient)
            await outbox.send_due()
            mark_overdue()
            await escalations.send_alerts()
            await invite_followups()
            if os.getenv("GROQ_API_KEY"):
                await escalations.improve_briefs()
            clear_expired()
        except Exception:  # keep the scheduler alive; the next run tries again
            log.exception("Scheduler run failed")
        finally:
            store().flush()


def start() -> None:
    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(tick, "interval", seconds=30, id="careloop-tick", max_instances=1, coalesce=True)
    _scheduler.start()


def stop() -> None:
    if _scheduler:
        _scheduler.shutdown(wait=False)
