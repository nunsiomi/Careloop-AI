"""Shared Pydantic models: patient, plan, task, CareEvent, InboundEvent, AgentResult, ApprovedResponse."""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# ---------- Care plan (docs/api_shapes.md, "Plan"; owners Mary + Olamide) ----------
# Every value must come from the source note. An empty string means "not in the note";
# the Plan Verifier flags it, and the clinician fills it in before approving.

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
ISO_DATE = r"^(\d{4}-\d{2}-\d{2})?$"


class PlanMedication(BaseModel):
    name: str = ""            # medicine, strength and form as written: "Amlodipine 5 mg tablet"
    dose: str = ""            # amount each time: "1 tablet"
    frequency: str = ""       # "Every morning", "Twice daily with food"
    times: list[str] = Field(default_factory=list)
    duration: str = ""
    instructions: str = ""

    @field_validator("times")
    @classmethod
    def check_times(cls, times: list[str]) -> list[str]:
        for time in times:
            if not _matches(HHMM, time):
                raise ValueError(f"time {time!r} is not HH:MM")
        return times


class PlanAppointment(BaseModel):
    what: str = ""
    where: str = ""
    date: str = Field("", pattern=ISO_DATE)
    time: str = Field("", pattern=r"^(([01]\d|2[0-3]):[0-5]\d)?$")


class PlanTest(BaseModel):
    name: str = ""
    where: str = ""
    date: str = Field("", pattern=ISO_DATE)


class PlanDraft(BaseModel):
    medications: list[PlanMedication] = Field(default_factory=list)
    appointments: list[PlanAppointment] = Field(default_factory=list)
    tests: list[PlanTest] = Field(default_factory=list)
    symptoms_to_watch: list[str] = Field(default_factory=list)
    reminder_times: list[str] = Field(default_factory=list)

    @field_validator("reminder_times")
    @classmethod
    def check_reminder_times(cls, times: list[str]) -> list[str]:
        for time in times:
            if not _matches(HHMM, time):
                raise ValueError(f"reminder time {time!r} is not HH:MM")
        return times


class PlanIssue(BaseModel):
    field: str                # "medications[0].frequency", or "medications" for a missing entry
    issue: str
    severity: Literal["high", "medium"]
    source_text: str = ""     # exact substring of the source note, so the dashboard can highlight it


class CarePlanResult(BaseModel):
    """Care Plan Agent output. A draft only: the clinician must review and approve it."""
    plan: PlanDraft
    unresolved: list[PlanIssue]
    deliverable: bool         # False while any high-severity issue is open (all dose ambiguity blocks delivery)


class VerifierResult(BaseModel):
    """Plan Verifier output. 'clean' never replaces clinician approval."""
    verdict: Literal["clean", "flagged"]
    issues: list[PlanIssue]
    deliverable: bool
    model_checked: bool       # False when only the rule checks ran (no key, or the model call failed)


def _matches(pattern: str, value: str) -> bool:
    return re.match(pattern, value) is not None
