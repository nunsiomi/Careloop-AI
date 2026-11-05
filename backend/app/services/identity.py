"""Patient, caregiver and staff identity: codes, PINs, passwords, invites and sessions (docs/api_shapes.md,
"Sign-in and accounts"). Ported from frontend/shared/mock-auth.js, without its demo_* fields.

Never reveal whether an account exists: phone sign-in, password reset and sign-up give the same answer either way.
"""

import os
import secrets

from app.adapters.email import send_email
from app.agents import language as language_agent
from app.db import store
from app.security import check_code, check_secret, hash_code, hash_secret, new_session_token, password_problem, rate_limit, session_key
from app.services.activity_log import log_event
from app.services.notifications import greeting, send_code_email, send_sign_in_code
from app.util import (EMAIL_PATTERN, ApiError, first_name, in_seconds, make_id, mask_email, mask_phone, normalize_phone,
                      now_iso, six_digits, token)

CODE_TTL, RESEND_AFTER, MAX_TRIES = 300, 60, 5
STAFF_CODE_TTL = 900
FACILITY_TYPES = [{"id": "hospital", "label": "Hospital"}, {"id": "pharmacy", "label": "Pharmacy"},
                  {"id": "clinic", "label": "Clinic or health centre"}, {"id": "care_home", "label": "Care home"}]
STAFF_ROLES = ["Doctor", "Nurse", "Follow-up nurse", "Pharmacist", "Pharmacy technician", "Carer", "Care coordinator"]


def app_url(path: str = "") -> str:
    return (os.getenv("APP_URL") or "http://localhost:5173").rstrip("/") + path


async def _email_code_or_fail(to: str, code: str, subject: str, text: str) -> None:
    result = await send_code_email(to, code, subject, text)
    if not result.ok:
        raise ApiError("We could not send the email just now. Try again in a minute.", 502)


# ======================================================================= patients and caregivers

def _holder(e164: str) -> dict | None:
    patient = store().first("patients", phone_e164=e164)
    if patient:
        return {"kind": "patient", "patient_id": patient["id"], "caregiver_id": None}
    caregiver = store().first("caregivers", phone_e164=e164)
    if caregiver:
        return {"kind": "caregiver", "patient_id": caregiver["patient_id"], "caregiver_id": caregiver["id"]}
    return None


def holder_by_email(email: str | None) -> dict | None:
    """The patient or caregiver account with this email address (patients sign in by email, decided by Nunsi, 5 Nov 2026)."""
    address = str(email or "").strip().lower()
    if not address:
        return None
    patient = store().first("patients", lambda item: (item.get("email") or "").lower() == address)
    if patient:
        return {"kind": "patient", "patient_id": patient["id"], "caregiver_id": None}
    caregiver = store().first("caregivers", lambda item: (item.get("email") or "").lower() == address)
    if caregiver:
        return {"kind": "caregiver", "patient_id": caregiver["patient_id"], "caregiver_id": caregiver["id"]}
    return None


def _pin_key(holder: dict) -> str:
    """Wrong-PIN counter for one account (a session or a holder: both carry kind, patient_id and caregiver_id)."""
    return f"pin:{holder['kind']}:{holder.get('caregiver_id') or holder['patient_id']}"


def _holder_record(holder: dict | None) -> dict:
    if not holder:
        return {}
    record = store().get("caregivers", holder["caregiver_id"]) if holder["kind"] == "caregiver" else store().get("patients", holder["patient_id"])
    return record or {}


def _challenge_view(challenge: dict) -> dict:
    # The person typed this address, so showing it back (masked) says nothing about whether it has an account.
    return {"challenge_id": challenge["id"], "via": "email", "masked_email": mask_email(challenge["email"]),
            "expires_in": CODE_TTL, "resend_in": RESEND_AFTER}


def _email_address(email: str | None) -> str:
    address = str(email or "").strip()
    if not EMAIL_PATTERN.match(address):
        raise ApiError("Enter your email address, for example name@example.com.")
    rate_limit(f"otp-email:{address.lower()}", 5, 600, "Too many codes for this email address. Wait 10 minutes, then try again.")
    return address


async def _send_challenge_code(challenge: dict) -> None:
    code = six_digits()
    challenge.update(code_hash=hash_code(code), tries=0, expires_at=in_seconds(CODE_TTL), resend_at=in_seconds(RESEND_AFTER))
    if not challenge.get("holder") and challenge["purpose"] != "invite":
        return  # an address with no account: nothing is sent, and the screen says the same as for a known one
    result = await send_sign_in_code(challenge["email"], code, _holder_record(challenge.get("holder")).get("name") or challenge.get("name"))
    if not result.ok and challenge["purpose"] == "invite":  # a failed send to a known address stays silent, like an unknown one
        raise ApiError("We could not send the email just now. Try again in a minute.", 502)


async def start_email_sign_in(email: str | None, client: str = "") -> dict:
    """Sign-in and forgotten PIN: a 6-digit code to the email address on the account."""
    rate_limit(f"otp:{client}", 10, 600)
    address = _email_address(email)
    challenge = store().add("challenges", {"id": token("ch"), "email": address, "via": "email", "purpose": "sign_in",
                                           "holder": holder_by_email(address), "invite_code": None})
    await _send_challenge_code(challenge)
    return _challenge_view(challenge)


async def start_invite_sign_in(code: str, email: str | None = None, client: str = "") -> dict:
    invite = store().get("invites", (code or "").upper())
    if not invite or invite["status"] != "pending":
        raise ApiError("This invite code is not valid or has been used. Ask your care team for a new one.", 404)
    rate_limit(f"otp:{client}", 10, 600)
    address = _email_address(email)
    holder = holder_by_email(address)
    # One account per email address, because the address is how people sign in. A patient's own address on file is fine.
    if holder and not (invite["kind"] == "patient" and holder["kind"] == "patient" and holder["patient_id"] == invite["patient_id"]):
        raise ApiError("This email address is already used for another CareLoop account. Use a different one.", 409)
    name = invite.get("name") if invite["kind"] == "caregiver" else store().get("patients", invite["patient_id"])["name"]
    challenge = store().add("challenges", {"id": token("ch"), "email": address, "via": "email", "purpose": "invite", "holder": None,
                                           "invite_code": invite["code"], "name": name})
    await _send_challenge_code(challenge)
    return _challenge_view(challenge)


async def resend_code(challenge_id: str) -> dict:
    challenge = store().get("challenges", challenge_id)
    if not challenge:
        raise ApiError("This code has expired. Start again.", 410)
    if challenge["resend_at"] > now_iso():
        raise ApiError("Wait a moment before asking for another code.", 429)
    _email_address(challenge["email"])
    await _send_challenge_code(challenge)
    return _challenge_view(challenge)


def _patient_session_view(session: dict) -> dict:
    patient = store().get("patients", session["patient_id"]) or {}
    return {
        "id": session["public_id"], "kind": session["kind"], "patient_id": session["patient_id"], "user_name": session["user_name"],
        "acting_for_name": session["acting_for_name"], "relation": session["relation"], "email": _pin_record(session).get("email"),
        "pin_set": bool(_pin_record(session).get("pin_hash")),
        "consent_needed": session["kind"] == "patient" and not patient.get("consent_at"),
        "idle_lock_minutes": 10, "expires_at": session["expires_at"],
    }


def _pin_record(session: dict) -> dict:
    if session["kind"] == "caregiver":
        return store().get("caregivers", session["caregiver_id"]) or {}
    return store().get("patients", session["patient_id"]) or {}


def _new_patient_session(kind: str, patient: dict, caregiver: dict | None = None) -> tuple[dict, str]:
    raw, key = new_session_token()
    session = store().add("patient_sessions", {
        "id": key, "public_id": token("ps"), "kind": kind, "patient_id": patient["id"], "caregiver_id": caregiver["id"] if caregiver else None,
        "user_name": caregiver["name"] if caregiver else patient["name"], "acting_for_name": patient["name"] if caregiver else None,
        "relation": caregiver.get("relation") if caregiver else None, "expires_at": in_seconds(30 * 86400), "created_at": now_iso(),
    })
    store().counter(_pin_key(session)).update(count=0, locked_until=None)
    return session, raw


def verify_code(challenge_id: str, code: str) -> tuple[dict, str]:
    challenge = store().get("challenges", challenge_id)
    if not challenge or challenge["expires_at"] < now_iso():
        raise ApiError("This code has expired. Ask for a new one.", 410)
    if challenge["tries"] >= MAX_TRIES:
        raise ApiError("Too many wrong codes. Ask for a new one.", 429)
    if not check_code(code, challenge.get("code_hash")):
        challenge["tries"] += 1
        left = MAX_TRIES - challenge["tries"]
        raise ApiError(f"That code is not right. You have {left} {'try' if left == 1 else 'tries'} left." if left > 0 else "Too many wrong codes. Ask for a new one.", 401)
    store().remove("challenges", lambda item: item["id"] == challenge_id)

    if challenge["purpose"] == "invite":
        invite = store().get("invites", challenge["invite_code"])
        if not invite or invite["status"] != "pending":
            raise ApiError("This invite is no longer valid.", 410)
        patient = store().get("patients", invite["patient_id"])
        invite["status"] = "accepted"
        if invite["kind"] == "caregiver":
            caregiver = store().add("caregivers", {
                "id": make_id("cg"), "patient_id": patient["id"], "name": invite["name"], "relation": invite.get("relation") or "Family",
                "phone_e164": invite.get("phone_e164"), "email": challenge["email"],
                "scope": "See the plan, tasks and visits. Report on their behalf.", "added_at": now_iso(), "pin_hash": None})
            log_event(patient["id"], actor_type="caregiver", actor_id=caregiver["name"], source_channel="web", event_type="caregiver_joined",
                      summary=f"{caregiver['name']} ({caregiver['relation']}) joined to help.", verification_status="self_reported")
            session, raw = _new_patient_session("caregiver", patient, caregiver)
        else:
            if not patient.get("consent_at"):
                patient["activation_status"] = "invited"
            patient["email"] = challenge["email"]
            session, raw = _new_patient_session("patient", patient)
    else:
        holder = challenge.get("holder")
        if not holder:
            raise ApiError("This email address is not linked to a CareLoop account. Use the invite your care team sent, or ask them to add you.", 404)
        patient = store().get("patients", holder["patient_id"])
        caregiver = store().get("caregivers", holder["caregiver_id"]) if holder["kind"] == "caregiver" else None
        session, raw = _new_patient_session(holder["kind"], patient, caregiver)
    return _patient_session_view(session), raw


def sign_in_with_pin(email: str, pin: str, client: str = "") -> tuple[dict, str]:
    """PIN on a remembered phone. The phone remembers the account's email address, not a phone number."""
    rate_limit(f"pin:{client}", 20, 600)
    holder = holder_by_email(email)
    if not holder:
        raise ApiError("This phone is not set up. Sign in with a code instead.", 404)
    record = _holder_record(holder)
    guard = store().counter(_pin_key(holder))
    if guard["count"] >= MAX_TRIES:
        raise ApiError("Too many wrong PINs. Sign in with a code to set a new PIN.", 429, locked=True)
    if not check_secret(pin, record.get("pin_hash")):
        guard["count"] += 1
        left = MAX_TRIES - guard["count"]
        raise ApiError(f"That PIN is not right. {left} {'try' if left == 1 else 'tries'} left." if left > 0 else
                       "Too many wrong PINs. Sign in with a code to set a new PIN.", 401, locked=left <= 0)
    guard["count"] = 0
    patient = store().get("patients", holder["patient_id"])
    session, raw = _new_patient_session(holder["kind"], patient, record if holder["kind"] == "caregiver" else None)
    return _patient_session_view(session), raw


def set_pin(session: dict, pin: str) -> dict:
    if not str(pin).isdigit() or len(str(pin)) != 4:
        raise ApiError("Your PIN must be 4 numbers.")
    record = _pin_record(session)
    record["pin_hash"] = hash_secret(pin)
    if session["kind"] == "patient":
        record["pin_set"] = True
    store().counter(_pin_key(session)).update(count=0, locked_until=None)
    return _patient_session_view(session)


def patient_session(raw: str | None) -> dict | None:
    session = store().get("patient_sessions", session_key(raw)) if raw else None
    if not session or session["expires_at"] < now_iso():
        return None
    return session


def patient_session_view(session: dict | None) -> dict | None:
    return _patient_session_view(session) if session else None


def sign_out_patient(raw: str | None) -> None:
    if raw:
        key = session_key(raw)
        store().remove("patient_sessions", lambda item: item["id"] == key)


def get_invite(code: str) -> dict:
    invite = store().get("invites", (code or "").upper())
    if not invite:
        raise ApiError("We could not find that invite code. Check the letters and numbers, or ask your care team.", 404)
    if invite["status"] != "pending":
        raise ApiError("This invite has already been used. Sign in with your email address instead.", 410)
    patient = store().get("patients", invite["patient_id"])
    return {"code": invite["code"], "kind": invite["kind"], "facility": invite["facility"], "invited_by": invite["invited_by"],
            "patient_first_name": first_name(patient["name"]), "caregiver_name": invite.get("name"), "relation": invite.get("relation"),
            "masked_email": mask_email(patient["email"]) if invite["kind"] == "patient" and patient.get("email") else None}


def list_caregivers(patient_id: str) -> dict:
    caregivers = [{key: value for key, value in item.items() if key not in ("phone_e164", "pin_hash")}
                  | {"masked_phone": mask_phone(item["phone_e164"]) if item.get("phone_e164") else None}
                  for item in store().where("caregivers", patient_id=patient_id)]
    invites = [{key: value for key, value in item.items() if key not in ("id", "phone_e164")}
               for item in store().where("invites", patient_id=patient_id, kind="caregiver", status="pending")]
    return {"caregivers": caregivers, "invites": invites}


def _invite_code(prefix: str) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = f"{prefix}-{''.join(secrets.choice(alphabet) for _ in range(4))}"
        if not store().get("invites", code):
            return code


async def invite_caregiver(patient: dict, name: str, relation: str, phone: str, email: str) -> dict:
    if not (name or "").strip():
        raise ApiError("Enter their name.")
    e164 = normalize_phone(phone)
    if not e164:
        raise ApiError("Enter their mobile number. Check the country, then type the number, for example 0803 123 4567.")
    address = str(email or "").strip()
    if not EMAIL_PATTERN.match(address):
        raise ApiError("Enter their email address, so we can send them the invite.")
    code = _invite_code("CG")
    invite = store().add("invites", {"id": code, "code": code, "kind": "caregiver", "patient_id": patient["id"], "name": name.strip(),
                                     "relation": relation or "Family", "facility": patient.get("facility"), "invited_by": patient["name"],
                                     "status": "pending", "phone_e164": e164, "masked_phone": mask_phone(e164), "email": address, "created_at": now_iso()})
    await send_email(address, f"{first_name(patient['name'])} asked you to help with their care",
                     f"{patient['name']} has asked you to help with their care plan on CareLoop.\n\n"
                     f"Your invite code is {code}. Open {app_url('/patient/#/invite/' + code)} to join. The code works once.\n\n"
                     "If you were not expecting this, you can ignore this email.")
    log_event(patient["id"], actor_type="patient", actor_id=patient["name"], source_channel="web", event_type="caregiver_invited",
              summary=f"Invited {name.strip()} ({relation or 'Family'}) to help.", verification_status="self_reported")
    return {key: value for key, value in invite.items() if key not in ("id", "phone_e164")}


def remove_caregiver(patient_id: str, caregiver_id: str) -> None:
    store().remove("caregivers", lambda item: item["id"] == caregiver_id and item["patient_id"] == patient_id)
    store().remove("patient_sessions", lambda item: item.get("caregiver_id") == caregiver_id)
    for invite in store().where("invites", patient_id=patient_id, code=caregiver_id):
        invite["status"] = "cancelled"


async def create_patient_invite(patient: dict) -> dict:
    """After plan approval: an invite code for the patient, emailed when there is an address on file."""
    existing = store().first("invites", patient_id=patient["id"], kind="patient", status="pending")
    if existing:
        return existing
    code = _invite_code("CL")
    invite = store().add("invites", {"id": code, "code": code, "kind": "patient", "patient_id": patient["id"], "facility": patient.get("facility"),
                                     "invited_by": patient.get("added_by") or patient.get("facility"), "status": "pending", "created_at": now_iso()})
    await send_welcome(patient, invite, reminder=False)
    return invite


async def send_welcome(patient: dict, invite: dict, reminder: bool) -> bool:
    """The welcome (or 24-hour reminder) email: in the patient's language when the Language Agent's checks pass,
    always with the English underneath. Generic: it never names a medicine or condition. False if no address."""
    if not patient.get("email"):
        return False
    link = app_url("/patient/#/invite/" + invite["code"])
    opening = ("A reminder: " if reminder else "") + f"{patient.get('facility') or 'Your care team'} has set up CareLoop to help you follow your care plan."
    english = f"Hello {first_name(patient['name'])}. {opening} Your invite code is {invite['code']}. Open {link} to start. The code works once."
    translated = await language_agent.run({"text": english, "language": patient.get("language"), "reading_level": patient.get("literacy_level"),
                                           "protected_terms": [invite["code"], link, first_name(patient["name"])]})
    text = f"{translated['text']}\n\n{english}" if translated["adapted"] else english
    subject = "Reminder: your CareLoop invite" if reminder else "Your care team set up CareLoop for you"
    return (await send_email(patient["email"], subject, text)).ok


# ======================================================================= care team

def _initials(name: str) -> str:
    return "".join(part[0] for part in name.removeprefix("Dr.").strip().split(" ") if part)[:2].upper()


def staff_view(user: dict) -> dict:
    return {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"], "facility": user["facility"],
            "initials": _initials(user["name"]), "is_admin": bool(user.get("is_admin"))}


def _new_staff_session(user: dict, remember: bool, device: str) -> tuple[dict, str]:
    raw, key = new_session_token()
    stamp = now_iso()
    session = store().add("staff_sessions", {"id": key, "public_id": token("ss"), "user_id": user["id"], "device": device, "remember_device": remember,
                                             "signed_in_at": stamp, "last_seen_at": stamp, "expires_at": in_seconds(12 * 3600)})
    return session, raw


def staff_session_view(session: dict | None) -> dict | None:
    if not session:
        return None
    user = store().get("staff", session["user_id"])
    return {"id": session["public_id"], "user": staff_view(user), "remember_device": session["remember_device"],
            "idle_lock_minutes": 15, "expires_at": session["expires_at"]} if user else None


def staff_session(raw: str | None) -> dict | None:
    session = store().get("staff_sessions", session_key(raw)) if raw else None
    if not session or session["expires_at"] < now_iso():
        return None
    session["last_seen_at"] = now_iso()
    return session


def _find_staff(email: str) -> dict | None:
    clean = str(email or "").strip().lower()
    return store().first("staff", lambda item: item["email"].lower() == clean)


async def staff_sign_in(email: str, password: str, client: str = "") -> dict:
    rate_limit(f"staff-sign-in:{client}", 20, 600)
    user = _find_staff(email)
    generic = "That email and password do not match. Check both and try again."
    if user and user.get("locked_until") and user["locked_until"] > now_iso():
        raise ApiError("Too many attempts. Wait one minute or reset your password.", 429)
    if not user or not check_secret(password, user.get("password_hash")):
        if user:
            user["failures"] = user.get("failures", 0) + 1
            if user["failures"] >= MAX_TRIES:
                user["locked_until"], user["failures"] = in_seconds(60), 0
        raise ApiError(generic, 401)
    user["failures"] = 0
    code = six_digits()
    pending = store().add("mfa_tokens", {"id": token("mfa"), "user_id": user["id"], "expires_at": in_seconds(STAFF_CODE_TTL), "tries": 0,
                                         "code_hash": hash_code(code), "resend_at": in_seconds(RESEND_AFTER)})
    await _email_code_or_fail(user["email"], code, "Your CareLoop sign-in code", _code_email(code, user.get("name"), "sign in"))
    return {"mfa_token": pending["id"], "masked_email": mask_email(user["email"]), "resend_in": RESEND_AFTER}


def _code_email(code: str, name: str | None, purpose: str) -> str:
    """Staff codes by email. Same wording as the mock (frontend/shared/mock-auth.js)."""
    if purpose == "sign up":
        lead, other = "Thank you for creating a CareLoop account. Here is your code to confirm your email:", "create a CareLoop account"
    else:
        lead, other = "Here is your code to sign in to CareLoop:", "try to sign in"
    return (f"{greeting(name)}\n\n{lead}\n\n    {code}\n\nIt works for 15 minutes. "
            f"If you did not {other}, you can ignore this email.\n\nThe CareLoop team")


async def resend_staff_code(mfa_token: str) -> dict:
    pending = store().get("mfa_tokens", mfa_token)
    if not pending or pending["expires_at"] < now_iso():
        raise ApiError("Sign-in timed out. Enter your password again.", 410)
    if pending["resend_at"] > now_iso():
        raise ApiError("Wait a moment before asking for another code.", 429)
    code = six_digits()
    pending.update(code_hash=hash_code(code), tries=0, resend_at=in_seconds(RESEND_AFTER))
    user = store().get("staff", pending["user_id"])
    await _email_code_or_fail(user["email"], code, "Your CareLoop sign-in code", _code_email(code, user.get("name"), "sign in"))
    return {"resend_in": RESEND_AFTER}


def verify_staff_code(mfa_token: str, code: str, remember: bool, device: str) -> tuple[dict, str]:
    pending = store().get("mfa_tokens", mfa_token)
    if not pending or pending["expires_at"] < now_iso():
        raise ApiError("Sign-in timed out. Enter your password again.", 410)
    if not check_code(code, pending["code_hash"]):
        pending["tries"] += 1
        if pending["tries"] >= MAX_TRIES:
            store().remove("mfa_tokens", lambda item: item["id"] == mfa_token)
            raise ApiError("Too many wrong codes. Enter your password again.", 429)
        left = MAX_TRIES - pending["tries"]
        raise ApiError(f"That code is not right. Use the code from the newest email. {left} {'try' if left == 1 else 'tries'} left.", 401)
    store().remove("mfa_tokens", lambda item: item["id"] == mfa_token)
    session, raw = _new_staff_session(store().get("staff", pending["user_id"]), remember, device)
    return staff_session_view(session), raw


async def request_password_reset(email: str, client: str = "") -> None:
    rate_limit(f"reset:{client}", 10, 600)
    user = _find_staff(email)
    if not user:
        return  # same answer either way
    raw, key = new_session_token()
    store().add("resets", {"id": key, "user_id": user["id"], "expires_at": in_seconds(1800)})
    await send_email(user["email"], "Reset your CareLoop password",
                     f"Reset your CareLoop password: {app_url('/clinician/#/reset-password/' + raw)}\n\n"
                     "This link works for 30 minutes. If you did not ask for this, ignore this email.")


def _reset(raw: str) -> dict:
    reset = store().get("resets", session_key(raw or ""))
    if not reset or reset["expires_at"] < now_iso():
        raise ApiError("This reset link has expired or was already used. Ask for a new one.", 410)
    return reset


def check_reset_token(raw: str) -> dict:
    return {"email_masked": mask_email(store().get("staff", _reset(raw)["user_id"])["email"])}


def reset_password(raw: str, password: str) -> None:
    reset = _reset(raw)
    user = store().get("staff", reset["user_id"])
    problem = password_problem(password, user["email"])
    if problem:
        raise ApiError(problem)
    user.update(password_hash=hash_secret(password), locked_until=None, failures=0)
    store().remove("resets", lambda item: item["id"] == reset["id"])
    store().remove("staff_sessions", lambda item: item["user_id"] == user["id"])


def get_staff_invite(invite_token: str) -> dict:
    invite = store().get("staff_invites", invite_token)
    if not invite:
        raise ApiError("This invite link is not valid. Ask the person who invited you to send a new one.", 404)
    if invite["status"] != "pending":
        raise ApiError("This invite was already used. Sign in instead.", 410)
    return {key: invite[key] for key in ("name", "email", "role", "facility", "invited_by")}


def _new_staff_user(name: str, email: str, password: str, role: str, facility: dict) -> dict:
    return store().add("staff", {"id": make_id("u"), "name": name, "email": email, "password_hash": hash_secret(password), "role": role,
                                 "facility": facility["name"], "facility_id": facility["id"], "failures": 0, "locked_until": None, "created_at": now_iso()})


def accept_staff_invite(invite_token: str, password: str, device: str) -> tuple[dict, str]:
    invite = store().get("staff_invites", invite_token)
    if not invite or invite["status"] != "pending":
        raise ApiError("This invite is no longer valid.", 410)
    problem = password_problem(password, invite["email"])
    if problem:
        raise ApiError(problem)
    facility = store().first("facilities", name=invite["facility"])
    user = _new_staff_user(invite["name"], invite["email"], password, invite["role"], facility)
    invite["status"] = "accepted"
    session, raw = _new_staff_session(user, False, device)
    return staff_session_view(session), raw


def _shown_join_code(facility: dict) -> dict:
    """CARELOOP_SHOW_JOIN_CODES=1 (for judges and testers) shows the code of the invented sample facilities only,
    so anyone can try staff sign-up. A real facility's code is never returned."""
    from app.seed import FACILITIES
    if os.getenv("CARELOOP_SHOW_JOIN_CODES") == "1" and facility["id"] in {item[0] for item in FACILITIES}:
        return {"demo_join_code": facility["join_code"]}
    return {}


def list_facilities() -> dict:
    facilities = [{**{key: item[key] for key in ("id", "type", "name", "city", "country")}, **_shown_join_code(item)} for item in store().all("facilities")]
    return {"types": FACILITY_TYPES, "facilities": facilities, "roles": STAFF_ROLES}


async def staff_sign_up(body: dict, client: str = "") -> dict:
    clean_email = str(body.get("email") or "").strip().lower()
    name = str(body.get("name") or "").strip()
    facility = store().get("facilities", body.get("facility_id"))
    if len(name) < 3:
        raise ApiError("Enter your full name.")
    if not EMAIL_PATTERN.match(clean_email):
        raise ApiError("Enter an email address, for example amina@gmail.com.")
    if not facility:
        raise ApiError("Choose where you work.")
    rate_limit(f"join:{client}", 10, 600, "Too many wrong facility codes. Wait 10 minutes, then try again.")
    guard = store().counter(f"join:{facility['id']}")
    if guard.get("locked_until") and guard["locked_until"] > now_iso():
        raise ApiError("Too many wrong facility codes. Wait 10 minutes, then try again.", 429)
    if str(body.get("join_code") or "").strip().upper().replace(" ", "") != facility["join_code"]:
        guard["count"] += 1
        if guard["count"] >= MAX_TRIES:
            guard.update(locked_until=in_seconds(600), count=0)
            raise ApiError("Too many wrong facility codes. Wait 10 minutes, then try again.", 429)
        raise ApiError(f"That code is not right for {facility['name']}. Ask your facility's CareLoop admin for it.", 403, field="join_code")
    guard["count"] = 0
    if body.get("role") not in STAFF_ROLES:
        raise ApiError("Choose your role.")
    problem = password_problem(body.get("password"), clean_email)
    if problem:
        raise ApiError(problem)
    if not body.get("confirmed"):
        raise ApiError(f"Confirm that you work at {facility['name']}.")
    existing = bool(_find_staff(clean_email))
    code = six_digits()
    signup = store().add("signups", {"id": token("su"), "name": name, "email": clean_email, "password_hash": hash_secret(body["password"]),
                                     "role": body["role"], "facility_id": facility["id"], "code_hash": hash_code(code), "existing": existing,
                                     "tries": 0, "expires_at": in_seconds(STAFF_CODE_TTL), "resend_at": in_seconds(RESEND_AFTER)})
    await _send_signup_email(signup, code)
    return {"signup_token": signup["id"], "masked_email": mask_email(clean_email), "resend_in": RESEND_AFTER}


async def _send_signup_email(signup: dict, code: str) -> None:
    if signup["existing"]:  # same response either way; only the email itself differs
        await send_email(signup["email"], "Someone tried to create a CareLoop account",
                         "Someone tried to create a CareLoop account with this email address, but you already have one. "
                         f"Sign in instead ({app_url('/clinician/#/sign-in')}), or reset your password if you have forgotten it.")
    else:
        await _email_code_or_fail(signup["email"], code, "Confirm your email for CareLoop", _code_email(code, signup["name"], "sign up"))


async def resend_signup_code(signup_token: str) -> dict:
    signup = store().get("signups", signup_token)
    if not signup or signup["expires_at"] < now_iso():
        raise ApiError("This sign-up has expired. Start again.", 410)
    if signup["resend_at"] > now_iso():
        raise ApiError("Wait a moment before asking for another code.", 429)
    code = six_digits()
    signup.update(code_hash=hash_code(code), tries=0, resend_at=in_seconds(RESEND_AFTER))
    await _send_signup_email(signup, code)
    return {"resend_in": RESEND_AFTER}


def verify_signup(signup_token: str, code: str, device: str) -> tuple[dict, str]:
    signup = store().get("signups", signup_token)
    if not signup or signup["expires_at"] < now_iso():
        raise ApiError("This sign-up has expired. Start again.", 410)
    if signup["tries"] >= MAX_TRIES:
        raise ApiError("Too many wrong codes. Ask for a new one.", 429)
    if signup["existing"] or not check_code(code, signup["code_hash"]):
        signup["tries"] += 1
        left = MAX_TRIES - signup["tries"]
        raise ApiError(f"That code is not right. You have {left} {'try' if left == 1 else 'tries'} left." if left > 0 else "Too many wrong codes. Ask for a new one.", 401)
    store().remove("signups", lambda item: item["id"] == signup_token)
    facility = store().get("facilities", signup["facility_id"])
    user = store().add("staff", {"id": make_id("u"), "name": signup["name"], "email": signup["email"], "password_hash": signup["password_hash"],
                                 "role": signup["role"], "facility": facility["name"], "facility_id": facility["id"], "failures": 0,
                                 "locked_until": None, "created_at": now_iso()})
    session, raw = _new_staff_session(user, False, device)
    return staff_session_view(session), raw


def unlock(session: dict, password: str) -> dict:
    user = store().get("staff", session["user_id"])
    if not check_secret(password, user.get("password_hash")):
        raise ApiError("That password is not right.", 401)
    return staff_session_view(session)


def change_password(session: dict, current: str, new: str) -> None:
    user = store().get("staff", session["user_id"])
    if not check_secret(current, user.get("password_hash")):
        raise ApiError("Your current password is not right.", 401)
    problem = password_problem(new, user["email"])
    if problem:
        raise ApiError(problem)
    user["password_hash"] = hash_secret(new)
    store().remove("staff_sessions", lambda item: item["user_id"] == user["id"] and item["id"] != session["id"])


def list_staff_sessions(session: dict) -> list[dict]:
    return [{"id": item["public_id"], "device": item["device"], "signed_in_at": item["signed_in_at"], "last_seen_at": item["last_seen_at"],
             "current": item["id"] == session["id"]} for item in store().where("staff_sessions", user_id=session["user_id"])]


def staff_sign_out(session: dict | None, everywhere: bool) -> None:
    if session:
        store().remove("staff_sessions", lambda item: item["user_id"] == session["user_id"] if everywhere else item["id"] == session["id"])
