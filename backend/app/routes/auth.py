"""Sign-in and accounts (docs/api_shapes.md, "Sign-in and accounts")."""

from fastapi import APIRouter, Body, Request, Response

from app.routes.deps import (PATIENT_COOKIE, STAFF_COOKIE, clear_cookie, client_key, device_name, patient_for, patient_or_none,
                             require_patient, require_staff, set_cookie, staff_or_none)
from app.services import identity
from app.util import ApiError

router = APIRouter()
PATIENT_AGE, STAFF_AGE = 30 * 86400, 12 * 3600


# ----- patients and caregivers

@router.get("/auth/patient/session")
def patient_session(request: Request):
    actor = patient_or_none(request)
    return {"session": identity.patient_session_view(actor.session) if actor else None}


@router.post("/auth/patient/otp")
async def start_phone_sign_in(request: Request, body: dict = Body(default={})):
    return await identity.start_phone_sign_in(body.get("phone"), body.get("via") or "email", client_key(request))


@router.post("/auth/invites/{code}/otp")
async def start_invite_sign_in(code: str, request: Request, body: dict = Body(default={})):
    return await identity.start_invite_sign_in(code, body.get("via") or "email", body.get("phone"), body.get("email"), client_key(request))


@router.post("/auth/patient/otp/{challenge_id}/resend")
async def resend_code(challenge_id: str, body: dict = Body(default={})):
    return await identity.resend_code(challenge_id, body.get("via"))


@router.post("/auth/patient/otp/{challenge_id}/verify")
def verify_code(challenge_id: str, response: Response, body: dict = Body(default={})):
    session, raw = identity.verify_code(challenge_id, str(body.get("code", "")))
    set_cookie(response, PATIENT_COOKIE, raw, PATIENT_AGE)
    return {"session": session}


@router.post("/auth/patient/pin-sign-in")
def pin_sign_in(request: Request, response: Response, body: dict = Body(default={})):
    session, raw = identity.sign_in_with_pin(body.get("phone_e164", ""), str(body.get("pin", "")), client_key(request))
    set_cookie(response, PATIENT_COOKIE, raw, PATIENT_AGE)
    return {"session": session}


@router.post("/auth/patient/pin")
def set_pin(request: Request, body: dict = Body(default={})):
    return {"session": identity.set_pin(require_patient(request).session, str(body.get("pin", "")))}


@router.get("/auth/invites/{code}")
def get_invite(code: str):
    return {"invite": identity.get_invite(code)}


@router.post("/auth/patient/sign-out")
def sign_out_patient(request: Request, response: Response):
    identity.sign_out_patient(request.cookies.get(PATIENT_COOKIE))
    clear_cookie(response, PATIENT_COOKIE)
    return {"ok": True}


@router.get("/patients/{patient_id}/caregivers")
def list_caregivers(patient_id: str, request: Request):
    actor = staff_or_none(request) or require_patient(request)
    patient_for(actor, patient_id)
    return identity.list_caregivers(patient_id)


@router.post("/patients/{patient_id}/caregivers")
async def invite_caregiver(patient_id: str, request: Request, body: dict = Body(default={})):
    actor = require_patient(request)
    if actor.kind != "patient":
        raise ApiError(f"Only {actor.session['acting_for_name']} can invite helpers.", 403)
    patient = patient_for(actor, patient_id)
    return {"invite": await identity.invite_caregiver(patient, body.get("name"), body.get("relation"), body.get("phone"), body.get("email"))}


@router.delete("/patients/{patient_id}/caregivers/{caregiver_id}")
def remove_caregiver(patient_id: str, caregiver_id: str, request: Request):
    actor = require_patient(request)
    if actor.kind != "patient":
        raise ApiError(f"Only {actor.session['acting_for_name']} can remove helpers.", 403)
    patient_for(actor, patient_id)
    identity.remove_caregiver(patient_id, caregiver_id)
    return {"ok": True}


# ----- care team

@router.get("/auth/staff/session")
def staff_session(request: Request):
    actor = staff_or_none(request)
    return {"session": identity.staff_session_view(actor.session) if actor else None}


@router.post("/auth/staff/sign-in")
async def staff_sign_in(request: Request, body: dict = Body(default={})):
    return await identity.staff_sign_in(body.get("email", ""), body.get("password", ""), client_key(request))


@router.post("/auth/staff/mfa/email")
async def resend_staff_code(body: dict = Body(default={})):
    return await identity.resend_staff_code(body.get("mfa_token", ""))


@router.post("/auth/staff/mfa")
def verify_staff_code(request: Request, response: Response, body: dict = Body(default={})):
    session, raw = identity.verify_staff_code(body.get("mfa_token", ""), str(body.get("code", "")), bool(body.get("remember_device")), device_name(request))
    set_cookie(response, STAFF_COOKIE, raw, STAFF_AGE)
    return {"session": session}


@router.post("/auth/staff/password-reset")
async def request_password_reset(request: Request, body: dict = Body(default={})):
    await identity.request_password_reset(body.get("email", ""), client_key(request))
    return {"ok": True}


@router.get("/auth/staff/password-reset/{reset_token}")
def check_reset_token(reset_token: str):
    return identity.check_reset_token(reset_token)


@router.post("/auth/staff/password-reset/{reset_token}")
def reset_password(reset_token: str, response: Response, body: dict = Body(default={})):
    identity.reset_password(reset_token, body.get("password", ""))
    clear_cookie(response, STAFF_COOKIE)
    return {"ok": True}


@router.get("/auth/staff/invites/{invite_token}")
def get_staff_invite(invite_token: str):
    return {"invite": identity.get_staff_invite(invite_token)}


@router.post("/auth/staff/invites/{invite_token}/accept")
def accept_staff_invite(invite_token: str, request: Request, response: Response, body: dict = Body(default={})):
    session, raw = identity.accept_staff_invite(invite_token, body.get("password", ""), device_name(request))
    set_cookie(response, STAFF_COOKIE, raw, STAFF_AGE)
    return {"session": session}


@router.get("/facilities")
def list_facilities():
    return identity.list_facilities()


@router.post("/auth/staff/sign-up")
async def staff_sign_up(request: Request, body: dict = Body(default={})):
    return await identity.staff_sign_up(body, client_key(request))


@router.post("/auth/staff/sign-up/resend")
async def resend_signup_code(body: dict = Body(default={})):
    return await identity.resend_signup_code(body.get("signup_token", ""))


@router.post("/auth/staff/sign-up/verify")
def verify_signup(request: Request, response: Response, body: dict = Body(default={})):
    session, raw = identity.verify_signup(body.get("signup_token", ""), str(body.get("code", "")), device_name(request))
    set_cookie(response, STAFF_COOKIE, raw, STAFF_AGE)
    return {"session": session}


@router.post("/auth/staff/unlock")
def unlock(request: Request, body: dict = Body(default={})):
    return {"session": identity.unlock(require_staff(request).session, body.get("password", ""))}


@router.post("/auth/staff/password")
def change_password(request: Request, body: dict = Body(default={})):
    identity.change_password(require_staff(request).session, body.get("current", ""), body.get("next", ""))
    return {"ok": True}


@router.get("/auth/staff/sessions")
def list_staff_sessions(request: Request):
    return {"sessions": identity.list_staff_sessions(require_staff(request).session)}


@router.post("/auth/staff/sign-out")
def staff_sign_out(request: Request, response: Response, body: dict = Body(default={})):
    actor = staff_or_none(request)
    identity.staff_sign_out(actor.session if actor else None, bool(body.get("everywhere")))
    clear_cookie(response, STAFF_COOKIE)
    return {"ok": True}
