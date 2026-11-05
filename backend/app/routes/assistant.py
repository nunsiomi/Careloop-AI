"""Clinician Assistant routes (docs/api_shapes.md, "Care-team assistant")."""

from fastapi import APIRouter, Body, Request

from app.routes.deps import patient_for, require_staff
from app.services import assistant, welcome

router = APIRouter()


@router.get("/assistant/welcome")
def greet(request: Request, patient_id: str | None = None):
    actor = require_staff(request)
    return {"welcome": welcome.for_staff(actor.name, actor.facility, patient_for(actor, patient_id) if patient_id else None)}


@router.post("/assistant/drafts")
async def draft(request: Request, body: dict = Body(default={})):
    actor = require_staff(request)
    return {"draft": await assistant.draft_with_model(body.get("text", ""), body.get("patient_id"), actor.facility, body.get("history"))}


@router.post("/assistant/apply")
def apply(request: Request, body: dict = Body(default={})):
    actor = require_staff(request)
    patient = patient_for(actor, body.get("patient_id", ""))
    return assistant.apply(patient, body.get("actions") or [], actor.name)
