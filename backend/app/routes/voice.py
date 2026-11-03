"""Calls, browser voice, the Tomi worker's routes, and the demo-only routes."""

from pathlib import Path

from fastapi import APIRouter, Body, Depends, Request

from app import seed
from app.db import store
from app.routes.deps import patient_for, record_for, require_any, require_patient, require_staff, require_worker, scoped
from app.services import care, voice
from app.services.activity_log import log_event
from app.util import ApiError, make_id, now_iso

router = APIRouter()
worker = APIRouter(dependencies=[Depends(require_worker)])
SAMPLES = Path(__file__).resolve().parents[3] / "data" / "sample_discharges"


def _require_demo() -> None:
    if not voice.demo_enabled():
        raise ApiError("Not found.", 404)


# ----- calls

@router.get("/calls")
def list_calls(request: Request):
    calls = sorted(scoped("calls", require_staff(request)), key=lambda item: item["started_at"], reverse=True)
    return {"calls": [voice.public_call(voice.advance_call(item)) for item in calls]}


@router.get("/patients/{patient_id}/calls")
def list_patient_calls(patient_id: str, request: Request):
    calls = sorted(scoped("calls", require_any(request), patient_id), key=lambda item: item["started_at"], reverse=True)
    return {"calls": [voice.public_call(voice.advance_call(item)) for item in calls]}


@router.get("/calls/{call_id}")
def get_call(call_id: str, request: Request):
    return {"call": voice.public_call(voice.advance_call(record_for(require_staff(request), "calls", call_id, "Call")))}


@router.post("/calls/outbound")
async def request_outbound_call(request: Request, body: dict = Body(default={})):
    actor = require_staff(request)
    patient = patient_for(actor, body.get("patient_id", ""))
    if "voice" not in patient.get("channels", []):
        raise ApiError(f"{patient['name']} has not agreed to phone calls.", 403)
    call = store().add("calls", {"id": make_id("c"), "patient_id": patient["id"], "direction": "outbound", "channel": "phone", "status": "initiated",
                                 "verification_state": "pending", "language": patient["language"], "started_at": now_iso(), "ended_at": None, "outcome": None, "turns": []})
    if not await voice.dial(patient, call):
        store().remove("calls", lambda item: item["id"] == call["id"])
        if not voice.demo_enabled():
            raise ApiError("Phone calls are not set up yet.", 503)
        call = voice.scripted_call(patient, "outbound")
    log_event(patient["id"], actor_type="clinician", actor_id=actor.name, source_channel="voice", event_type="call_requested",
              summary="Outbound Tomi call requested from the dashboard.", verification_status="clinician_verified")
    return {"call": voice.public_call(call)}


# ----- browser voice

@router.post("/voice/sessions")
def create_voice_session(request: Request, body: dict = Body(default={})):
    patient = patient_for(require_patient(request), body.get("patient_id", ""))
    live = voice.livekit_session(patient)
    if live:
        return {"session": live}
    if not voice.demo_enabled():
        raise ApiError("Voice is not available right now.", 503)
    return {"session": voice.scripted_session(patient)}


def _voice_session(request: Request, session_id: str) -> dict:
    actor = require_patient(request)
    session = store().get("voice_sessions", session_id)
    if not session or session["patient_id"] != actor.patient_id:
        raise ApiError("Voice session was not found.", 404)
    return session


@router.post("/voice/sessions/{session_id}/input")
def send_voice_input(session_id: str, request: Request, body: dict = Body(default={})):
    session = _voice_session(request, session_id)
    result = voice.voice_turn(session, body)
    if result["ended"]:
        voice.close_session(session)
    return result


@router.post("/voice/sessions/{session_id}/end")
def end_voice_session(session_id: str, request: Request):
    voice.close_session(_voice_session(request, session_id))
    return {"ok": True}


# ----- Tomi worker (service token only)

@worker.post("/voice/calls")
def worker_start_call(body: dict = Body(default={})):
    return {"call": voice.start_call(body.get("direction", "inbound"), body.get("phone_e164"), body.get("patient_id"))}


@worker.post("/voice/calls/{call_id}/verify-pin")
def worker_verify_pin(call_id: str, body: dict = Body(default={})):
    return voice.verify_pin(call_id, body.get("phone_e164"), str(body.get("pin", "")))


@worker.get("/voice/calls/{call_id}/context")
def worker_context(call_id: str):
    return {"context": voice.call_context(call_id)}


@worker.post("/voice/calls/{call_id}/turns/check")
def worker_check_turn(call_id: str, body: dict = Body(default={})):
    return voice.check_turn(call_id, str(body.get("text", "")))


@worker.post("/voice/calls/{call_id}/turns")
def worker_log_turn(call_id: str, body: dict = Body(default={})):
    voice.log_turn(call_id, body.get("speaker", "patient"), str(body.get("transcript", "")))
    return {}


@worker.post("/voice/calls/{call_id}/task-updates")
def worker_task_update(call_id: str, body: dict = Body(default={})):
    voice.task_update(call_id, body.get("task_id", ""), body.get("status", ""), str(body.get("original_text", "")))
    return {"ok": True}


@worker.post("/voice/calls/{call_id}/barriers")
def worker_barrier(call_id: str, body: dict = Body(default={})):
    voice.barrier(call_id, body.get("type", "other"))
    return {"ok": True}


@worker.post("/voice/calls/{call_id}/questions")
def worker_question(call_id: str, body: dict = Body(default={})):
    voice.question(call_id, str(body.get("original_text", "")))
    return {"ok": True}


@worker.post("/voice/calls/{call_id}/end")
def worker_end(call_id: str, body: dict = Body(default={})):
    voice.end_call(call_id, body.get("outcome", "completed"))
    return {}


# ----- demo only (CARELOOP_DEMO=1); the app shows these only in presenter mode

@router.get("/demo/sample-notes")
def sample_notes(request: Request):
    _require_demo()
    actor = require_staff(request)
    notes = []
    for path in sorted(SAMPLES.glob("*.txt")):
        text = path.read_text(encoding="utf-8").strip().replace(seed.FACILITY, actor.facility)
        notes.append({"id": path.stem, "title": f"Sample: {path.stem.replace('-', ' ').title()}", "text": text})
    return {"notes": notes}


@router.get("/demo/voice-phrases")
def voice_phrases():
    _require_demo()
    return {"phrases": [
        {"label": "Yes, I took it", "transcript": "Yes, I took it", "confidence": 0.93},
        {"label": "Not yet", "transcript": "Not yet", "confidence": 0.9},
        {"label": "I could not buy the medicine", "transcript": "I could not buy the medicine, the pharmacy is out of stock", "confidence": 0.86},
        {"label": "Can I change my visit?", "transcript": "Can I change my visit to a new time?", "confidence": 0.88},
        {"label": "Unclear speech", "transcript": "mm… ba…", "confidence": 0.31, "presenter_only": True},
        {"label": "My chest hurts", "transcript": "My chest hurts and it is hard to breathe", "confidence": 0.74},
    ]}


@router.post("/demo/calls/inbound")
def simulate_inbound_call(request: Request, body: dict = Body(default={})):
    _require_demo()
    patient = patient_for(require_any(request), body.get("patient_id", ""))
    return {"call": voice.public_call(voice.scripted_call(patient, "inbound"))}


@router.post("/demo/patients/{patient_id}/reminders/next")
def send_next_reminder(patient_id: str, request: Request):
    _require_demo()
    patient = patient_for(require_any(request), patient_id)
    task = care.next_open_task(patient_id)
    if not task:
        return {"message": None}
    message = store().add("messages", {"id": make_id("m"), "patient_id": patient_id, "direction": "careloop", "channel": "web",
                                       "original_text": f"Reminder: {task['title']}, {task['detail']}. Did you take it?", "language": patient["language"],
                                       "created_at": now_iso(), "task_id": task["id"], "number_check_passed": True, "answered": False})
    return {"message": message}


@router.post("/demo/reset")
def reset_demo(request: Request):
    _require_demo()
    require_any(request)
    seed.load_into(store())
    return {"ok": True}
