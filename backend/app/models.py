"""Shared Pydantic models: patient, plan, task, CareEvent, InboundEvent, AgentResult, ApprovedResponse."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# ---------- Care plan (docs/api_shapes.md, "Plan"; owners Mary + Olamide) ----------
# Every value must come from the source note. An empty string means "not in the note";
# the Plan Verifier flags it, and the clinician fills it in before approving.

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
ISO_DATE = r"^(\d{4}-\d{2}-\d{2})?$"
TIME_WORDS = {"noon": "12:00", "midday": "12:00", "midnight": "00:00"}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y")


def to_hhmm(value) -> str:
    """Times as people write them ("5pm", "5:00 pm", "17.00", "8") become HH:MM. Anything else is returned
    unchanged, so the check below can say which field to fix."""
    text = re.sub(r"\s+", " ", str(value or "").strip().lower()).replace("a.m.", "am").replace("p.m.", "pm")
    if text in TIME_WORDS:
        return TIME_WORDS[text]
    match = re.fullmatch(r"(\d{1,2})(?:[:.h](\d{2}))?\s*(am|pm)?", text)
    if not match:
        return str(value or "").strip()
    hours, minutes, half = int(match.group(1)), int(match.group(2) or 0), match.group(3)
    if half:
        if not 1 <= hours <= 12:
            return str(value).strip()
        hours = hours % 12 + (12 if half == "pm" else 0)
    return f"{hours:02d}:{minutes:02d}" if hours < 24 and minutes < 60 else str(value).strip()


def to_iso_date(value) -> str:
    """Dates as people write them ("9/11/2026", "9 Nov 2026") become YYYY-MM-DD. Numbers are read day first."""
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", re.sub(r"[\s,]+", " ", str(value or "").strip()))
    for pattern in DATE_FORMATS:
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    return text


def _time_list(value) -> list[str]:
    items = value.split(",") if isinstance(value, str) else (value or [])
    return [to_hhmm(item) for item in items if str(item).strip()]


class PlanMedication(BaseModel):
    name: str = ""            # medicine, strength and form as written: "Amlodipine 5 mg tablet"
    dose: str = ""            # amount each time: "1 tablet"
    frequency: str = ""       # "Every morning", "Twice daily with food"
    times: list[str] = Field(default_factory=list)
    duration: str = ""
    instructions: str = ""

    @field_validator("times", mode="before")
    @classmethod
    def read_times(cls, value) -> list[str]:
        return _time_list(value)

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

    @field_validator("date", mode="before")
    @classmethod
    def read_date(cls, value) -> str:
        return to_iso_date(value)

    @field_validator("time", mode="before")
    @classmethod
    def read_time(cls, value) -> str:
        return to_hhmm(value) if str(value or "").strip() else ""


class PlanTest(BaseModel):
    name: str = ""
    where: str = ""
    date: str = Field("", pattern=ISO_DATE)

    @field_validator("date", mode="before")
    @classmethod
    def read_date(cls, value) -> str:
        return to_iso_date(value)


class PlanDraft(BaseModel):
    medications: list[PlanMedication] = Field(default_factory=list)
    appointments: list[PlanAppointment] = Field(default_factory=list)
    tests: list[PlanTest] = Field(default_factory=list)
    symptoms_to_watch: list[str] = Field(default_factory=list)
    reminder_times: list[str] = Field(default_factory=list)

    @field_validator("reminder_times", mode="before")
    @classmethod
    def read_reminder_times(cls, value) -> list[str]:
        return _time_list(value)

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
