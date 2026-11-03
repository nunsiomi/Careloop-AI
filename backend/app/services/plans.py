"""The plan flow (doc v2, section 6, flow A): discharge note -> Care Plan Agent -> Plan Verifier -> clinician
review -> approval -> tasks, visits and reminders. Nothing reaches the patient before a clinician approves, and a
plan with an open high-severity issue cannot be approved unless the clinician explicitly acknowledges it.
"""

import logging
import re
from datetime import datetime, timedelta

from pydantic import ValidationError

from app.agents import care_plan, plan_rules, plan_verifier
from app.db import store
from app.models import PlanDraft
from app.services import care, identity, outbox
from app.services.activity_log import log_event
from app.util import ApiError, iso, make_id, now, now_iso

log = logging.getLogger("careloop.plans")
PLAN_FIELDS = ("medications", "appointments", "tests", "symptoms_to_watch", "reminder_times")
DEFAULT_DAYS = 7  # used only when the plan gives no length of treatment; the event log says so


def _empty_plan() -> dict:
    return PlanDraft().model_dump()


async def create_plan(patient: dict, source_note: str, by: str) -> dict:
    note = (source_note or "").strip()
    if not note:
        raise ApiError("Paste the discharge note first.")
    try:
        drafted = await care_plan.run({"source_note": note, "patient": {"name": patient["name"]}})
    except ValueError as error:  # GROQ_API_KEY missing
        log.warning("Care Plan Agent unavailable: %s", error)
        drafted = {"plan": _empty_plan(), "unresolved": [{"field": "plan", "issue": "The plan could not be drafted automatically; enter it by hand",
                                                          "severity": "high", "source_text": ""}], "deliverable": False, "error": str(error)}
    checked = await plan_verifier.run({"source_note": note, "plan": drafted["plan"], "patient": {"name": patient["name"]}})
    issues = checked["issues"] + [item for item in drafted["unresolved"] if item["field"] == "plan"]
    plan = {"id": make_id("plan"), "patient_id": patient["id"], "status": "needs_review", "clinician_approved_at": None, "approved_by": None,
            "source_note": note, "verifier_issues": issues, "deliverable": checked["deliverable"] and not drafted.get("error"),
            "model_checked": checked["model_checked"], "created_by": by, **drafted["plan"]}
    store().remove("plans", lambda item: item["patient_id"] == patient["id"])
    store().add("plans", plan)
    flagged = len(issues)
    log_event(patient["id"], actor_type="agent", actor_id="Care Plan Agent", source_channel="system", event_type="plan_drafted",
              summary=f"Plan drafted. {flagged} field{'' if flagged == 1 else 's'} flagged by the verifier.", verification_status="system_recorded")
    return plan


def update_plan(plan: dict, updates: dict, by: str) -> dict:
    """Clinician edits. The rule checks run again so the issue list matches what is now in the plan."""
    if plan["status"] == "approved":
        raise ApiError("This plan is already approved. Draft a new one to change it.", 409)
    changed = {key: updates[key] for key in PLAN_FIELDS if key in updates}
    if "source_note" in updates and str(updates["source_note"]).strip():
        changed["source_note"] = str(updates["source_note"]).strip()
    try:
        draft = PlanDraft.model_validate({**{key: plan.get(key) for key in PLAN_FIELDS}, **{key: changed[key] for key in PLAN_FIELDS if key in changed}})
    except ValidationError as error:
        raise ApiError(f"Check the plan: {error.errors()[0]['msg']}.") from error
    plan.update(draft.model_dump())
    if "source_note" in changed:
        plan["source_note"] = changed["source_note"]
    patient = store().get("patients", plan["patient_id"])
    found = [issue.model_dump() for issue in plan_rules.issues(plan["source_note"], draft, patient["name"] if patient else "")]
    plan["verifier_issues"], plan["deliverable"] = found, not any(issue["severity"] == "high" for issue in found)
    log_event(plan["patient_id"], actor_type="clinician", actor_id=by, source_channel="dashboard", event_type="plan_edited",
              summary="Plan fields edited by clinician.", verification_status="clinician_verified")
    return plan


def _days(duration: str) -> int | None:
    match = re.search(r"(\d+)\s*(day|week|month)", duration or "", re.I)
    if not match:
        return None
    return int(match.group(1)) * {"day": 1, "week": 7, "month": 30}[match.group(2).lower()]


def _local(day: datetime, hhmm: str) -> datetime:
    hours, minutes = (int(part) for part in hhmm.split(":"))
    return day.replace(hour=hours, minute=minutes, second=0, microsecond=0)


def _tasks_from_plan(plan: dict, by: str) -> tuple[int, list[str]]:
    """One pending task per medicine time per day, one per dated test, one appointment per dated visit."""
    db, notes, created = store(), [], 0
    db.remove("tasks", lambda item: item.get("plan_id") == plan["id"] and item["status"] == "pending")
    today = datetime.now(care.zone()).replace(hour=0, minute=0, second=0, microsecond=0)
    current = now()
    for medication in plan.get("medications", []):
        if not medication.get("name") or not medication.get("times"):
            notes.append(f"{medication.get('name') or 'A medicine'} has no time, so no reminders were made for it.")
            continue
        days = _days(medication.get("duration", ""))
        if days is None:
            days = DEFAULT_DAYS
            notes.append(f"{medication['name']} has no length of treatment; reminders set for {DEFAULT_DAYS} days.")
        for offset in range(min(days, 90)):
            for time in medication["times"]:
                due = _local(today + timedelta(days=offset), time)
                if due <= current:
                    continue
                db.add("tasks", {"id": make_id("t"), "patient_id": plan["patient_id"], "plan_id": plan["id"], "type": "medication",
                                 "title": medication["name"], "detail": medication.get("dose", ""), "due_at": iso(due), "criticality": "high",
                                 "status": "pending", "last_reported_at": None, "created_by": by})
                created += 1
    for test in plan.get("tests", []):
        if test.get("name") and test.get("date"):
            due = _local(datetime.fromisoformat(test["date"]).replace(tzinfo=care.zone()), "09:00")
            db.add("tasks", {"id": make_id("t"), "patient_id": plan["patient_id"], "plan_id": plan["id"], "type": "test", "title": test["name"],
                             "detail": test.get("where", ""), "due_at": iso(due), "criticality": "medium", "status": "pending", "last_reported_at": None, "created_by": by})
            created += 1
    for visit in plan.get("appointments", []):
        if visit.get("date") and visit.get("time"):
            starts = _local(datetime.fromisoformat(visit["date"]).replace(tzinfo=care.zone()), visit["time"])
            already = db.first("appointments", lambda item: item["starts_at"] == iso(starts), patient_id=plan["patient_id"])
            if not already:
                db.add("appointments", {"id": make_id("a"), "patient_id": plan["patient_id"], "plan_id": plan["id"], "what": visit.get("what") or "Review visit",
                                        "where": visit.get("where", ""), "starts_at": iso(starts), "status": "scheduled", "created_by": by})
    return created, notes


async def approve_plan(plan: dict, override_issues: bool, by: str) -> dict:
    high = [issue for issue in plan.get("verifier_issues", []) if issue.get("severity") == "high"]
    if high and not override_issues:
        raise ApiError("This plan still has serious issues. Fix them, or confirm you have checked each one.", 409)
    plan.update(status="approved", clinician_approved_at=now_iso(), approved_by=by)
    patient = store().get("patients", plan["patient_id"])
    if patient["activation_status"] == "plan_review":
        patient["activation_status"] = "invited"
    created, notes = _tasks_from_plan(plan, by)
    summary = "Plan approved with verifier issues acknowledged." if (override_issues and plan.get("verifier_issues")) else "Plan approved."
    log_event(plan["patient_id"], actor_type="clinician", actor_id=by, source_channel="dashboard", event_type="plan_approved",
              summary=" ".join([summary, f"{created} reminders created.", *notes]), verification_status="clinician_verified")
    if not patient.get("consent_at"):
        await identity.create_patient_invite(patient)
    outbox.schedule_reminders(patient)
    return plan
