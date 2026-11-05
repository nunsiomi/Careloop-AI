"""Patient chat in the app (doc v2, flow B/C): safety first, then the Check-in Agent's proposal, confirmed by the
patient before anything changes their record.

Order for every message:
1. Safety rules (safety/rules.py). A red flag stops everything: approved emergency line + escalation. A negated
   mention ("no chest pain") is checked once with the patient.
2. A pending question ("Is that right?") is answered with yes or no.
3. Quick replies (buttons the patient tapped) are explicit, so they act at once.
4. Free text goes to the Check-in Agent (Dorcas). Marking a task done waits for the patient's "yes". A barrier
   opens straight away (it only offers an approved contact). Anything else (a question, a hello) goes to Tomi's
   chat agent, which answers from the patient's own plan, can say what a plan medicine is generally for
   (MedlinePlus) and passes other questions to the care team. Every model reply is used only if it passes the
   number check and the advice guard; otherwise a fixed, approved line is sent.
5. Without a model (no GROQ_API_KEY or an error), simple word matching does the same jobs.
"""

import json
import logging
import os
import re

from groq import GroqError

from app.agents import barrier as barrier_agent
from app.agents import checkin, tomi_chat
from app.db import store
from app.safety import number_check
from app.safety import rules as safety
from app.services import briefs, care, drug_info, escalations
from app.services.activity_log import log_event
from app.util import now_iso

log = logging.getLogger("careloop.chat")
YES = re.compile(r"^(yes|yeah|yep|y|correct|that is right|that's right|right|ok|okay|eh|ee|ehen|ehn|i|beeni|bee ni|odi|o di)\b")
# A question to Tomi, in English or in common Hausa, Yoruba and Igbo question words.
QUESTION = re.compile(r"\?\s*$|^\s*(what|when|where|which|who|why|how|is|are|do|does|did|can|could|should|will|tell me|explain|"
                      r"me ne|mene|yaushe|wane|wace|kí ni|ki ni|nígbà wo|nigba wo|níbo|nibo|èló|elo|gịnị|gini|olee|kedu|mgbe ole)\b", re.I)
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
    "passed_on": "I have passed your question to your care team. Someone will get back to you.",
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


def _clock_hours(sources: list[str]) -> set[str]:
    """"09:00" on the plan also allows "9" and "9 am" in a reply."""
    hours = set()
    for hour, _ in re.findall(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", " ".join(sources)):
        hours |= {str(int(hour)), str(int(hour) % 12 or 12)}
    return hours


def guarded(reply: str | None, patient: dict, fallback: str, extra_sources: list[str] | None = None, limit: int = 320) -> str:
    """The model's reply only if it adds no number and gives no advice; otherwise the fixed line."""
    text = re.sub(r"[  ]", " ", reply or "").strip()
    if not text or len(text) > limit or ADVICE.search(text) or safety.check(text).action != "continue":
        return fallback
    sources = _approved_sources(patient) + (extra_sources or [])
    return text if number_check.check(text, sources, _clock_hours(sources)).passed else fallback


async def _tomi_answer(patient: dict, text: str, actor: str | None) -> str | None:
    """Tomi's answer to a question or a hello, from the patient's own plan. None when the model is unavailable."""
    brief = briefs.patient_brief(patient)
    on_plan = [drug_info.clean_name(item["name"]) for item in brief["medicines"]]
    looked_up: list[str] = []
    passed_on: list[str] = []

    async def look_up_medicine(name: str = "") -> dict:
        wanted = drug_info.clean_name(name)
        if not wanted or not any(wanted in item or item in wanted for item in on_plan if item):
            return {"found": False, "note": "This medicine is not on their plan. Pass the question to the care team."}
        info = drug_info.for_patient(await drug_info.look_up(name))
        looked_up.append(json.dumps(info))
        return info

    async def ask_to_move_visit(reason: str = "") -> dict:
        moved = care.request_reschedule(patient, reason or text, "web", text)
        return {"ok": bool(moved), "note": "Asked the clinic for a new time. The current visit stays booked until they confirm."
                if moved else "There is no upcoming visit to move. Offer to pass it to the care team."}

    async def ask_care_team(question: str = "") -> dict:
        question = (question or text).strip()[:500]
        log_event(patient["id"], actor_type="caregiver" if actor and actor != patient["name"] else "patient", actor_id=actor or patient["name"],
                  source_channel="web", event_type="question_for_care_team", summary=f'Asked the care team: "{question}"', verification_status="self_reported")
        passed_on.append(question)
        return {"ok": True, "note": "Passed to the care team. Tell them someone will get back to them."}

    _, history = _checkin_context(patient)
    try:
        reply = await tomi_chat.run({"message": text, "patient": brief, "speaker": actor or patient["name"], "history": history,
                                     "today": care.local(now_iso()).strftime("%A %d %B %Y, %H:%M")},
                                    {"look_up_medicine": look_up_medicine, "ask_care_team": ask_care_team, "ask_to_move_visit": ask_to_move_visit})
    except (GroqError, ValueError) as error:
        log.warning("Tomi chat agent unavailable: %s", error)
        return FIXED["passed_on"] if passed_on else None
    fallback = FIXED["passed_on"] if passed_on else FIXED["received"]
    return guarded(reply, patient, fallback, [json.dumps(brief, ensure_ascii=False), *looked_up], limit=600)


TODAY_QUESTION = re.compile(r"\b(today|this morning|tonight)\b")
VISIT_QUESTION = re.compile(r"\b(next|when)\b.*\b(visit|appointment|clinic)\b")


def _plan_answer(patient: dict, text: str) -> str | None:
    """Without a model: today's plan or the next visit, straight from the record. None for anything else."""
    clean = safety.normalize(text)
    if care.classify(text)["kind"] in ("reschedule", "barrier", "red_flag"):
        return None  # "I could not get my medicine today?" is a problem to solve, not a question about the plan
    brief = briefs.patient_brief(patient)
    if TODAY_QUESTION.search(clean):
        if not brief["today"]:
            return "There is nothing on the plan for today."
        rows = [f"- {task['what']}, {task['due'][-5:]} ({task['status']})" for task in brief["today"]]
        return "Today on the plan:\n" + "\n".join(rows)
    if VISIT_QUESTION.search(clean):
        visit = brief["upcoming_visits"][0] if brief["upcoming_visits"] else None
        return f"The next visit: {visit['what']}, {visit['where']}, {visit['when']}." if visit else "There is no visit booked. Your care team can help."
    return None


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

    # 4. Free text. A question goes straight to Tomi, who answers from the plan (or passes it to the care team).
    if QUESTION.search(safety.normalize(text)):
        answer = await _tomi_answer(patient, text, actor) if os.getenv("GROQ_API_KEY") else None
        if answer in (None, FIXED["received"]):  # no model, or its answer did not pass the guards
            answer = _plan_answer(patient, text) or answer
        if answer:
            result["reply"] = answer
            return result

    # Visit moves are handled directly (the Check-in Agent has no tool for them)
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
                answer = await _tomi_answer(patient, text, actor)
                result["reply"] = answer or guarded(proposal["reply_draft"], patient, FIXED["received"])
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
