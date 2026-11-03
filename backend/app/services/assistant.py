"""Clinician Assistant (proposed seventh agent, owner Nunsi): a clinician's typed or spoken instruction ->
proposed changes. Nothing is saved until the clinician confirms (apply). Only uses the clinician's own words:
it never invents a medicine, dose, time or place, flags what is missing as an issue, and blocks messages or calls
the patient has not agreed to. This is the rules-based stand-in ported from the frontend mock; a Groq-backed
drafting step can replace `draft_action` later without changing the contract (docs/api_shapes.md).
"""

import re
from datetime import datetime, timedelta

from app.db import store
from app.services import care, notifications, outbox, voice
from app.services.activity_log import log_event
from app.util import ApiError, first_name, iso, make_id, now

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fourteen": 14, "thirty": 30}
TEST_WORDS = re.compile(r"\b(test|lab|labs|blood|scan|x-?ray|ecg|urine|swab)\b")
MEDICINE_WORDS = re.compile(r"\b\d+(?:\.\d+)?\s?(mg|mcg|ml|g|units?)\b|\b(tablets?|capsules?|syrup|injection|dose|medicine|medication|take|takes)\b")
VISIT_WORDS = re.compile(r"\b(book|appointment|visit|review|follow-?up|clinic|wound check|dressing|check-?up)\b")
TEXT_WORDS = re.compile(r"\b(text|sms|e-?mail|send (?:her|him|them)?\s*a message|message (?:her|him|them))\b")
CALL_WORDS = re.compile(r"\b(call|ring|phone)\b")
ASSISTANT_TEMPLATES = ["medicine", "visit", "call_clinic"]


def _number(word: str) -> int:
    return NUMBER_WORDS.get(word, int(word) if word.isdigit() else 1)


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _local_now() -> datetime:
    return datetime.now(care.zone())


def parse_when(clause: str, fallback_hour: int) -> str | None:
    lower = clause.lower()
    date = _local_now()
    day_found = False
    if re.search(r"\btomorrow\b", lower):
        date, day_found = date + timedelta(days=1), True
    elif re.search(r"\b(today|tonight|this (morning|afternoon|evening))\b", lower):
        day_found = True
    elif match := re.search(r"\bin (\d+|a|an|one|two|three|four|five|six|seven|ten|fourteen) (days?|weeks?)\b", lower):
        date, day_found = date + timedelta(days=_number(match.group(1)) * (7 if match.group(2).startswith("week") else 1)), True
    elif re.search(r"\bnext week\b", lower):
        date, day_found = date + timedelta(days=7), True
    elif match := re.search(rf"\b({'|'.join(WEEKDAYS)})\b", lower):
        diff = (WEEKDAYS.index(match.group(1)) - date.weekday()) % 7 or 7
        date, day_found = date + timedelta(days=diff), True
    elif (match := re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({'|'.join(MONTHS)})\b", lower)) or \
            (match := re.search(rf"\b({'|'.join(MONTHS)})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", lower)):
        day, month = (int(match.group(1)), MONTHS.index(match.group(2)) + 1) if match.group(1).isdigit() else (int(match.group(2)), MONTHS.index(match.group(1)) + 1)
        try:
            candidate = date.replace(month=month, day=day)
        except ValueError:
            candidate = None
        if candidate:
            if candidate < date - timedelta(days=1):
                candidate = candidate.replace(year=candidate.year + 1)
            date, day_found = candidate, True

    hour, minute = None, 0
    if match := re.search(r"\b(\d{1,2})[:.](\d{2})\s*(am|pm)?\b", lower):
        hour, minute = int(match.group(1)), int(match.group(2))
        hour += 12 if match.group(3) == "pm" and hour < 12 else 0
        hour = 0 if match.group(3) == "am" and hour == 12 else hour
    elif match := re.search(r"\b(\d{1,2})\s*(am|pm)\b", lower):
        hour = int(match.group(1)) % 12 + (12 if match.group(2) == "pm" else 0)
    elif match := re.search(r"\bat (\d{1,2})\b(?!\s*(mg|mcg|ml|g|days?|weeks?))", lower):
        hour = int(match.group(1))
        hour += 12 if hour < 7 else 0
    elif re.search(r"\bmorning\b", lower):
        hour = 8
    elif re.search(r"\bafternoon\b", lower):
        hour = 14
    elif re.search(r"\b(evening|tonight|night)\b", lower):
        hour = 20

    if not day_found and hour is None:
        return None
    date = date.replace(hour=hour if hour is not None else fallback_hour, minute=minute, second=0, microsecond=0)
    if not day_found and date < _local_now():
        date += timedelta(days=1)
    return iso(date)


def parse_times(lower: str) -> list[str] | None:
    if re.search(r"\b(three times|3 times)\b", lower):
        return ["08:00", "14:00", "20:00"]
    if re.search(r"\b(twice|two times|2 times|morning and (evening|night))\b", lower):
        return ["08:00", "20:00"]
    clock = []
    for match in re.finditer(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)\b|\b(\d{1,2})[:.](\d{2})\b", lower):
        hour = int(match.group(1) or match.group(4))
        minute = int(match.group(2) or match.group(5) or 0)
        hour += 12 if match.group(3) == "pm" and hour < 12 else 0
        hour = 0 if match.group(3) == "am" and hour == 12 else hour
        stamp = f"{hour:02d}:{minute:02d}"
        if stamp not in clock:
            clock.append(stamp)
    if clock:
        return clock
    if re.search(r"\b(evening|night|bedtime)\b", lower):
        return ["20:00"]
    if re.search(r"\bafternoon\b", lower):
        return ["14:00"]
    if re.search(r"\bmorning\b", lower):
        return ["08:00"]
    return None


def mentioned_patient(text: str, facility: str) -> dict | None:
    lower = text.lower()
    patients = store().where("patients", facility=facility)
    return next((item for item in patients if item["name"].lower() in lower), None) or \
        next((item for item in patients if re.search(rf"\b{re.escape(first_name(item['name']).lower())}\b", lower)), None)


def split_instruction(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+|\n+|\s+(?:and\s+)?also\s+|\s+(?:and\s+)?then\s+|\s+and\s+(?=(?:text|sms|e-?mail|send|message|call|ring|phone|book|schedule|add|remind|note|tell)\b)",
                     text, flags=re.I)
    return [cleaned for part in parts if (cleaned := re.sub(r"[.;]+$", "", part.strip())) and len(cleaned) > 2]


def draft_action(clause: str, patient: dict) -> dict:
    lower = clause.lower()
    first = first_name(patient["name"])
    action_id = make_id("act")
    if re.match(r"^(note|add a note|write down|remember)\b[:\s]*", clause, re.I):
        return {"id": action_id, "kind": "note", "text": _cap(re.sub(r"^(note|add a note|write down|remember)\b[:\s]*(that\s+)?", "", clause, flags=re.I)), "issues": []}
    if TEXT_WORDS.search(lower):
        template = "visit" if re.search(r"\b(visit|appointment|clinic day)\b", lower) else "medicine" if MEDICINE_WORDS.search(lower) else "call_clinic"
        if not notifications.message_channels(patient):
            return {"id": action_id, "kind": "send_text", "template": template, "blocked": True, "issues": [f"{first} has not agreed to email reminders, so this cannot be sent."]}
        return {"id": action_id, "kind": "send_text", "template": template, "issues": []}
    if CALL_WORDS.search(lower) and not re.search(r"\bcall (us|the clinic|the ward)\b", lower):
        if "voice" not in patient.get("channels", []):
            return {"id": action_id, "kind": "call_patient", "blocked": True, "issues": [f"{first} has not agreed to phone calls, so Tomi cannot call."]}
        return {"id": action_id, "kind": "call_patient", "issues": ["Tomi calls straight away. Calls at a set time are not available yet."] if parse_when(clause, 10) else []}
    if TEST_WORDS.search(lower):
        name = re.search(r"(?:(?:a|an|the|her|his|their)\s+)((?:[a-z-]+\s+){0,3}?(?:blood test|test|scan|x-?ray|ecg|swab|labs?))\b", lower)
        place = re.search(r"\bat (?:the )?([a-z ]*(?:laboratory|lab|clinic|radiology))\b", lower)
        due_at = parse_when(clause, 9)
        return {"id": action_id, "kind": "test", "title": _cap(name.group(1)) if name else "Test", "detail": _cap(place.group(1)) if place else "Hospital laboratory",
                "due_at": due_at, "issues": [] if due_at else ["No date given. Set when it is due."]}
    if MEDICINE_WORDS.search(lower) and not VISIT_WORDS.search(re.sub(r"\b(review|follow-?up)\b", "", lower)):
        named = re.search(r"\b([A-Za-z][a-z]{3,}(?:[- ][A-Za-z][a-z]+)?)\s+(\d+(?:\.\d+)?\s?(?:mg|mcg|ml|g|units?))\b", clause, re.I)
        name_only = None if named else re.search(r"\btakes?\s+(?:the\s+|her\s+|his\s+|their\s+)?([A-Za-z][a-z]{3,})\b", clause, re.I)
        form = re.search(r"\b(tablet|capsule|syrup|injection)s?\b", lower)
        amount = re.search(r"\b(\d+|one|two|half)\s+(tablet|capsule|teaspoon|spoon)s?\b", lower)
        days_match = re.search(r"\bfor (\d+|a|one|two|three|four|five|six|seven|ten|fourteen|thirty) (days?|weeks?)\b", lower)
        times = parse_times(lower)
        issues = []
        if not named:
            issues.append("No dose given. Add it after the name before you confirm." if name_only else "The medicine name or dose is not clear. Type it in before you confirm.")
        if not times:
            issues.append("No time given. Set to 08:00. Change it if needed.")
        if not days_match:
            issues.append("No length given. Set to 7 days. Change it if needed.")
        strength = re.sub(r"(\d)(mg|mcg|ml|g)", r"\1 \2", named.group(2), flags=re.I) if named else ""
        title = f"{_cap(named.group(1))} {strength}{' ' + form.group(1) if form else ''}" if named else (_cap(name_only.group(1)) if name_only else "")
        detail = f"{amount.group(1)} {amount.group(2)}{'' if amount.group(1) in ('one', '1') else 's'}" if amount else (f"1 {form.group(1)}" if form else "")
        starts = parse_when(re.sub(r"\b(morning|evening|night|afternoon)\b", "", clause, flags=re.I), 8) or iso(_local_now())
        return {"id": action_id, "kind": "medicine", "title": title, "detail": detail, "times": times or ["08:00"],
                "days": _number(days_match.group(1)) * (7 if days_match.group(2).startswith("week") else 1) if days_match else 7,
                "starts_on": datetime.fromisoformat(starts.replace("Z", "+00:00")).astimezone(care.zone()).date().isoformat(), "issues": issues}
    if VISIT_WORDS.search(lower):
        what = re.search(r"\b(wound check|dressing change|check-?up|review visit|review|follow-?up(?: visit)?|[a-z]+ review|[a-z]+ clinic visit)\b", lower)
        where = re.search(r"\b(?:at|in) (?:the )?((?:[A-Z][a-z]+ )*(?:Clinic|Outpatients|Ward|Unit|Centre)(?:,? room \d+)?)", clause)
        starts_at = parse_when(clause, 10)
        issues = ([] if starts_at else ["No date or time given. Set when the visit is."]) + ([] if where else ["No place given. Add where the visit is."])
        label = what.group(1) if what else "Review visit"
        return {"id": action_id, "kind": "visit", "what": _cap("review visit" if label == "review" else label), "where": where.group(1) if where else "",
                "starts_at": starts_at, "issues": issues}
    return {"id": action_id, "kind": "note", "text": _cap(clause), "issues": []}


def template_options(patient: dict) -> list[dict]:
    return [{"id": template, "title": notifications.TEMPLATES[template][0], "body": notifications.render(template, patient, "sms")[1]} for template in ASSISTANT_TEMPLATES]


def draft_reply(patient: dict, actions: list[dict]) -> str:
    if not actions:
        return f"I did not find anything to change for {patient['name']}. Try saying what to add, book, send or note."
    count = "one change" if len(actions) == 1 else f"{len(actions)} changes"
    flagged = any(not action.get("blocked") and action["issues"] for action in actions)
    blocked = sum(bool(action.get("blocked")) for action in actions)
    left = f"{'One' if blocked == 1 else blocked} cannot be done, so {'it is' if blocked == 1 else 'they are'} left out. " if blocked else ""
    return (f"For {patient['name']}, I have drafted {count}. {'Some need a detail from you. ' if flagged else ''}{left}"
            f"{'Check it' if len(actions) == 1 else 'Check them'}, then confirm. Nothing is saved until you do.")


def draft(text: str, patient_id: str | None, facility: str) -> dict:
    instruction = str(text or "").strip()
    if not instruction:
        raise ApiError("Type or say what you want done.")
    patient = None
    if patient_id:
        patient = store().first("patients", id=patient_id, facility=facility)
        if not patient:
            raise ApiError("Patient was not found.", 404)
    else:
        patient = mentioned_patient(instruction, facility)
    if not patient:
        return {"instruction": instruction, "patient": None, "reply": "Which patient is this for? Choose one and I will draft the changes.", "needs_patient": True,
                "choices": [{"id": item["id"], "name": item["name"]} for item in store().where("patients", facility=facility)], "actions": []}
    actions = [draft_action(clause, patient) for clause in split_instruction(instruction)]
    return {"instruction": instruction, "patient": {"id": patient["id"], "name": patient["name"], "language": patient["language"], "channels": patient.get("channels", [])},
            "reply": draft_reply(patient, actions), "needs_patient": False, "actions": actions, "templates": template_options(patient)}


def _apply(patient: dict, action: dict, by: str) -> str:
    first = first_name(patient["name"])
    kind = action.get("kind")
    if kind == "medicine":
        title = str(action.get("title") or "").strip()
        if not title:
            raise ApiError("Add the medicine name and dose.")
        raw_times = action.get("times") if isinstance(action.get("times"), list) else re.split(r"[,\s]+", str(action.get("times") or ""))
        times = [time for time in raw_times if re.match(r"^\d{1,2}:\d{2}$", str(time))]
        if not times:
            raise ApiError("Add at least one time, such as 08:00.")
        days = min(max(int(action.get("days") or 1), 1), 90)
        start = datetime.fromisoformat(str(action.get("starts_on") or _local_now().date().isoformat())).replace(tzinfo=care.zone())
        created = 0
        for offset in range(days):
            for time in times:
                hours, minutes = (int(part) for part in time.split(":"))
                due = (start + timedelta(days=offset)).replace(hour=hours, minute=minutes)
                if due < now():
                    continue
                store().add("tasks", {"id": make_id("t"), "patient_id": patient["id"], "type": "medication", "title": title, "detail": str(action.get("detail") or "").strip(),
                                      "due_at": iso(due), "criticality": "high", "status": "pending", "last_reported_at": None, "created_by": by})
                created += 1
        log_event(patient["id"], actor_type="clinician", actor_id=by, source_channel="dashboard", event_type="task_added",
                  summary=f"Added {title} at {' and '.join(times)} for {days} {'day' if days == 1 else 'days'}.", verification_status="clinician_verified")
        outbox.schedule_reminders(patient)
        return f"{title}: {created} {'reminder' if created == 1 else 'reminders'} added."
    if kind == "test":
        title = str(action.get("title") or "").strip()
        if not title:
            raise ApiError("Add the name of the test.")
        if not action.get("due_at"):
            raise ApiError("Set when the test is due.")
        store().add("tasks", {"id": make_id("t"), "patient_id": patient["id"], "type": "test", "title": title, "detail": str(action.get("detail") or "").strip(),
                              "due_at": action["due_at"], "criticality": "medium", "status": "pending", "last_reported_at": None, "created_by": by})
        log_event(patient["id"], actor_type="clinician", actor_id=by, source_channel="dashboard", event_type="task_added",
                  summary=f"Added {title}, due {care.local(action['due_at']).strftime('%A %d %B').replace(' 0', ' ')}.", verification_status="clinician_verified")
        outbox.schedule_reminders(patient)
        return f"{title} added to the plan."
    if kind == "visit":
        if not action.get("starts_at"):
            raise ApiError("Set the date and time of the visit.")
        where = str(action.get("where") or "").strip()
        if not where:
            raise ApiError("Add where the visit is.")
        what = str(action.get("what") or "").strip() or "Review visit"
        store().add("appointments", {"id": make_id("a"), "patient_id": patient["id"], "what": what, "where": where, "starts_at": action["starts_at"],
                                     "status": "scheduled", "created_by": by})
        log_event(patient["id"], actor_type="clinician", actor_id=by, source_channel="dashboard", event_type="appointment_booked",
                  summary=f"Booked {what.lower()} at {where}.", verification_status="clinician_verified")
        outbox.schedule_reminders(patient)
        return f"{what} booked."
    if kind == "send_text":
        channels = notifications.message_channels(patient)
        if not channels:
            raise ApiError(f"{first} has not agreed to email reminders.")
        if action.get("template") not in ASSISTANT_TEMPLATES:
            raise ApiError("Choose which message to send.")
        message = outbox.queue_message(patient, channel=channels[0], template=action["template"], created_by=by)
        log_event(patient["id"], actor_type="clinician", actor_id=by, source_channel="dashboard", event_type="notification_requested",
                  summary=f'Sent a "{message["title"]}" {outbox.channel_noun(channels[0])}.', verification_status="clinician_verified")
        return f'"{message["title"]}" {outbox.channel_noun(channels[0])} sent to {first}.'
    if kind == "call_patient":
        if "voice" not in patient.get("channels", []):
            raise ApiError(f"{first} has not agreed to phone calls.")
        if not voice.demo_enabled():
            raise ApiError("Phone calls are not set up yet.", 503)
        voice.scripted_call(patient, "outbound")
        log_event(patient["id"], actor_type="clinician", actor_id=by, source_channel="voice", event_type="call_requested",
                  summary="Outbound Tomi call requested from the assistant.", verification_status="clinician_verified")
        return f"Tomi is calling {first} now."
    if kind == "note":
        text = str(action.get("text") or "").strip()
        if not text:
            raise ApiError("The note is empty.")
        log_event(patient["id"], actor_type="clinician", actor_id=by, source_channel="dashboard", event_type="care_team_note", summary=text, verification_status="clinician_verified")
        return "Note added to the timeline."
    raise ApiError("This kind of change is not supported.")


def apply(patient: dict, actions: list[dict], by: str) -> dict:
    results = []
    for action in actions or []:
        if action.get("blocked"):
            continue
        try:
            results.append({"id": action.get("id"), "kind": action.get("kind"), "ok": True, "summary": _apply(patient, action, by)})
        except (ApiError, ValueError) as error:
            results.append({"id": action.get("id"), "kind": action.get("kind"), "ok": False, "summary": getattr(error, "detail", str(error))})
    return {"results": results, "patient": {"id": patient["id"], "name": patient["name"]}}
