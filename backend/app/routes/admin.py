"""Care facility admin: the staff join code, the care team, and new sign-ups. Only the facility's CareLoop admin
(`is_admin`) can use these, and only for their own facility."""

import secrets

from fastapi import APIRouter, Request

from app.db import store
from app.routes.deps import Actor, require_staff
from app.util import ApiError, now_iso

router = APIRouter()


def require_admin(request: Request) -> tuple[Actor, dict, dict]:
    actor = require_staff(request)
    user = store().get("staff", actor.session["user_id"])
    if not user or not user.get("is_admin"):
        raise ApiError("Only your facility's CareLoop admin can open this page.", 403)
    facility = store().first("facilities", name=actor.facility)
    if not facility:
        raise ApiError("Your care facility was not found.", 404)
    return actor, user, facility


def _staff_row(user: dict) -> dict:
    sessions = store().where("staff_sessions", user_id=user["id"])
    last_seen = max((item["last_seen_at"] for item in sessions), default=None)
    return {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"], "is_admin": bool(user.get("is_admin")),
            "joined_at": user.get("created_at"), "last_seen_at": last_seen}


@router.get("/admin/facility")
def facility(request: Request):
    _, _, place = require_admin(request)
    staff = sorted((_staff_row(user) for user in store().where("staff", facility=place["name"])), key=lambda row: row["joined_at"] or "", reverse=True)
    return {"facility": {key: place[key] for key in ("id", "name", "type", "city", "country", "join_code")}, "staff": staff}


@router.post("/admin/join-code")
def new_join_code(request: Request):
    """A new join code; the old one stops working at once. Accounts already made are not affected."""
    _, user, place = require_admin(request)
    prefix = place["join_code"].split("-")[0] if "-" in place["join_code"] else "CL"
    place["join_code"] = f"{prefix}-{secrets.randbelow(9000) + 1000}"
    place["join_code_changed_at"], place["join_code_changed_by"] = now_iso(), user["name"]
    return {"join_code": place["join_code"]}


@router.delete("/admin/staff/{staff_id}")
def remove_staff(staff_id: str, request: Request):
    actor, user, place = require_admin(request)
    target = store().first("staff", id=staff_id, facility=place["name"])
    if not target:
        raise ApiError("That person was not found.", 404)
    if target["id"] == user["id"]:
        raise ApiError("You cannot remove your own account.", 409)
    store().remove("staff", lambda item: item["id"] == staff_id)
    store().remove("staff_sessions", lambda item: item["user_id"] == staff_id)
    for patient in store().where("patients", facility=place["name"]):
        if (patient.get("assigned_to") or {}).get("id") == staff_id:
            patient["assigned_to"] = None
    return {"ok": True, "removed_by": actor.name}
