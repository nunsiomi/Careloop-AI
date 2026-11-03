"""APScheduler jobs for due reminders and follow-ups.

Every 30 seconds: send due reminders (email now, SMS once set up), mark missed critical tasks overdue, top up
reminder schedules, and clear expired codes and sessions. Runs inside the API process (one Uvicorn worker).
A missed task is never treated as a missed dose; it shows as overdue for the care team to follow up.
"""

import asyncio
import logging
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db import store
from app.services import outbox
from app.services.activity_log import log_event
from app.util import iso, now, now_iso

log = logging.getLogger("careloop.scheduler")
OVERDUE_AFTER = timedelta(hours=2)
_lock = asyncio.Lock()
_scheduler: AsyncIOScheduler | None = None


def mark_overdue() -> int:
    cutoff = iso(now() - OVERDUE_AFTER)
    late = store().where("tasks", lambda task: task["status"] == "pending" and task["due_at"] < cutoff)
    for task in late:
        task["status"] = "overdue"
        log_event(task["patient_id"], actor_type="system", actor_id="Scheduler", source_channel="system", event_type="task_overdue",
                  summary=f"{task['title']}: no report 2 hours after it was due. Not treated as a missed dose.", verification_status="system_recorded")
    return len(late)


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
