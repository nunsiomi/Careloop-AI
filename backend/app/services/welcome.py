"""Tomi's welcome: what each assistant says when it opens (decided by Nunsi, 5 Nov 2026).

Every assistant in CareLoop is Tomi. When the patient chat or the dashboard panel opens, Tomi greets the person by
first name, says what she can do there, asks what they would like to ask, and offers a few questions to tap.

- Patients and caregivers get prepared lines in the patient's language (voice/prompts/lines.json, the same file the
  phone calls use). Nothing here is generated, and the questions only name what is on the approved plan.
- Staff get English, with questions built from their own facility's patients.
"""

import json
import re

from app.services import briefs, care, drug_info
from app.services.assistant import ranked_overview
from app.util import now_iso

TITLES = re.compile(r"^(dr|doctor|nurse|pharm|prof|mr|mrs|ms|miss|matron|sister)\.?\s+", re.I)


def first_name(name: str | None) -> str:
    """'Dr. Ada Okafor' -> 'Ada'."""
    clean = TITLES.sub("", str(name or "").strip())
    return clean.split(" ")[0] if clean else ""


def _medicine(names: list[str]) -> str | None:
    """The first medicine name, without strength or form: 'Amlodipine 5 mg tablet' -> 'Amlodipine'."""
    for name in names:
        clean = drug_info.clean_name(name)
        if clean:
            return clean[:1].upper() + clean[1:]
    return None


def _lines(language: str | None) -> dict | None:
    try:
        lines = json.loads(care.LINES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return lines.get(care.LANGUAGE_CODES.get(language or "", "en")) or lines.get("en")


def for_patient(patient: dict, speaker: str) -> dict | None:
    """The chat welcome for the patient, or for their caregiver (greeted by their own name)."""
    lines = _lines(patient.get("language"))
    if not lines:
        return None
    brief = briefs.patient_brief(patient)
    suggestions = [lines["ask_today"]]
    if brief["upcoming_visits"]:
        suggestions.append(lines["ask_visit"])
    medicine = _medicine([item["name"] for item in brief["medicines"] if item.get("name")])
    if medicine:
        suggestions.append(lines["ask_medicine"].format(medicine=medicine))
    hello = lines["chat_hello"].format(first_name=first_name(speaker) or first_name(patient["name"]))
    return {"text": "\n".join([hello, lines["chat_can_do"], lines["chat_ask"]]), "suggestions": suggestions}


def for_staff(name: str, facility: str, patient: dict | None = None) -> dict:
    """The dashboard assistant's welcome, with questions about this facility's patients (or the one selected)."""
    hour = care.local(now_iso()).hour
    part = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
    text = "\n".join([
        f"{part}, {first_name(name) or 'there'}. I am Tomi, your CareLoop assistant.",
        "I can tell you who needs attention and how a patient is doing, look up a medicine, or explain a report you paste in. "
        "I can also draft reminders, visits, email reminders, Tomi calls and notes. Nothing is saved until you confirm.",
        "What would you like to ask?",
    ])
    if patient:
        who = first_name(patient["name"])
        medicine = _medicine([item["name"] for item in briefs.patient_brief(patient)["medicines"] if item.get("name")])
        suggestions = [f"How is {who} doing?", f"What medicines is {who} on?",
                       *([f"What is {medicine.lower()} used for?"] if medicine else []), f"Book {who} a follow-up visit next week"]
        return {"text": text, "suggestions": suggestions}
    rows = ranked_overview(facility)
    suggestions = ["Who needs attention today?"]
    if rows:
        suggestions.append(f"How is {first_name(rows[0]['name'])} doing?")
        medicine = _medicine([name for row in rows for name in row["medicines"]])
        if medicine:
            suggestions.append(f"What is {medicine.lower()} used for?")
        suggestions.append(f"Book {first_name(rows[-1]['name'] if len(rows) > 1 else rows[0]['name'])} a follow-up visit next week")
    return {"text": text, "suggestions": suggestions}
