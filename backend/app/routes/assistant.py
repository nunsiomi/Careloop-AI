"""Clinician Assistant routes (docs/api_shapes.md, "Care-team assistant")."""

from fastapi import APIRouter, Body, Request

from app.routes.deps import patient_for, require_staff
from app.services import assistant

router = APIRouter()


@router.post("/assistant/drafts")
async def draft(request: Request, body: dict = Body(default={})):
    actor = require_staff(request)
    return {"draft": await assistant.draft_with_model(body.get("text", ""), body.get("patient_id"), actor.facility, body.get("history"))}


@router.post("/assistant/apply")
def apply(request: Request, body: dict = Body(default={})):
    actor = require_staff(request)
    patient = patient_for(actor, body.get("patient_id", ""))
    return assistant.apply(patient, body.get("actions") or [], actor.name)
