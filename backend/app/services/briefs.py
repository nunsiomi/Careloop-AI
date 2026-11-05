"""What an agent may know about a patient, as compact JSON-ready dicts (decided by Nunsi, 5 Nov 2026).

- staff_brief: the whole record for the care-team assistant (plan, tasks, problems, escalations, calls, timeline).
- facility_overview: one line per patient, so the assistant can answer "who needs attention today?".
- patient_brief: what Tomi may tell the patient (or their caregiver) about their own care, in the chat or on a call.

Nothing here is written by a model: it is the record as stored, with times in the facility's time zone.
"""

from app.db import store
from app.services import care
from app.util import now_iso

DONE = ("patient_reported_done", "clinician_verified")
MISSED = ("overdue", "unable")


def _when(iso_text: str | None) -> str | None:
    return care.local(iso_text).strftime("%a %d %b %Y, %H:%M") if iso_text else None


def _plan(patient_id: str) -> dict | None:
    return store().first("plans", patient_id=patient_id, status="approved") or store().first("plans", patient_id=patient_id)


def _task(task: dict) -> dict:
    return {"id": task["id"], "type": task["type"], "what": task["title"], "detail": task["detail"], "due": _when(task["due_at"]),
            "status": task["status"].replace("_", " "), "importance": task.get("criticality")}


def _visits(patient_id: str) -> list[dict]:
    visits = sorted(store().where("appointments", lambda item: item["status"] != "cancelled", patient_id=patient_id), key=lambda item: item["starts_at"])
    return [{"what": item["what"], "where": item["where"], "when": _when(item["starts_at"]), "status": item["status"]} for item in visits]


def _medicines(plan: dict | None) -> list[dict]:
    return [{key: item.get(key) for key in ("name", "dose", "frequency", "times", "duration", "instructions")} for item in (plan or {}).get("medications", [])]


def staff_brief(patient: dict) -> dict:
    db = store()
    plan = _plan(patient["id"])
    tasks = sorted(db.where("tasks", patient_id=patient["id"]), key=lambda item: item["due_at"])
    events = sorted(db.where("events", patient_id=patient["id"]), key=lambda item: item["reported_at"], reverse=True)[:15]
    calls = sorted(db.where("calls", patient_id=patient["id"]), key=lambda item: item["started_at"], reverse=True)[:3]
    summary = care.patient_summary(patient)
    return {
        "id": patient["id"], "name": patient["name"], "age": patient.get("age"), "language": patient.get("language"),
        "reading_level": patient.get("literacy_level"), "facility": patient.get("facility"), "status": patient.get("activation_status"),
        "agreed_channels": care.channel_list(patient.get("channels", [])), "contact_window": patient.get("contact_window"),
        "caregiver": patient.get("caregiver"), "risk": patient.get("risk_level") or patient.get("risk"),
        "plan": None if not plan else {
            "status": plan["status"], "approved_by": plan.get("approved_by"), "approved_at": _when(plan.get("clinician_approved_at")),
            "medicines": _medicines(plan), "visits_in_plan": plan.get("appointments", []), "tests_in_plan": plan.get("tests", []),
            "symptoms_to_watch": plan.get("symptoms_to_watch", []), "checker_issues": plan.get("verifier_issues", []),
        },
        "task_counts": summary["task_counts"], "overdue_high_importance": summary["overdue_critical"],
        "tasks": [_task(task) for task in tasks][-20:],
        "upcoming_visits": _visits(patient["id"]),
        "problems_reported": [{"type": item["type"], "status": item["status"].replace("_", " "), "attempts": item.get("attempts"), "opened": _when(item.get("opened_at"))}
                              for item in db.where("barriers", patient_id=patient["id"])],
        "escalations": [{"reason": item.get("rule_label") or item.get("reason"), "severity": item.get("severity"), "status": item["status"],
                         "patient_words": item.get("original_text"), "opened": _when(item.get("created_at"))}
                        for item in db.where("escalations", patient_id=patient["id"])],
        "recent_calls": [{"when": _when(item["started_at"]), "direction": item["direction"], "outcome": item.get("outcome") or item["status"]} for item in calls],
        "timeline": [{"when": _when(item["reported_at"]), "who": item.get("actor_id"), "channel": item.get("source_channel"), "what": item["summary"]} for item in events],
        "last_contact": summary["last_contact"],
    }


def facility_overview(facility: str) -> list[dict]:
    rows = []
    for patient in store().where("patients", facility=facility):
        summary = care.patient_summary(patient)
        visits = [visit for visit in _visits(patient["id"]) if visit["status"] != "attended"]
        rows.append({"id": patient["id"], "name": patient["name"], "age": patient.get("age"), "language": patient.get("language"),
                     "status": patient.get("activation_status"), "plan": summary["plan_status"], "tasks": summary["task_counts"],
                     "overdue_high_importance": summary["overdue_critical"], "open_problems": summary["open_barriers"],
                     "open_escalations": summary["open_escalations"],
                     "open_escalation_levels": [item["severity"] for item in store().where("escalations", patient_id=patient["id"]) if item["status"] != "resolved"],
                     "next_visit": visits[0] if visits else None,
                     "medicines": [item["name"] for item in _medicines(_plan(patient["id"]))],
                     "last_contact": summary["last_contact"]})
    return rows


def patient_brief(patient: dict) -> dict:
    """Only the approved plan and the patient's own tasks and visits: what Tomi may say to them."""
    plan = store().first("plans", patient_id=patient["id"], status="approved")
    tasks = sorted(store().where("tasks", patient_id=patient["id"]), key=lambda item: item["due_at"])
    today = care.local(now_iso()).date()
    return {
        "first_name": patient["name"].split(" ")[0], "facility": patient.get("facility"), "language": patient.get("language"),
        "medicines": _medicines(plan), "symptoms_to_watch": (plan or {}).get("symptoms_to_watch", []),
        "today": [_task(task) for task in tasks if care.local(task["due_at"]).date() == today],
        "open_tasks": [_task(task) for task in tasks if task["status"] in ("pending", "overdue", "unable")][:12],
        "upcoming_visits": [visit for visit in _visits(patient["id"]) if visit["status"] not in ("attended", "missed")][:5],
        "has_approved_plan": bool(plan),
    }
