"""Escalations (doc v2, flow G): safety rule fires -> immutable escalation -> factual brief -> dashboard and care-team
email -> delivery and acknowledgement tracked -> backup contact if nobody acknowledges -> a reviewer resolves.

The alert emails say only that an escalation needs review and link to the dashboard: no name or clinical detail.
"""

import logging
from datetime import timedelta

from app.adapters.email import send_email
from app.agents import escalation as summary_agent
from app.db import store
from app.safety.rules import policy
from app.services import care, identity
from app.services.activity_log import log_event
from app.util import make_id, now, now_iso, parse_iso

log = logging.getLogger("careloop.escalations")


def open_items(patient_id: str) -> list[str]:
    db = store()
    items = [f"{barrier['type']} barrier open since {care.local(barrier['opened_at']).strftime('%d %b')}"
             for barrier in db.where("barriers", lambda item: not item["status"].startswith("resolved"), patient_id=patient_id)]
    for request in db.where("reschedule_requests", patient_id=patient_id, status="pending"):
        visit = db.get("appointments", request["appointment_id"]) or {}
        items.append(f"move of {visit.get('what', 'a visit')} requested")
    items += [f"{task['title']} overdue" for task in db.where("tasks", patient_id=patient_id, status="overdue")]
    return items


def create(patient: dict, text: str, channel: str, *, rule_id: str, rule_label: str, severity: str = "red",
           call_id: str | None = None, confidence: float | None = None, english_text: str | None = None, target_id: str | None = None) -> dict:
    stamp = now_iso()
    items = open_items(patient["id"])
    record = {
        "id": make_id("e"), "patient_id": patient["id"], "rule_id": rule_id, "rule_label": rule_label, "severity": severity,
        "status": "created", "channel": channel, "call_id": call_id, "original_text": text, "english_text": english_text or text,
        "confidence": confidence, "outstanding": "; ".join(items) + "." if items else "None recorded.", "created_at": stamp,
        "note": None, "target_id": target_id, "alert_sent_at": None, "backup_sent_at": None, "brief_source": "rules",
        "history": [{"status": "created", "at": stamp, "by": None}],
    }
    record["brief"] = summary_agent.build_brief(record, items, care.local(stamp).strftime("%H:%M"))
    record["brief_ready"] = True
    store().add("escalations", record)
    log_event(patient["id"], actor_type="system", actor_id="Safety engine", source_channel=channel, event_type="escalation_created",
              summary=f"{rule_label}. Escalation created and care team notified.", verification_status="system_recorded")
    return record


def _staff_emails(patient: dict) -> list[str]:
    return [user["email"] for user in store().where("staff", facility=patient.get("facility")) if user.get("email")]


async def _alert(escalation: dict, backup: bool) -> bool:
    patient = store().get("patients", escalation["patient_id"]) or {}
    link = identity.app_url('/clinician/#/escalations')
    subject = "Reminder: a CareLoop escalation still needs review" if backup else "A CareLoop escalation needs review"
    text = (f"A safety rule fired for a patient at {patient.get('facility') or 'your care facility'}"
            f"{' and nobody has acknowledged it yet' if backup else ''}. Open the dashboard to see it: {link}\n\n"
            "This email does not include patient details. CareLoop does not contact emergency services.")
    results = [await send_email(address, subject, text) for address in _staff_emails(patient)]
    return bool(results) and all(result.ok for result in results)


async def send_alerts() -> None:
    """Email the care team about new escalations, and the backup contact about unacknowledged ones."""
    backup_after = timedelta(minutes=int(policy("acknowledgement").get("backup_after_minutes", 15)))
    for escalation in store().all("escalations"):
        if escalation.get("status") == "created" and not escalation.get("alert_sent_at"):
            escalation["alert_sent_at"] = now_iso()
            escalation["status"] = "notification_attempted"
            escalation["history"].append({"status": "notification_attempted", "at": now_iso(), "by": None})
            if await _alert(escalation, backup=False):
                escalation["status"] = "delivered"
                escalation["history"].append({"status": "delivered", "at": now_iso(), "by": None})
        elif (escalation.get("status") in ("notification_attempted", "delivered") and escalation.get("alert_sent_at")
              and not escalation.get("backup_sent_at") and parse_iso(escalation["alert_sent_at"]) + backup_after <= now()):
            escalation["backup_sent_at"] = now_iso()
            escalation["history"].append({"status": "backup_contacted", "at": now_iso(), "by": None})
            await _alert(escalation, backup=True)
            log_event(escalation["patient_id"], actor_type="system", actor_id="Safety engine", source_channel="system", event_type="escalation_backup",
                      summary=f"{escalation['rule_label']}: not acknowledged after {int(backup_after.total_seconds() // 60)} minutes. Backup contact emailed.",
                      verification_status="system_recorded")


async def improve_briefs() -> None:
    """Replace rule-written briefs with the Escalation Summary Agent's, when it passes every check."""
    for escalation in store().where("escalations", brief_source="rules"):
        if escalation["status"] == "resolved":
            continue
        result = await summary_agent.run({"escalation": escalation, "open_items": open_items(escalation["patient_id"]),
                                          "when": care.local(escalation["created_at"]).strftime("%H:%M")})
        escalation["brief_source"] = "model" if result["model_used"] else "rules-final"
        escalation["brief"] = result["brief"]


def missed_critical_task(task: dict) -> dict | None:
    rule = policy("missed_critical_task")
    if not rule.get("enabled") or task.get("criticality") != "high":
        return None
    if store().first("escalations", rule_id="missed_critical_task", target_id=task["id"]):
        return None
    patient = care.find_patient(task["patient_id"])
    return create(patient, f"No report for {task['title']}, due {care.local(task['due_at']).strftime('%H:%M')}.", "system",
                  rule_id="missed_critical_task", rule_label=rule.get("label", "Critical medicine overdue"), severity=rule.get("severity", "amber"),
                  target_id=task["id"])
