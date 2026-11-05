"""Patient chat in the app (doc v2, flow B/C): safety first, then the Check-in Agent's proposal, confirmed by the
patient before anything changes their record.

Order for every message:
1. Safety rules (safety/rules.py). A red flag stops everything: approved emergency line + escalation. A negated
   mention ("no chest pain") is checked once with the patient.
2. A pending question ("Is that right?") is answered with yes or no.
3. Quick replies (buttons the patient tapped) are explicit, so they act at once.
4. Free text goes to the Check-in Agent (Dorcas). Marking a task done waits for the patient's "yes". A barrier
   opens straight away (it only offers an approved contact). Its reply is used only if it passes the number check
   and the advice guard; otherwise a fixed, approved line is sent.
5. Without a model (no GROQ_API_KEY or an error), simple word matching does the same jobs.
"""

import logging
import os
import re

from groq import GroqError

from app.agents import barrier as barrier_agent
from app.agents import checkin
from app.db import store
from app.safety import number_check
from app.safety import rules as safety
from app.services import care, escalations
from app.services.activity_log import log_event
from app.util import now_iso

log = logging.getLogger("careloop.chat")
YES = re.compile(r"^(yes|yeah|yep|y|correct|that is right|that's right|right|ok|okay|eh|ee|ehen|ehn|i|beeni|bee ni|odi|o di)\b")
NO = re.compile(r"^(no|nope|not really|a'?a|aa|rara|mba|ko)\b")
# Reply wording that would change treatment. Model replies containing any of these are never sent.
ADVICE = re.compile(r"\b(stop taking|stop the|increase|decrease|reduce|double|skip|extra dose|more than|less than|instead of|switch to|"
                    r"you should take|try taking|it is safe|it's safe|don't worry|nothing to worry|diagnos\w*|probably|likely)\b", re.I)
FIXED = {
    "barrier": "Thank you for telling me. Here is an option your care team shared. Please tell me if it worked.",
    "done": "Thank you. I have noted that you took it.",
    "not_yet": "Okay. I will remind you again later.",
    "received": "Thank you. Your message has been received. Your care team can see it.",
    "unchanged": "Okay, I have not changed anything. Your care team can see your message.",
    "no_flag": "Thank you for telling me. If anything changes or you feel very unwell, go to the nearest hospital now.",
}


def _answer(text: str) -> str | None:
    clean = safety.normalize(text)
    return "yes" if YES.match(clean) else "no" if NO.match(clean) else None


def _escalate(patient: dict, text: str, rule_id: str, label: str, severity: str, result: dict) -> None:
    record = escalations.create(patient, text, "web", rule_id=rule_id, rule_label=label, severity=severity)
    result["escalation"], result["reply"] = {**record, "call_number": care.SUPPORT["emergency_number"]}, care.EMERGENCY_LINE


def _approved_sources(patient: dict) -> list[str]:
    plan = store().first("plans", patient_id=patient["id"], status="approved") or {}
    tasks = store().where("tasks", patient_id=patient["id"])
    return [str(plan.get(key, "")) for key in ("medications", "appointments", "tests")] + [f"{task['title']} {task['detail']} {care.task_time(task)}" for task in tasks]


def guarded(reply: str | None, patient: dict, fallback: str) -> str:
    """The model's reply only if it adds no number and gives no advice; otherwise the fixed line."""
    text = (reply or "").strip()
    if not text or len(text) > 320 or ADVICE.search(text) or safety.check(text).action != "continue":
        return fallback
    return text if number_check.check(text, _approved_sources(patient)).passed else fallback


def _checkin_context(patient: dict) -> tuple[dict, list[dict]]:
    tasks = sorted(store().where("tasks", lambda task: task["status"] in ("pending", "overdue"), patient_id=patient["id"]), key=lambda task: task["due_at"])[:8]
    plan = store().first("plans", patient_id=patient["id"], status="approved") or {}
    care_plan = {"tasks": [{"id": task["id"], "description": f"{task['title']} {task['detail']}".strip(), "due": care.task_time(task)} for task in tasks],
                 "medicines": [item.get("name") for item in plan.get("medications", [])]}
    history = [{"role": "user" if item["direction"] == "patient" else "assistant", "content": item["original_text"]}
               for item in store().where("messages", patient_id=patient["id"])[-6:]]
    return care_plan, history


def _barrier(patient: dict, kind: str, result: dict) -> None:
    result["barrier"] = care.open_barrier(patient, kind, "web")
    result["reply"] = FIXED["barrier"]


def _did_not_work(patient: dict, actor: str | None, text: str) -> str:
    barrier = store().first("barriers", patient_id=patient["id"], status="option_offered")
    if barrier:
        if barrier_agent.should_escalate(barrier["attempts"]) and not barrier.get("escalation_id"):
            rule = safety.policy("barrier_unresolved")
            record = escalations.create(patient, text, "web", rule_id="barrier_unresolved", rule_label=rule.get("label", "Barrier not resolved"),
                                        severity=rule.get("severity", "amber"), target_id=barrier["id"])
            barrier["escalation_id"], barrier["status"] = record["id"], "escalated"
        else:
            barrier["status"] = "awaiting_response"
    log_event(patient["id"], actor_type="patient", actor_id=actor or patient["name"], source_channel="web", event_type="barrier_update",
              summary="Said the support option did not work.", verification_status="self_reported")
    return "Thank you for telling me. I have told your care team so they can help."


async def handle(patient: dict, payload: dict, actor: str | None = None) -> dict:
    text = str(payload.get("original_text") or "").strip()
    quick = payload.get("quick_reply")
    task = store().get("tasks", payload.get("task_id")) if payload.get("task_id") else care.next_open_task(patient["id"])
    result = {"reply": None, "barrier": None, "escalation": None, "reschedule": None}
    pending = patient.pop("pending_check", None)

    # 1. Safety first, whatever else the message is
    check = safety.check(text)
    if check.escalate:
        _escalate(patient, text, check.rule_id, f"Possible {check.label}", check.severity, result)
        return result
    if check.action == "confirm" and not quick:
        patient["pending_check"] = {"type": "safety", "rule_id": check.rule_id, "label": check.label, "severity": check.severity, "text": text, "at": now_iso()}
        log_event(patient["id"], actor_type="system", actor_id="Safety engine", source_channel="web", event_type="safety_check_asked",
                  summary=f'Mentioned {check.label} with a "no"; asked the patient to confirm.', verification_status="system_recorded")
        result["reply"] = check.confirm_line()
        return result

    # 2. Answer to a question Tomi asked
    answer = _answer(text) if pending and not quick else None
    if pending and answer:
        if pending["type"] == "safety":
            if answer == "yes":
                _escalate(patient, pending["text"], pending["rule_id"], f"Possible {pending['label']}", pending["severity"], result)
            else:
                result["reply"] = FIXED["no_flag"]
        elif pending["type"] == "task_done":
            if answer == "yes":
                care.report_task(patient, store().get("tasks", pending["task_id"]), "done", "web", actor)
                result["reply"] = FIXED["done"]
            else:
                result["reply"] = FIXED["unchanged"]
        return result

    # 3. Buttons the patient tapped
    if quick:
        if quick in barrier_agent.BARRIER_TYPES:
            _barrier(patient, quick, result)
        elif quick == "done":
            care.report_task(patient, task, "done", "web", actor)
            result["reply"] = FIXED["done"]
        elif quick == "not_yet":
            care.report_task(patient, task, "not_yet", "web", actor)
            result["reply"] = FIXED["not_yet"]
        elif quick == "worked":
            barrier = store().first("barriers", patient_id=patient["id"], status="option_offered")
            if barrier:
                barrier["status"] = "resolved_patient_reported"
            log_event(patient["id"], actor_type="patient", actor_id=actor or patient["name"], source_channel="web", event_type="barrier_resolved",
                      summary="Said the support option worked.", verification_status="self_reported")
            result["reply"] = "I am glad it helped. I have noted it."
        elif quick == "did_not_work":
            result["reply"] = _did_not_work(patient, actor, text)
        else:
            result["reply"] = FIXED["received"]
        return result

    # 4. Free text: visit moves are handled directly (the Check-in Agent has no tool for them)
    kind = care.classify(text)
    if kind["kind"] == "reschedule":
        moved = care.request_reschedule(patient, text, "web", text)
        result["reschedule"] = moved
        result["reply"] = ("I have asked the clinic for a new time. Your current visit stays booked until the clinic confirms a new one."
                           if moved else "You have no upcoming visit to move. Your care team can help.")
        return result

    if os.getenv("GROQ_API_KEY"):
        care_plan, history = _checkin_context(patient)
        try:
            proposal = await checkin.run({"message": text, "care_plan": care_plan, "history": history})
        except (GroqError, ValueError) as error:
            log.warning("Check-in Agent unavailable: %s", error)
            proposal = None
        if proposal:
            if proposal["intent"] == "report_barrier":
                _barrier(patient, proposal["barrier_type"], result)
            elif proposal["intent"] == "mark_task_done":
                proposed = store().get("tasks", proposal["task_id"])
                patient["pending_check"] = {"type": "task_done", "task_id": proposed["id"], "at": now_iso()}
                result["reply"] = f"I heard that you have done this: {proposed['title']}. Is that right? Please reply yes or no."
            else:
                result["reply"] = guarded(proposal["reply_draft"], patient, FIXED["received"])
            log_event(patient["id"], actor_type="agent", actor_id="Check-in Agent", source_channel="web", event_type="checkin_proposal",
                      summary=f"Read the message as: {proposal['intent'].replace('_', ' ')}"
                              f"{' (needs the patient to confirm)' if proposal['requires_confirmation'] else ''}.", verification_status="system_recorded")
            return result

    # 5. No model: simple word matching
    if kind["kind"] == "barrier":
        _barrier(patient, kind["type"], result)
    elif kind["kind"] == "done" and task:
        patient["pending_check"] = {"type": "task_done", "task_id": task["id"], "at": now_iso()}
        result["reply"] = f"I heard that you have done this: {task['title']}. Is that right? Please reply yes or no."
    elif kind["kind"] == "not_yet":
        care.report_task(patient, task, "not_yet", "web", actor)
        result["reply"] = FIXED["not_yet"]
    else:
        result["reply"] = FIXED["received"]
    return result
