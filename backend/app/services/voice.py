"""Voice: live Tomi tokens, the Tomi worker's call routes, and the scripted voice demo.

- Browser voice: a short-lived LiveKit token that dispatches the agent `tomi` (same claims as
  frontend/api/voice/sessions.js). Without LiveKit keys the app gets the scripted session instead.
- Phone calls: `POST /calls/outbound` asks LiveKit to dial when a SIP trunk is set up. Otherwise, with
  CARELOOP_DEMO=1, a scripted call plays out so the dashboard can be shown; without either it answers 503.
- Worker routes (/voice/calls/*): the Tomi worker reports turns, task updates and problems here, and runs every
  patient turn through the safety check first (docs/api_shapes.md, "Voice worker").
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

import httpx

from app.db import store
from app.security import check_secret
from app.safety import rules as safety
from app.services import care, escalations, identity
from app.services.activity_log import log_event
from app.util import ApiError, first_name, make_id, not_found, now_iso

DEMO_PIN = "1234"


def demo_enabled() -> bool:
    return os.getenv("CARELOOP_DEMO", "1") == "1"


# ======================================================================= LiveKit

def _livekit() -> tuple[str, str, str] | None:
    url, key, secret = os.getenv("LIVEKIT_URL"), os.getenv("LIVEKIT_API_KEY"), os.getenv("LIVEKIT_API_SECRET")
    return (url, key, secret) if url and key and secret else None


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _jwt(claims: dict, secret: str) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps(claims, separators=(",", ":")).encode())
    signature = hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{_b64(signature)}"


def livekit_session(patient: dict) -> dict | None:
    """A 15-minute token for one patient's browser voice room, or None when LiveKit is not set up."""
    config = _livekit()
    if not config:
        return None
    url, key, secret = config
    room, identity_name, issued = f"voice-{secrets.token_hex(6)}", f"patient-{secrets.token_hex(4)}", int(time.time())
    language = patient.get("language") or "English"
    claims = {
        "iss": key, "sub": identity_name, "nbf": issued - 10, "exp": issued + 900, "name": first_name(patient["name"]),
        "video": {"room": room, "roomJoin": True, "canPublish": True, "canSubscribe": True, "canPublishData": True},
        "attributes": {"careloop.patient_id": patient["id"]},
        "roomConfig": {"name": room, "maxParticipants": 2, "emptyTimeout": 60,
                       "agents": [{"agentName": "tomi", "metadata": json.dumps({"patient_id": patient["id"], "language": language})}]},
    }
    return {"id": room, "mode": "livekit", "url": url, "token": _jwt(claims, secret), "language": language}


async def dial(patient: dict, call: dict) -> bool:
    """Ask LiveKit to dispatch Tomi to dial the patient (needs LIVEKIT_SIP_TRUNK_ID). False if not set up."""
    config = _livekit()
    if not config or not os.getenv("LIVEKIT_SIP_TRUNK_ID"):
        return False
    url, key, secret = config
    issued = int(time.time())
    admin = _jwt({"iss": key, "sub": "careloop-backend", "nbf": issued - 10, "exp": issued + 60, "video": {"roomCreate": True, "roomAdmin": True, "agent": True}}, secret)
    api = url.replace("wss://", "https://").replace("ws://", "http://").rstrip("/")
    body = {"agentName": "tomi", "room": f"call-{call['id']}",
            "metadata": json.dumps({"call_id": call["id"], "patient_id": patient["id"], "phone_e164": patient["phone_e164"]})}
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(f"{api}/twirp/livekit.AgentDispatchService/CreateDispatch", json=body, headers={"Authorization": f"Bearer {admin}"})
    return response.status_code == 200


# ======================================================================= Tomi worker routes

def start_call(direction: str, phone_e164: str | None, patient_id: str | None) -> dict:
    patient = store().get("patients", patient_id) if patient_id else None
    if direction == "outbound" and patient:
        waiting = store().first("calls", lambda item: item["status"] in ("initiated", "ringing"), patient_id=patient["id"], direction="outbound")
        if waiting:
            waiting["status"] = "answered"
            return {"id": waiting["id"], "language": patient["language"]}
    call = store().add("calls", {
        "id": make_id("c"), "patient_id": patient["id"] if patient else None, "direction": direction,
        "channel": "browser_voice" if direction == "browser" else "phone", "status": "answered",
        "verification_state": "verified" if direction == "browser" and patient else "pending",
        "language": patient["language"] if patient else None, "phone_e164": phone_e164, "started_at": now_iso(), "ended_at": None,
        "outcome": None, "turns": []})
    return {"id": call["id"], "language": call["language"] if direction != "inbound" else None}


def _call(call_id: str) -> dict:
    call = store().get("calls", call_id)
    if not call:
        raise not_found("Call")
    return call


def _verified_patient(call: dict) -> dict:
    if call["verification_state"] != "verified" or not call.get("patient_id"):
        raise ApiError("Verify the caller's PIN first.", 403)
    return care.find_patient(call["patient_id"])


def verify_pin(call_id: str, phone_e164: str | None, pin: str) -> dict:
    call = _call(call_id)
    ok, patient_id, tries_left = identity.verify_voice_pin(phone_e164 or call.get("phone_e164") or "", str(pin))
    if not ok:
        return {"ok": False, "tries_left": tries_left}
    call.update(patient_id=patient_id, verification_state="verified", status="verified")
    call["language"] = call["language"] or store().get("patients", patient_id)["language"]
    return {"ok": True, "patient_id": patient_id}


def call_context(call_id: str) -> dict:
    patient = _verified_patient(_call(call_id))
    plan = store().first("plans", patient_id=patient["id"], status="approved")
    now_text = now_iso()
    visits = sorted(store().where("appointments", lambda item: item["starts_at"] > now_text and item["status"] != "cancelled", patient_id=patient["id"]),
                    key=lambda item: item["starts_at"])
    tasks = sorted(store().where("tasks", lambda item: item["status"] in ("pending", "overdue", "patient_reported_done", "unable"), patient_id=patient["id"]),
                   key=lambda item: item["due_at"])
    return {
        "patient": {"id": patient["id"], "first_name": first_name(patient["name"]), "language": patient["language"], "timezone": patient.get("timezone", "Africa/Lagos")},
        "consent": {"voice": "voice" in patient.get("channels", [])},
        "facility": patient.get("facility"),
        "plan": None if not plan else {
            "status": "approved", "medications": plan.get("medications", []),
            "appointments": [{"what": item["what"], "where": item["where"], "starts_at": item["starts_at"]} for item in visits],
            "tests": [{"name": item["title"], "where": item["detail"], "due_at": item["due_at"]} for item in tasks if item["type"] == "test"],
            "symptoms_to_watch": plan.get("symptoms_to_watch", []),
        },
        "tasks": [{key: item[key] for key in ("id", "title", "detail", "due_at", "status")} for item in tasks][:12],
        "opening": None,
    }


def check_turn(call_id: str, text: str, confidence: float | None = None) -> dict:
    call = _call(call_id)
    patient = _verified_patient(call)
    check = safety.check(text or "", confidence)
    if check.action == "clarify":
        return {"action": "clarify"}
    if check.action == "confirm":  # Tomi's own prompt asks again; the worker only knows continue or escalate
        log_event(patient["id"], actor_type="system", actor_id="Safety engine", source_channel="voice", event_type="safety_check_asked",
                  summary=f'Mentioned {check.label} with a "no" during a call.', verification_status="system_recorded")
    if not check.escalate:
        return {"action": "continue"}
    escalation = escalations.create(patient, text, "voice", rule_id=check.rule_id, rule_label=f"Possible {check.label}", severity=check.severity, call_id=call["id"])
    call["escalation_id"] = escalation["id"]
    return {"action": "escalate", "escalation": {"id": escalation["id"], "call_number": care.SUPPORT["emergency_number"]}}


def log_turn(call_id: str, speaker: str, transcript: str) -> None:
    _call(call_id)["turns"].append({"speaker": "tomi" if speaker == "tomi" else "patient", "transcript": transcript, "english": None,
                                    "confidence": None, "confirmed": None, "keypad": None, "at": now_iso()})


def task_update(call_id: str, task_id: str, status: str, original_text: str) -> None:
    call = _call(call_id)
    patient = _verified_patient(call)
    task = store().first("tasks", id=task_id, patient_id=patient["id"])
    if not task:
        raise not_found("Task")
    care.report_task(patient, task, {"done": "done", "not_done": "not_yet", "unable": "unable"}.get(status, "not_yet"), "voice")


def barrier(call_id: str, kind: str) -> None:
    patient = _verified_patient(_call(call_id))
    mapped = {"distance": "transport", "no_helper": "understanding", "other": "understanding"}.get(kind, kind)
    care.open_barrier(patient, mapped, "voice")


def question(call_id: str, original_text: str) -> None:
    patient = _verified_patient(_call(call_id))
    log_event(patient["id"], actor_type="patient", actor_id=patient["name"], source_channel="voice", event_type="question_for_care_team",
              summary=f'Asked the care team: "{original_text}"', verification_status="self_reported")


def end_call(call_id: str, outcome: str) -> None:
    call = _call(call_id)
    words = {"completed": "Check-in completed", "escalated": "Escalation created", "unverified": "Not verified", "not_reached": "No answer"}
    call.update(status="failed" if outcome == "not_reached" else "completed", ended_at=now_iso(), outcome=words.get(outcome, outcome))
    if call["verification_state"] == "pending":
        call["verification_state"] = "not_reached" if outcome == "not_reached" else "unverified"
    if call.get("patient_id"):
        log_event(call["patient_id"], actor_type="system", actor_id="Tomi", source_channel="voice", event_type="call_completed",
                  summary=f"{'Browser voice session' if call['channel'] == 'browser_voice' else 'Call'} ended. {call['outcome']}.", verification_status="provider_status")


# ======================================================================= scripted voice and calls (demo)

KEYPAD = {
    "verify": [],
    "task": [{"key": "1", "label": "Yes, I did"}, {"key": "2", "label": "Not yet"}, {"key": "3", "label": "I have a problem"}],
    "confirm": [{"key": "1", "label": "Yes, that is right"}, {"key": "2", "label": "No"}],
    "menu": [{"key": "1", "label": "Report a problem"}, {"key": "2", "label": "My next visit"}, {"key": "3", "label": "End"}],
    "reschedule": [{"key": "1", "label": "Yes, ask for a new time"}, {"key": "2", "label": "No"}],
}
GREETING = "Hello, this is Tomi, an automated assistant from your care team."
MENU_PROMPT = "Is there anything else? Press 1 to report a problem, 2 for your next visit, or 3 to end."


def _say(session: dict, text: str, state: str, **extra) -> dict:
    session["state"] = state
    turn = {"speaker": "tomi", "transcript": text, "at": now_iso()}
    session["turns"].append(turn)
    return {"turns": [turn], "state": state, "keypad": KEYPAD.get(state, []), "ended": state == "ended", **extra}


def task_question(task: dict | None) -> str:
    if not task:
        return "You have nothing due right now."
    if task["type"] == "medication":
        return f"Your medicine {task['title']}, {task['detail']}, is due at {care.task_time(task)}. Have you taken it? Press 1 for yes, 2 for not yet, or 3 for a problem."
    return f"{task['title']} is due. Have you done it? Press 1 for yes, 2 for not yet, or 3 for a problem."


def scripted_session(patient: dict) -> dict:
    session = store().add("voice_sessions", {"id": make_id("vs"), "patient_id": patient["id"], "channel": "browser_voice", "state": "greeting",
                                             "turns": [], "verified": False, "started_at": now_iso(), "closed": False})
    return {"id": session["id"], "mode": "mock", "language": patient["language"]}


def voice_turn(session: dict, payload: dict | None) -> dict:
    patient = care.find_patient(session["patient_id"])
    payload = payload or {}
    raw, digit = str(payload.get("transcript") or "").strip(), payload.get("digit")
    confidence = payload.get("confidence") if payload.get("confidence") is not None else (1 if digit else 0.9)
    if raw or digit:
        session["turns"].append({"speaker": "patient", "transcript": f"Pressed {digit}" if digit else raw, "confidence": confidence, "keypad": bool(digit), "at": now_iso()})
    tasks = lambda: store().get("tasks", session.get("task_id"))

    if session["state"] == "greeting":
        return _say(session, f"{GREETING} To keep your details private, please enter your 4-digit PIN.", "verify", pin_required=True)
    if session["state"] == "verify":
        pin = str(payload.get("pin") or raw)
        if check_secret(pin, patient.get("pin_hash")):
            session["verified"] = True
            task = care.next_open_task(patient["id"])
            session["task_id"] = task["id"] if task else None
            return _say(session, f"Thank you, {first_name(patient['name'])}. {task_question(task)}", "task" if task else "menu")
        session["pin_attempts"] = session.get("pin_attempts", 0) + 1
        if session["pin_attempts"] >= 3:
            log_event(patient["id"], actor_type="system", actor_id="Tomi", source_channel=session["channel"], event_type="verification_failed",
                      summary="Identity not verified after 3 PIN attempts. No details shared.", verification_status="system_recorded")
            return _say(session, "I could not confirm who you are, so I cannot share details. Please contact your care team. Goodbye.", "ended")
        return _say(session, "That PIN did not match. Please try again.", "verify", pin_required=True)

    intent = None if digit else care.classify(raw)
    check = safety.check(raw, None if digit else confidence)
    if check.escalate:
        escalation = escalations.create(patient, raw, session["channel"], rule_id=check.rule_id, rule_label=f"Possible {check.label}",
                                        severity=check.severity, call_id=session["id"], confidence=confidence)
        session["escalation_id"] = escalation["id"]
        return _say(session, care.EMERGENCY_LINE, "ended", escalation={"id": escalation["id"], "call_number": care.SUPPORT["emergency_number"]})
    if check.action == "confirm":
        return _say(session, check.confirm_line(), session["state"])
    if check.action == "clarify":
        return _say(session, "I am not sure I understood. Please say it again, or use the keypad.", session["state"])

    kind = intent["kind"] if intent else None
    if session["state"] == "task":
        choice = digit or {"done": "1", "not_yet": "2", "barrier": "3", "problem": "3"}.get(kind)
        if choice == "1":
            return _say(session, "I heard that you took it. Is that right? Press 1 for yes, or 2 for no.", "confirm")
        if choice == "2":
            care.report_task(patient, tasks(), "not_yet", session["channel"])
            return _say(session, f"Okay. I will remind you again later. {MENU_PROMPT}", "menu")
        if choice == "3":
            barrier_record = care.open_barrier(patient, (intent or {}).get("type", "stock"), session["channel"])
            option = barrier_record["options"][0]
            return _say(session, f"Thank you for telling me. Your care team shared this option: {option['name']}, {option['distance']}. Phone {option['phone']}. {option['note']} {MENU_PROMPT}",
                        "menu", barrier=barrier_record)
        if kind == "reschedule":
            return _start_reschedule(session, patient)
        return _say(session, "I did not catch that. Press 1 for yes, 2 for not yet, or 3 for a problem.", "task")
    if session["state"] == "confirm":
        if digit == "1" or kind == "done":
            care.report_task(patient, tasks(), "done", session["channel"])
            return _say(session, f"Thank you. I have noted it. {MENU_PROMPT}", "menu")
        return _say(session, f"Okay, let us try again. {task_question(tasks())}", "task")
    if session["state"] == "reschedule":
        if digit == "1" or kind == "done":
            moved = care.request_reschedule(patient, "Asked by voice for a new time", session["channel"], raw or "Pressed 1")
            return _say(session, "I have asked the clinic for a new time. Your current visit stays booked until the clinic confirms. Goodbye for now."
                        if moved else "You have no upcoming visit to move. Goodbye for now.", "ended")
        return _say(session, f"Okay. Your visit stays as it is. {MENU_PROMPT}", "menu")
    if digit == "1" or kind in ("barrier", "problem"):
        barrier_record = care.open_barrier(patient, (intent or {}).get("type", "understanding"), session["channel"])
        option = barrier_record["options"][0]
        return _say(session, f"Thank you. Your care team shared this option: {option['name']}. Phone {option['phone']}. {option['note']} "
                    "Is there anything else? Press 2 for your next visit, or 3 to end.", "menu", barrier=barrier_record)
    if digit == "2" or kind == "reschedule":
        return _start_reschedule(session, patient)
    if digit == "3":
        return _say(session, "Thank you for talking with me. Goodbye.", "ended")
    return _say(session, "I did not catch that. Press 1 to report a problem, 2 for your next visit, or 3 to end.", "menu")


def _start_reschedule(session: dict, patient: dict) -> dict:
    now_text = now_iso()
    upcoming = sorted(store().where("appointments", lambda item: item["starts_at"] > now_text and item["status"] != "cancelled", patient_id=patient["id"]),
                      key=lambda item: item["starts_at"])
    if not upcoming:
        return _say(session, "You have no upcoming visit booked. Is there anything else? Press 1 to report a problem, or 3 to end.", "menu")
    visit = upcoming[0]
    when = care.local(visit["starts_at"]).strftime("%A %d %B, %H:%M").replace(" 0", " ")
    if visit["status"] == "reschedule_requested":
        return _say(session, f"Your visit is {visit['what']} at {visit['where']}, {when}. You already asked for a new time. The clinic will confirm. "
                    "Is there anything else? Press 1 to report a problem, or 3 to end.", "menu")
    return _say(session, f"Your next visit is {visit['what']} at {visit['where']}, {when}. Do you want to ask for a new time? Press 1 for yes, or 2 for no.", "reschedule")


def close_session(session: dict) -> None:
    if session.get("closed"):
        return
    session["closed"] = True
    patient = care.find_patient(session["patient_id"])
    outcome = "Escalation created" if session.get("escalation_id") else "Check-in completed" if session.get("verified") else "Not verified"
    store().add("calls", {
        "id": make_id("c"), "patient_id": patient["id"], "direction": "browser", "channel": session["channel"], "status": "completed",
        "verification_state": "verified" if session.get("verified") else "unverified", "language": patient["language"], "started_at": session["started_at"],
        "ended_at": now_iso(), "outcome": outcome,
        "turns": [{"speaker": turn["speaker"], "transcript": turn["transcript"], "english": None, "confidence": turn.get("confidence"), "confirmed": None,
                   "keypad": turn.get("keypad")} for turn in session["turns"]]})
    log_event(patient["id"], actor_type="system", actor_id="Tomi", source_channel=session["channel"], event_type="call_completed",
              summary=f"Browser voice session ended. {outcome}.", verification_status="provider_status")


def _outbound_script(patient: dict) -> list[dict]:
    task = care.next_open_task(patient["id"])
    return [
        {"t": 0, "status": "initiated"}, {"t": 2.5, "status": "ringing"}, {"t": 6, "status": "answered"},
        {"t": 7, "turn": {"speaker": "tomi", "transcript": f"{GREETING} To keep your details private, please enter your PIN."}},
        {"t": 10, "status": "verified", "verification_state": "verified", "turn": {"speaker": "patient", "transcript": "PIN entered", "keypad": True, "confirmed": True}},
        {"t": 11.5, "turn": {"speaker": "tomi", "transcript": f"Thank you. {task_question(task)}"}},
        {"t": 15, "turn": {"speaker": "patient", "transcript": "Yes, I took it.", "confidence": 0.92}},
        {"t": 16.5, "turn": {"speaker": "tomi", "transcript": "I heard that you took it. Is that right?"}},
        {"t": 19, "turn": {"speaker": "patient", "transcript": "Pressed 1", "keypad": True, "confirmed": True}},
        {"t": 20.5, "turn": {"speaker": "tomi", "transcript": "Thank you. I have noted it. Goodbye."}},
        {"t": 22.5, "status": "completed", "outcome": "Task reported" if task else "Check-in completed", "report_task_id": task["id"] if task else None},
    ]


def _inbound_script() -> list[dict]:
    return [
        {"t": 0, "status": "ringing"}, {"t": 2, "status": "answered"},
        {"t": 3, "turn": {"speaker": "tomi", "transcript": f"{GREETING} Please enter your PIN."}},
        {"t": 6, "status": "verified", "verification_state": "verified", "turn": {"speaker": "patient", "transcript": "PIN entered", "keypad": True, "confirmed": True}},
        {"t": 7.5, "turn": {"speaker": "tomi", "transcript": "You can press 1 for your tasks, 2 to report a problem, 3 for your visits, or 4 for your care team."}},
        {"t": 10.5, "turn": {"speaker": "patient", "transcript": "Pressed 3", "keypad": True}},
        {"t": 12, "turn": {"speaker": "tomi", "transcript": "Your next visit is booked. I will send the details by email."}},
        {"t": 14.5, "status": "completed", "outcome": "Visit details requested"},
    ]


def scripted_call(patient: dict, direction: str) -> dict:
    call = store().add("calls", {
        "id": make_id("c"), "patient_id": patient["id"], "direction": direction, "channel": "phone", "status": "initiated" if direction == "outbound" else "ringing",
        "verification_state": "pending", "language": patient["language"], "started_at": now_iso(), "ended_at": None, "outcome": None, "turns": [],
        "script": _outbound_script(patient) if direction == "outbound" else _inbound_script(), "script_started": time.time(), "script_index": 0})
    return advance_call(call)


def advance_call(call: dict) -> dict:
    if "script" not in call:
        return call
    elapsed = time.time() - call["script_started"]
    while call["script_index"] < len(call["script"]) and call["script"][call["script_index"]]["t"] <= elapsed:
        step = call["script"][call["script_index"]]
        if step.get("status"):
            call["status"] = step["status"]
        if step.get("verification_state"):
            call["verification_state"] = step["verification_state"]
        if step.get("turn"):
            call["turns"].append({"english": None, "confidence": None, "confirmed": None, "keypad": None, **step["turn"]})
        if step.get("status") == "answered":
            log_event(call["patient_id"], actor_type="provider", actor_id="Telephony provider", source_channel="voice", event_type="call_answered",
                      summary=f"{'Outbound' if call['direction'] == 'outbound' else 'Inbound'} call answered.", verification_status="provider_status")
        if step.get("status") == "completed":
            call["ended_at"], call["outcome"] = now_iso(), step["outcome"]
            patient = care.find_patient(call["patient_id"])
            if step.get("report_task_id"):
                care.report_task(patient, store().get("tasks", step["report_task_id"]), "done", "voice")
            log_event(call["patient_id"], actor_type="system", actor_id="Tomi", source_channel="voice", event_type="call_completed",
                      summary=f"Call completed. {step['outcome']}.", verification_status="provider_status")
        call["script_index"] += 1
    if call["script_index"] >= len(call["script"]):
        for key in ("script", "script_started", "script_index"):
            call.pop(key, None)
    return call


def public_call(call: dict) -> dict:
    return care.with_patient({key: value for key, value in call.items() if key not in ("script", "script_started", "script_index", "phone_e164")})
