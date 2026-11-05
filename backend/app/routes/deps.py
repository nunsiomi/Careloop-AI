"""Who is asking, and what they may see.

- Staff (cookie `careloop_staff`) see only patients at their own care facility, on every route.
- Patients and caregivers (cookie `careloop_patient`) see only their own (or the person they help's) records.
- The Tomi worker uses `Authorization: Bearer <VOICE_SERVICE_TOKEN>` and can only call /voice/calls/*.
"""

import hmac
import os
import re
from dataclasses import dataclass

from fastapi import Request, Response

from app.db import store
from app.services import identity
from app.util import ApiError

STAFF_COOKIE, PATIENT_COOKIE = "careloop_staff", "careloop_patient"


@dataclass
class Actor:
    kind: str                       # "staff" | "patient" | "caregiver"
    name: str
    session: dict
    facility: str | None = None     # staff only
    patient_id: str | None = None   # patient app only


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def device_name(request: Request) -> str:
    agent = request.headers.get("user-agent", "")
    browser = next((name for pattern, name in [(r"Edg/", "Edge"), (r"Chrome/", "Chrome"), (r"Firefox/", "Firefox"), (r"Safari/", "Safari")] if re.search(pattern, agent)), "Browser")
    system = next((name for pattern, name in [(r"Windows", "Windows"), (r"Android", "Android"), (r"iPhone|iPad", "iPhone"), (r"Mac OS", "Mac"), (r"Linux", "Linux")] if re.search(pattern, agent)), "a computer")
    return f"{browser} on {system}"


def _secure_cookies() -> bool:
    return os.getenv("COOKIE_SECURE", "1" if (os.getenv("APP_URL") or "").startswith("https://") else "0") == "1"


def set_cookie(response: Response, name: str, raw: str, max_age: int) -> None:
    response.set_cookie(name, raw, max_age=max_age, httponly=True, secure=_secure_cookies(), samesite="lax", path="/")


def clear_cookie(response: Response, name: str) -> None:
    response.delete_cookie(name, path="/")


def staff_or_none(request: Request) -> Actor | None:
    session = identity.staff_session(request.cookies.get(STAFF_COOKIE))
    user = store().get("staff", session["user_id"]) if session else None
    return Actor("staff", user["name"], session, facility=user["facility"]) if user else None


def patient_or_none(request: Request) -> Actor | None:
    session = identity.patient_session(request.cookies.get(PATIENT_COOKIE))
    return Actor(session["kind"], session["user_name"], session, patient_id=session["patient_id"]) if session else None


def require_staff(request: Request) -> Actor:
    actor = staff_or_none(request)
    if not actor:
        raise ApiError("Your session has ended. Sign in again.", 401)
    return actor


def require_patient(request: Request) -> Actor:
    actor = patient_or_none(request)
    if not actor:
        raise ApiError("Your session has ended. Sign in again.", 401)
    return actor


def require_any(request: Request) -> Actor:
    actor = staff_or_none(request) or patient_or_none(request)
    if not actor:
        raise ApiError("Your session has ended. Sign in again.", 401)
    return actor


def patient_for(actor: Actor, patient_id: str) -> dict:
    """The patient record, if this person may see it. Same 404 for 'missing' and 'not yours'."""
    patient = store().get("patients", patient_id)
    allowed = patient and (patient.get("facility") == actor.facility if actor.kind == "staff" else patient["id"] == actor.patient_id)
    if not allowed:
        raise ApiError("Patient was not found.", 404)
    return patient


def facility_patient_ids(actor: Actor) -> set[str]:
    if actor.kind != "staff":
        return {actor.patient_id}
    return {item["id"] for item in store().where("patients", facility=actor.facility)}


def scoped(collection: str, actor: Actor, patient_id: str | None = None) -> list[dict]:
    """Records of one collection this person may see, optionally for one patient."""
    if patient_id:
        patient_for(actor, patient_id)
        return store().where(collection, patient_id=patient_id)
    ids = facility_patient_ids(actor)
    return [item for item in store().all(collection) if item.get("patient_id") in ids]


def record_for(actor: Actor, collection: str, record_id: str, what: str) -> dict:
    record = store().get(collection, record_id)
    if not record or record.get("patient_id") not in facility_patient_ids(actor):
        raise ApiError(f"{what} was not found.", 404)
    return record


def require_worker(request: Request) -> None:
    expected = os.getenv("VOICE_SERVICE_TOKEN") or ""
    given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not expected or not hmac.compare_digest(given, expected):
        raise ApiError("Not allowed.", 401)
