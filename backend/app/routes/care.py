"""Patients, plans, chat, timeline, visits, barriers, messages and escalations (docs/api_shapes.md, "Endpoints")."""

from fastapi import APIRouter, Body, Request

from app.db import store
from app.routes.deps import patient_for, record_for, require_any, require_patient, require_staff, scoped
from app.security import hash_secret
from app.agents import language
from app.services import care, chat, escalations, outbox, plans
from app.services.activity_log import log_event
from app.util import EMAIL_PATTERN, ApiError, make_id, normalize_phone, now_iso

router = APIRouter()
LANGUAGES = ("Hausa", "Yoruba", "Igbo", "English")


@router.get("/support")
def support():
    return care.SUPPORT


# ----- patients

@router.get("/patients")
def list_patients(request: Request):
    actor = require_staff(request)
    return {"patients": [care.patient_summary(item) for item in store().where("patients", facility=actor.facility)]}


@router.get("/patients/{patient_id}")
def get_patient(patient_id: str, request: Request):
    return {"patient": care.patient_summary(patient_for(require_any(request), patient_id))}


@router.post("/patients")
def create_patient(request: Request, body: dict = Body(default={})):
    actor = require_staff(request)
    name = str(body.get("name") or "").strip()
    phone = normalize_phone(body.get("phone_e164"))
    email = str(body.get("email") or "").strip() or None
    if len(name) < 3:
        raise ApiError("Add the patient's full name.")
    if not phone:
        raise ApiError("Check the mobile number, for example +234 803 123 4567.")
    if email and not EMAIL_PATTERN.match(email):
        raise ApiError("Check the email address, or leave it empty.")
    if store().first("patients", phone_e164=phone) or store().first("caregivers", phone_e164=phone):
        raise ApiError("This mobile number is already linked to someone in CareLoop. Check it with the patient.", 409)
    facility = store().first("facilities", name=actor.facility) or {}
    patient = store().add("patients", {
        "id": make_id("p"), "name": name, "age": body.get("age"), "language": body.get("language") if body.get("language") in LANGUAGES else "English",
        "literacy_level": body.get("literacy_level") or "standard", "caregiver_mode": bool(body.get("caregiver_mode")), "caregiver": None,
        "phone_e164": phone, "email": email, "channels": [], "contact_window": None, "pin_set": False, "pin_hash": None, "consent_at": None,
        "activation_status": "plan_review", "facility": actor.facility, "facility_id": facility.get("id"), "timezone": "Africa/Lagos", "added_by": actor.name,
        "assigned_to": {"id": actor.session["user_id"], "name": actor.name}})
    log_event(patient["id"], actor_type="clinician", actor_id=actor.name, source_channel="dashboard", event_type="patient_created",
              summary="Patient record created with discharge note.", verification_status="clinician_verified")
    return {"patient": care.patient_summary(patient)}


@router.get("/staff")
def list_staff(request: Request):
    """The care team at the signed-in person's facility, for assigning patients."""
    actor = require_staff(request)
    return {"staff": [{"id": user["id"], "name": user["name"], "role": user["role"]} for user in store().where("staff", facility=actor.facility)]}


@router.patch("/patients/{patient_id}/assignment")
def assign_patient(patient_id: str, request: Request, body: dict = Body(default={})):
    actor = require_staff(request)
    patient = patient_for(actor, patient_id)
    staff_id = body.get("staff_id")
    lead = store().first("staff", id=staff_id, facility=actor.facility) if staff_id else None
    if staff_id and not lead:
        raise ApiError("Choose someone from your care team.")
    patient["assigned_to"] = {"id": lead["id"], "name": lead["name"]} if lead else None
    log_event(patient_id, actor_type="clinician", actor_id=actor.name, source_channel="dashboard", event_type="patient_assigned",
              summary=f"Lead clinician set to {lead['name']}." if lead else "Lead clinician removed.", verification_status="clinician_verified")
    return {"patient": care.patient_summary(patient)}


@router.patch("/patients/{patient_id}/profile")
def update_profile(patient_id: str, request: Request, body: dict = Body(default={})):
    actor = require_any(request)
    patient = patient_for(actor, patient_id)
    if body.get("language") in LANGUAGES:
        patient["language"] = body["language"]
    if body.get("literacy_level") in ("basic", "standard", "caregiver"):
        patient["literacy_level"] = body["literacy_level"]
    if "caregiver_mode" in body:
        patient["caregiver_mode"] = bool(body["caregiver_mode"])
    log_event(patient_id, actor_type="clinician" if actor.kind == "staff" else actor.kind, actor_id=actor.name, source_channel="dashboard" if actor.kind == "staff" else "web",
              event_type="profile_updated", summary=f"Preferences updated: {patient['language']}, {patient['literacy_level']} reading.", verification_status="self_reported")
    return {"patient": care.patient_summary(patient)}


CHANNELS = ("web", "voice", "sms", "email")


def _clean_channels(channels) -> list[str]:
    picked = [channel for channel in channels or [] if channel in CHANNELS]
    return ["web", *[channel for channel in picked if channel != "web"]] if picked else ["web"]


@router.post("/patients/{patient_id}/consent")
def record_consent(patient_id: str, request: Request, body: dict = Body(default={})):
    actor = require_patient(request)
    if actor.kind != "patient":
        raise ApiError("Only the patient can agree to how they are contacted.", 403)
    patient = patient_for(actor, patient_id)
    channels = _clean_channels(body.get("channels"))
    email = str(body.get("email") or "").strip()
    if email:
        if not EMAIL_PATTERN.match(email):
            raise ApiError("Check your email address.")
        patient["email"] = email
    if "voice" in channels and body.get("pin") and not patient.get("pin_hash"):
        patient["pin_hash"], patient["pin_set"] = hash_secret(str(body["pin"])), True
    patient.update(channels=channels, contact_window=body.get("contact_window") or patient.get("contact_window"), consent_at=now_iso(),
                   activation_status="active", consent_version=body.get("version") or "v1", consent_scope=body.get("scope") or "patient_follow_up")
    log_event(patient_id, actor_type="patient", actor_id=patient["name"], source_channel="web", event_type="consent_recorded",
              summary=f"Agreed to be contacted by {care.channel_list(channels)}.", verification_status="self_reported")
    outbox.schedule_reminders(patient)
    return {"patient": care.patient_summary(patient)}


@router.patch("/patients/{patient_id}/consent")
def update_consent(patient_id: str, request: Request, body: dict = Body(default={})):
    actor = require_patient(request)
    if actor.kind != "patient":
        raise ApiError(f"Only {actor.session['acting_for_name']} can change these.", 403)
    patient = patient_for(actor, patient_id)
    channels = _clean_channels(body.get("channels"))
    removed = [channel for channel in patient.get("channels", []) if channel not in channels]
    added = [channel for channel in channels if channel not in patient.get("channels", [])]
    patient["channels"] = channels
    if removed:
        outbox.cancel_messages(patient_id, lambda item: item["channel"] in removed, "Not sent. The patient turned this channel off.")
        log_event(patient_id, actor_type="patient", actor_id=patient["name"], source_channel="web", event_type="consent_withdrawn",
                  summary=f"Turned off {care.channel_list(removed)}.", verification_status="self_reported")
    if added:
        log_event(patient_id, actor_type="patient", actor_id=patient["name"], source_channel="web", event_type="consent_recorded",
                  summary=f"Turned on {care.channel_list(added)}.", verification_status="self_reported")
    outbox.schedule_reminders(patient)
    return {"patient": care.patient_summary(patient)}


# ----- plans

@router.post("/patients/{patient_id}/plan")
async def create_plan(patient_id: str, request: Request, body: dict = Body(default={})):
    actor = require_staff(request)
    return {"plan": await plans.create_plan(patient_for(actor, patient_id), body.get("source_note", ""), actor.name)}


@router.get("/patients/{patient_id}/plan")
def get_plan(patient_id: str, request: Request):
    actor = require_any(request)
    patient_for(actor, patient_id)
    plan = store().first("plans", patient_id=patient_id)
    if not plan or (actor.kind != "staff" and plan["status"] != "approved"):
        raise ApiError("Plan was not found.", 404)
    return {"plan": plan, "tasks": sorted(store().where("tasks", patient_id=patient_id), key=lambda item: item["due_at"])}


@router.patch("/plans/{plan_id}")
def update_plan(plan_id: str, request: Request, body: dict = Body(default={})):
    actor = require_staff(request)
    return {"plan": plans.update_plan(record_for(actor, "plans", plan_id, "Plan"), body, actor.name)}


@router.post("/plans/{plan_id}/approve")
async def approve_plan(plan_id: str, request: Request, body: dict = Body(default={})):
    actor = require_staff(request)
    return {"plan": await plans.approve_plan(record_for(actor, "plans", plan_id, "Plan"), bool(body.get("override_issues")), actor.name)}


# ----- chat

@router.get("/patients/{patient_id}/messages")
def get_messages(patient_id: str, request: Request):
    return {"messages": scoped("messages", require_any(request), patient_id)}


async def translate(patient: dict, english: str) -> dict:
    """The reply in the patient's language and reading level (Language Agent), or English if any check fails."""
    names = [task["title"] for task in store().where("tasks", patient_id=patient["id"])]
    plan = store().first("plans", patient_id=patient["id"], status="approved") or {}
    names += [item.get("name", "") for item in plan.get("medications", [])] + [item.get("where", "") for item in plan.get("appointments", [])]
    return await language.run({"text": english, "language": patient["language"], "reading_level": patient.get("literacy_level"),
                               "protected_terms": sorted({name for name in names if name})})


@router.post("/patients/{patient_id}/messages")
async def send_message(patient_id: str, request: Request, body: dict = Body(default={})):
    actor = require_patient(request)
    patient = patient_for(actor, patient_id)
    text = str(body.get("original_text") or "").strip()
    if not text:
        raise ApiError("Type a message first.")
    store().add("messages", {"id": make_id("m"), "patient_id": patient_id, "direction": "patient", "channel": "web", "original_text": text,
                             "language": patient["language"], "created_at": now_iso(), "sender": actor.name})
    if body.get("task_id"):
        prompt = store().first("messages", lambda item: not item.get("answered"), task_id=body["task_id"], patient_id=patient_id)
        if prompt:
            prompt["answered"] = True
    result = await chat.handle(patient, {**body, "original_text": text}, actor.name if actor.kind == "caregiver" else None)
    escalation = {"id": result["escalation"]["id"], "call_number": care.SUPPORT["emergency_number"]} if result["escalation"] else None
    shown = care.emergency_in(patient["language"]) if escalation else await translate(patient, result["reply"])
    reply = store().add("messages", {"id": make_id("m"), "patient_id": patient_id, "direction": "careloop", "channel": "web", "original_text": shown["text"],
                                     "english_text": result["reply"], "language": shown["language"], "confidence": 0.98,
                                     "number_check_passed": shown["number_check_passed"], "uncertainty_flags": shown["uncertainty_flags"], "created_at": now_iso(), **({"barrier": result["barrier"]} if result["barrier"] else {}), **({"escalation": escalation} if escalation else {})})
    if escalation:
        await escalations.send_alerts()  # tell the care team now, not at the next scheduler run
    return {"reply": reply, "barrier": result["barrier"], "escalation": escalation, "reschedule": result["reschedule"]}


# ----- timeline

def _events(actor, patient_id: str | None, limit: int | None) -> dict:
    events = sorted(scoped("events", actor, patient_id), key=lambda item: item["reported_at"], reverse=True)
    return {"events": [care.with_patient(item) for item in (events[:limit] if limit else events)]}


@router.get("/events")
def list_events(request: Request, limit: int | None = None):
    return _events(require_staff(request), None, limit)


@router.get("/patients/{patient_id}/events")
def list_patient_events(patient_id: str, request: Request, limit: int | None = None):
    return _events(require_any(request), patient_id, limit)


# ----- visits

@router.get("/appointments")
def list_appointments(request: Request, patient_id: str | None = None):
    items = sorted(scoped("appointments", require_any(request), patient_id), key=lambda item: item["starts_at"])
    return {"appointments": [care.with_patient(item) for item in items]}


@router.get("/clinic-slots")
def list_slots(request: Request):
    actor = require_staff(request)
    facility = store().first("facilities", name=actor.facility) or {}
    now_text = now_iso()
    slots = [item for item in store().all("clinic_slots") if item.get("facility_id") == facility.get("id") and item["starts_at"] > now_text]
    return {"slots": sorted(slots, key=lambda item: item["starts_at"])}


@router.get("/reschedule-requests")
def list_reschedule_requests(request: Request, status: str | None = None):
    items = [item for item in scoped("reschedule_requests", require_staff(request)) if not status or item["status"] == status]
    return {"requests": [{**care.with_patient(item), "appointment": store().get("appointments", item["appointment_id"])} for item in items]}


@router.post("/appointments/{appointment_id}/reschedule-requests")
def create_reschedule_request(appointment_id: str, request: Request, body: dict = Body(default={})):
    actor = require_patient(request)
    appointment = record_for(actor, "appointments", appointment_id, "Appointment")
    patient = care.find_patient(appointment["patient_id"])
    if appointment["status"] == "reschedule_requested":
        return {"appointment": appointment}
    reason = str(body.get("reason") or "").strip() or "Asked for a new time"
    appointment["status"] = "reschedule_requested"
    item = store().add("reschedule_requests", {"id": make_id("rr"), "appointment_id": appointment_id, "patient_id": patient["id"], "reason": reason,
                                               "original_text": reason, "channel": "web", "requested_at": now_iso(), "status": "pending", "reviewer": None})
    log_event(patient["id"], actor_type=actor.kind, actor_id=actor.name, source_channel="web", event_type="reschedule_requested",
              summary=f"Asked for a new appointment time: {reason}.", verification_status="self_reported")
    return {"request": item, "appointment": appointment}


@router.post("/reschedule-requests/{request_id}/decision")
def decide_reschedule(request_id: str, request: Request, body: dict = Body(default={})):
    actor = require_staff(request)
    item = record_for(actor, "reschedule_requests", request_id, "Request")
    if item["status"] != "pending":
        raise ApiError("This request has already been decided.", 409)
    appointment = store().get("appointments", item["appointment_id"])
    patient = care.find_patient(item["patient_id"])
    if body.get("decision") == "approve":
        slot = store().get("clinic_slots", body.get("slot_id"))
        if not slot:
            raise ApiError("Slot was not found.", 404)
        if slot["reserved_count"] >= slot["capacity"]:
            raise ApiError("That slot was just taken. Choose another time.", 409)
        slot["reserved_count"] += 1
        old_time = appointment["starts_at"]
        appointment["status"] = "cancelled"
        replacement = store().add("appointments", {**appointment, "id": make_id("a"), "starts_at": slot["starts_at"], "where": slot["where"],
                                                   "status": "rescheduled", "replaces": appointment["id"]})
        item["status"] = "approved"
        outbox.cancel_messages(patient["id"], lambda message: message.get("appointment_id") == appointment["id"], "Not sent. The visit was moved.")
        for channel in outbox.notifications.message_channels(patient):
            outbox.queue_message(patient, channel=channel, template="visit_moved", appointment_id=replacement["id"], created_by=actor.name)
        outbox.schedule_reminders(patient)
        fmt = lambda value: care.local(value).strftime("%d %b, %H:%M").lstrip("0")
        log_event(patient["id"], actor_type="clinician", actor_id=actor.name, source_channel="dashboard", event_type="appointment_rescheduled",
                  summary=f"Visit moved from {fmt(old_time)} to {fmt(slot['starts_at'])}. Old reminder cancelled, new reminder scheduled.", verification_status="clinician_verified")
    else:
        appointment["status"] = "scheduled"
        item["status"] = "rejected"
        log_event(patient["id"], actor_type="clinician", actor_id=actor.name, source_channel="dashboard", event_type="reschedule_declined",
                  summary="Kept the original visit time. Patient to be told.", verification_status="clinician_verified")
    item["reviewer"] = actor.name
    return {"request": item}


@router.post("/appointments/{appointment_id}/attendance")
def record_attendance(appointment_id: str, request: Request, body: dict = Body(default={})):
    actor = require_staff(request)
    appointment = record_for(actor, "appointments", appointment_id, "Appointment")
    if body.get("status") not in ("attended", "no_show"):
        raise ApiError("Choose attended or did not attend.")
    appointment["status"] = body["status"]
    log_event(appointment["patient_id"], actor_type="clinician", actor_id=actor.name, source_channel="dashboard", event_type="attendance_recorded",
              summary=f"{appointment['what']}: {'attended' if body['status'] == 'attended' else 'did not attend'}.", verification_status="clinician_verified")
    return {"appointment": appointment}


# ----- barriers

@router.get("/barriers")
def list_barriers(request: Request, status: str | None = None):
    items = [item for item in scoped("barriers", require_staff(request)) if status != "open" or not item["status"].startswith("resolved")]
    return {"barriers": [care.with_patient(item) for item in items]}


# ----- reminders and messages

GROUPS = {"upcoming": ["scheduled"], "sent": ["sent", "delivered"], "problem": ["failed"], "cancelled": ["cancelled"]}


@router.get("/notifications")
def list_notifications(request: Request, patient_id: str | None = None, status: str | None = None):
    items = [item for item in scoped("notifications", require_any(request), patient_id) if not status or item["status"] in GROUPS.get(status, [])]
    items.sort(key=lambda item: item["scheduled_for"], reverse=status != "upcoming")
    return {"notifications": [care.with_patient({key: value for key, value in item.items() if key != "provider_id"}) for item in items]}


@router.get("/patients/{patient_id}/message-templates")
def list_message_templates(patient_id: str, request: Request):
    patient = patient_for(require_staff(request), patient_id)
    return {"templates": [{"id": template, "title": outbox.notifications.TEMPLATES[template][0], "body": outbox.notifications.render(template, patient, "sms")[1]}
                          for template in outbox.MANUAL_TEMPLATES]}


@router.post("/notifications")
def send_patient_message(request: Request, body: dict = Body(default={})):
    actor = require_staff(request)
    patient = patient_for(actor, body.get("patient_id", ""))
    channel, template = body.get("channel"), body.get("template")
    if template not in outbox.MANUAL_TEMPLATES:
        raise ApiError("Choose which message to send.")
    if channel not in outbox.notifications.message_channels(patient):
        raise ApiError(f"{patient['name']} has not agreed to {'text messages' if channel == 'sms' else 'email'}.", 403)
    message = outbox.queue_message(patient, channel=channel, template=template, created_by=actor.name)
    log_event(patient["id"], actor_type="clinician", actor_id=actor.name, source_channel="dashboard", event_type="notification_requested",
              summary=f'Sent a "{message["title"]}" {outbox.channel_noun(channel)}.', verification_status="clinician_verified")
    return {"notification": care.with_patient(message)}


@router.post("/notifications/{notification_id}/cancel")
def cancel_notification(notification_id: str, request: Request):
    actor = require_staff(request)
    message = record_for(actor, "notifications", notification_id, "Message")
    if message["status"] != "scheduled":
        raise ApiError("This message has already been sent.", 409)
    message["status"], message["failure_reason"] = "cancelled", f"Cancelled by {actor.name}."
    return {"notification": care.with_patient(message)}


@router.post("/notifications/{notification_id}/retry")
def retry_notification(notification_id: str, request: Request):
    actor = require_staff(request)
    original = record_for(actor, "notifications", notification_id, "Message")
    patient = care.find_patient(original["patient_id"])
    if original["status"] != "failed" or original.get("retried"):
        raise ApiError("This message has already been sent again." if original.get("retried") else "Only a message that was not delivered can be sent again.", 409)
    if original["channel"] not in outbox.notifications.message_channels(patient):
        raise ApiError(f"{patient['name']} has turned this channel off.", 403)
    message = outbox.queue_message(patient, channel=original["channel"], template=original["template"], task_id=original.get("task_id"),
                                   appointment_id=original.get("appointment_id"), created_by=actor.name, retry_of=original["id"])
    original["retried"] = True
    return {"notification": care.with_patient(message)}


# ----- escalations

@router.get("/escalations")
def list_escalations(request: Request, status: str | None = None):
    items = [item for item in scoped("escalations", require_staff(request))
             if not status or (item["status"] != "resolved" if status == "open" else item["status"] == status)]
    return {"escalations": sorted((care.with_patient(item) for item in items), key=lambda item: item["created_at"], reverse=True)}


@router.post("/escalations/{escalation_id}/acknowledge")
def acknowledge_escalation(escalation_id: str, request: Request):
    actor = require_staff(request)
    escalation = record_for(actor, "escalations", escalation_id, "Escalation")
    if escalation["status"] in ("acknowledged", "resolved"):
        return {"escalation": care.with_patient(escalation)}
    escalation["status"] = "acknowledged"
    escalation["history"].append({"status": "acknowledged", "at": now_iso(), "by": actor.name})
    log_event(escalation["patient_id"], actor_type="clinician", actor_id=actor.name, source_channel="dashboard", event_type="escalation_acknowledged",
              summary=f"{escalation['rule_label']}: acknowledged.", verification_status="clinician_verified")
    return {"escalation": care.with_patient(escalation)}


@router.post("/escalations/{escalation_id}/resolve")
def resolve_escalation(escalation_id: str, request: Request, body: dict = Body(default={})):
    actor = require_staff(request)
    escalation = record_for(actor, "escalations", escalation_id, "Escalation")
    note = str(body.get("note") or "").strip() or None
    escalation.update(status="resolved", note=note)
    escalation["history"].append({"status": "resolved", "at": now_iso(), "by": actor.name})
    log_event(escalation["patient_id"], actor_type="clinician", actor_id=actor.name, source_channel="dashboard", event_type="escalation_resolved",
              summary=f"{escalation['rule_label']}: resolved.{f' Note: {note}' if note else ''}", verification_status="clinician_verified")
    return {"escalation": care.with_patient(escalation)}
