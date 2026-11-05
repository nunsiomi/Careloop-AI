"""Rule checks of a draft care plan against its source discharge note (owner: Mary).

Used by the Care Plan Agent (to drop anything the model invented) and the Plan Verifier (field-by-field diff).
No model calls here, so these checks always run. Each finding says which plan field it is about and quotes the
note (`source_text` is always an exact substring of the note, so the dashboard can highlight it).

Severity: "high" blocks delivery to the patient (anything about which medicine, how much, how often, or a date or
time that is not in the note); "medium" needs the clinician's attention but does not block on its own.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

from app.models import PlanDraft, PlanIssue

NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
    "nine": "9", "ten": "10", "twelve": "12", "fourteen": "14", "twenty": "20", "thirty": "30", "half": "0.5",
}
STRENGTH = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|iu|units?)\b", re.I)
MEDICINE_LINE = re.compile(r"\b(tablets?|capsules?|injections?|syrup|inhaler|cream|drops|suspension)\b|" + STRENGTH.pattern, re.I)
CLOCK = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
AM_PM = re.compile(r"\b(1[0-2]|0?[1-9])(?:[:.]([0-5]\d))?\s*(am|pm)\b", re.I)
FRACTION = re.compile(r"(?<![\d/])(\d)/(\d)(?![\d/])|½")
# Words before a medicine's name: verbs, and the dosage-form abbreviations notes often start with ("Tab. Amlodipine")
LEADING_VERBS = {"continue", "start", "restart", "take", "give", "stop", "tab", "tabs", "tablet", "cap", "caps", "capsule",
                 "inj", "injection", "syr", "syrup", "susp", "suspension", "t", "c"}
# Standard prescription abbreviations, expanded only for comparing (the note's own words are what gets quoted)
ABBREVIATIONS = {"od": "once daily", "bd": "twice daily", "bid": "twice daily", "tds": "three times daily", "tid": "three times daily",
                 "qds": "four times daily", "qid": "four times daily", "nocte": "at night", "mane": "in the morning", "prn": "as needed",
                 "tab": "tablet", "tabs": "tablets", "cap": "capsule", "caps": "capsules"}
FREQUENCY_COUNTS = {"once": 1, "twice": 2, "three times": 3, "four times": 4}
# Lines that book a visit or a test, so one the plan leaves out is caught without the model (from Mary's PR #3).
VISIT_LINE = re.compile(r"\b(appointments?|follow[- ]?up|review|clinic visit|see (?:the |your )?(?:doctor|nurse))\b", re.I)
TEST_LINE = re.compile(r"\b(tests?|scans?|x-?rays?|ultrasound|ecg|echo(?:cardiogram)?|blood count|fbc|urinalysis|lab(?:oratory)? work)\b", re.I)
UNCLEAR_USE = re.compile(r"\b(as directed|as needed|when required|prn|as before|as usual)\b", re.I)
VAGUE_DATE = re.compile(r"\b(next week|next month|soon|later|in a few days|as soon as possible)\b", re.I)
RELATIVE_DATE = re.compile(r"\b(in|within)\s+(\d+|" + "|".join(NUMBER_WORDS) + r")\s+(days?|weeks?)\b", re.I)
DAY_MONTH = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]{3,9})\b(?!,?\s+\d{4})")
WRITTEN_DATE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]{3,9}),?\s+(\d{4})\b|\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
DISCHARGE_DATE = re.compile(r"discharge date:?\s*(.+)", re.I)
MONTHS = {name: number for number, names in enumerate(
    [("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",), ("jun", "june"),
     ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
     ("dec", "december")], start=1) for name in names}
STOP_WORDS = {"take", "with", "after", "before", "every", "the", "and", "your", "each", "this", "that", "from",
              "for", "once", "daily", "tablet", "tablets", "capsule", "capsules", "hospital", "room", "time"}


@dataclass
class Finding:
    issue: PlanIssue
    invented: bool = False      # the plan holds a value the note does not support: the Care Plan Agent blanks it
                                # (or drops the whole item when the field is its name)


def _issue(field: str, text: str, severity: str, source_text: str = "", invented: bool = False) -> Finding:
    return Finding(PlanIssue(field=field, issue=text, severity=severity, source_text=source_text), invented)


def _words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z]+", text.lower()) if len(word) >= 4 and word not in STOP_WORDS}


def expand(text: str) -> str:
    """'1 tab bd' -> '1 tablet twice daily', for comparing only."""
    return re.sub(r"\b(" + "|".join(ABBREVIATIONS) + r")\b\.?", lambda match: ABBREVIATIONS[match.group(1).lower()], text, flags=re.I)


def _plain_words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z]+", text.lower()) if len(word) >= 3} - {"every", "with", "take", "the", "and", "daily", "times", "day"}


def _frequency_count(text: str) -> int | None:
    lower = text.lower()
    return next((count for words, count in FREQUENCY_COUNTS.items() if re.search(rf"\b{words}\b", lower)), None)


def _numbers(text: str) -> set[str]:
    """Numbers in a piece of text, with number words turned into digits and clock times left out."""
    text = AM_PM.sub(" ", CLOCK.sub(" ", text.lower()))
    text = FRACTION.sub(lambda match: str(int(match.group(1)) / int(match.group(2))) if match.group(1) else "0.5", text)
    text = re.sub(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", lambda match: NUMBER_WORDS[match.group(1)], text)
    return {str(float(value)) for value in re.findall(r"\d+(?:\.\d+)?", text)}


def _strengths(text: str) -> set[str]:
    return {f"{float(amount)} {unit.lower().rstrip('s')}" for amount, unit in STRENGTH.findall(text)}


def _clock_times(text: str) -> set[str]:
    times = {f"{int(hour):02d}:{minute}" for hour, minute in CLOCK.findall(text)}
    for hour, minute, half in AM_PM.findall(text):
        times.add(f"{int(hour) % 12 + (12 if half.lower() == 'pm' else 0):02d}:{minute or '00'}")
    return times


def _note_lines(note: str) -> list[str]:
    return [line.strip() for line in note.splitlines() if line.strip()]


def _care_lines(lines: list[str]) -> list[str]:
    """Lines that can hold plan items (not the heading, the discharge date or the return-to-hospital advice)."""
    return [line for line in lines if not re.match(r"(discharge|return to hospital)", line, re.I)]


def _medicine_word(text: str) -> str:
    """The medicine's name: the first word, skipping a leading verb ("Continue lisinopril 5 mg")."""
    words = [word.lower() for word in re.findall(r"[A-Za-z][A-Za-z-]+", text)]
    return next((word for word in words if word not in LEADING_VERBS), "")


def _lines_naming(lines: list[str], medicine: str) -> list[str]:
    return [line for line in lines if re.search(rf"\b{re.escape(medicine)}\b", line, re.I)] if medicine else []


def _best_line(lines: list[str], text: str) -> str:
    wanted = _words(text)
    scored = [(len(wanted & _words(line)), line) for line in lines]
    best = max(scored, default=(0, ""), key=lambda pair: pair[0])
    return best[1] if best[0] else ""


def _parse_date(day: int, month: int, year: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _written_dates(text: str, default_year: int | None = None) -> tuple[list[date], list[str]]:
    """Valid dates written in the text, and date-like strings that are not real dates (e.g. 31 November).
    A day and month without a year ("10th November") takes the discharge year."""
    valid, invalid = [], []
    if default_year:
        for match in DAY_MONTH.finditer(text):
            month = MONTHS.get(match.group(2).lower())
            if not month:
                continue
            parsed = _parse_date(int(match.group(1)), month, default_year)
            if parsed:
                valid.append(parsed)
            else:
                invalid.append(match.group(0))
    for match in WRITTEN_DATE.finditer(text):
        if match.group(1):
            month = MONTHS.get(match.group(2).lower())
            if not month:
                continue
            parsed = _parse_date(int(match.group(1)), month, int(match.group(3)))
        elif match.group(4):
            parsed = _parse_date(int(match.group(6)), int(match.group(5)), int(match.group(4)))
        else:
            parsed = _parse_date(int(match.group(7)), int(match.group(8)), int(match.group(9)))
        if parsed:
            valid.append(parsed)
        else:
            invalid.append(match.group(0))
    return valid, invalid


def discharge_date(note: str) -> date | None:
    for line in _note_lines(note):
        match = DISCHARGE_DATE.match(line)
        if match:
            valid, _ = _written_dates(match.group(1))
            if valid:
                return valid[0]
    return None


def _check_date(field: str, plan_date: str, line: str, discharged: date | None, what: str) -> list[Finding]:
    valid, invalid = _written_dates(line, discharged.year if discharged else None)
    if invalid:
        return [_issue(field, f"The {what} date in the note ({invalid[0]}) is not a real date", "high", invalid[0], bool(plan_date))]

    exact, window = list(valid), None
    relative = RELATIVE_DATE.search(line)
    if relative:
        if not discharged:
            return [_issue(field, f"The note gives the {what} date relative to discharge, but has no discharge date",
                           "medium" if not plan_date else "high", relative.group(0), bool(plan_date))]
        amount = int(NUMBER_WORDS.get(relative.group(2).lower(), relative.group(2)))
        days = amount * (7 if relative.group(3).lower().startswith("week") else 1)
        if relative.group(1).lower() == "in":
            exact.append(discharged + timedelta(days=days))
        else:
            window = (discharged, discharged + timedelta(days=days))

    if not plan_date:
        vague = VAGUE_DATE.search(line)
        if vague:
            return [_issue(field, f'"{vague.group(0)}" is not an exact date', "medium", vague.group(0))]
        if window:
            return [_issue(field, f'The note says "{relative.group(0)}"; choose the exact {what} date', "medium", relative.group(0))]
        if exact:
            return [_issue(field, f"The note gives a {what} date, but the plan has none", "medium", relative.group(0) if relative else line)]
        return [_issue(field, f"The {what} date is missing from the note", "medium", line)]

    try:
        chosen = date.fromisoformat(plan_date)
    except ValueError:
        return [_issue(field, f"The date {plan_date} is not a real date", "high", line, invented=True)]
    if chosen in exact or (window and window[0] <= chosen <= window[1]):
        return []
    return [_issue(field, f"The date {plan_date} is not in the note", "high", line, invented=True)]


def _check_medicine(index: int, medication, care_lines: list[str]) -> list[Finding]:
    field = f"medications[{index}]"
    medicine = _medicine_word(medication.name)
    naming = _lines_naming(care_lines, medicine)
    if not naming:
        return [_issue(f"{field}.name", f"{medication.name or 'This medicine'} is not in the note", "high", invented=True)]
    line = naming[0]
    seen = expand(line)  # "1 tab bd" read as "1 tablet twice daily"; findings still quote the note's own words
    findings = []

    # Strength: must be written, and the same everywhere the note names this medicine
    note_strengths = set().union(*(_strengths(other) for other in naming))
    plan_strengths = _strengths(medication.name)
    if len(note_strengths) > 1:
        conflicting = next((other for other in naming if _strengths(other) != _strengths(line)), naming[-1])
        findings.append(_issue(f"{field}.name", f"The note gives different strengths for {medicine.capitalize()}", "high", conflicting))
    elif not note_strengths:
        findings.append(_issue(f"{field}.name", "The strength (for example mg) is not stated in the note", "high", line))
    elif not plan_strengths:
        findings.append(_issue(f"{field}.name", "The plan leaves out the strength written in the note", "high", line))
    elif not plan_strengths <= note_strengths:
        findings.append(_issue(f"{field}.name", "The strength in the plan does not match the note", "high", line))

    # Amount each time
    if not medication.dose:
        findings.append(_issue(f"{field}.dose", "How much to take each time is not stated", "high", line))
    elif not _numbers(medication.dose) <= _numbers(seen):
        findings.append(_issue(f"{field}.dose", f'The dose "{medication.dose}" is not in the note', "high", line, invented=True))

    # How often
    unclear = UNCLEAR_USE.search(line)
    plan_count, note_count = _frequency_count(expand(medication.frequency)), _frequency_count(seen)
    if unclear:
        findings.append(_issue(f"{field}.frequency", "How often to take it is not stated", "high", unclear.group(0), bool(medication.frequency)))
    elif not medication.frequency:
        findings.append(_issue(f"{field}.frequency", "How often to take it is missing from the plan", "high", line))
    elif plan_count and note_count and plan_count != note_count:
        findings.append(_issue(f"{field}.frequency", f'"{medication.frequency}" is not how often the note says to take it', "high", line, invented=True))
    elif not (plan_count and plan_count == note_count) and not (_plain_words(expand(medication.frequency)) & _plain_words(seen)):
        findings.append(_issue(f"{field}.frequency", f'"{medication.frequency}" is not how the note says to take it', "medium", line))

    # Reminder times for this medicine
    written_times = _clock_times(seen)
    extra = [time for time in medication.times if time not in written_times]
    if extra:
        findings.append(_issue(f"{field}.times", f"{', '.join(extra)} is not a time written in the note; confirm it", "medium", line, invented=True))

    # Duration
    if medication.duration and not _numbers(medication.duration) <= _numbers(seen):
        findings.append(_issue(f"{field}.duration", f'"{medication.duration}" is not the length of treatment in the note', "high", line, invented=True))

    # Extra instructions must come from the note
    if medication.instructions and not _words(medication.instructions) <= _words(seen):
        findings.append(_issue(f"{field}.instructions", f'"{medication.instructions}" is not in the note', "medium", line))
    return findings


def check(note: str, plan: PlanDraft, patient_name: str = "") -> list[Finding]:
    lines = _note_lines(note)
    care_lines = _care_lines(lines)
    discharged = discharge_date(note)
    findings: list[Finding] = []

    if patient_name and patient_name.lower() not in note.lower():
        findings.append(_issue("source_note", f"The note does not name {patient_name}; check it is the right patient", "high", lines[0] if lines else ""))

    for index, medication in enumerate(plan.medications):
        findings += _check_medicine(index, medication, care_lines)

    # Medicines in the note that the plan leaves out
    planned = {_medicine_word(medication.name) for medication in plan.medications}
    seen = set()
    for line in care_lines:
        if not MEDICINE_LINE.search(line):
            continue
        medicine = _medicine_word(line)
        if medicine and medicine not in planned and medicine not in seen:
            seen.add(medicine)
            findings.append(_issue("medications", "A medicine in the note is not in the plan", "high", line))

    for index, appointment in enumerate(plan.appointments):
        field = f"appointments[{index}]"
        line = _best_line(care_lines, f"{appointment.what} {appointment.where}")
        if not line:
            findings.append(_issue(f"{field}.what", "This visit is not in the note", "high", invented=True))
            continue
        findings += _check_date(f"{field}.date", appointment.date, line, discharged, "visit")
        if appointment.time and appointment.time not in _clock_times(line):
            findings.append(_issue(f"{field}.time", f"The time {appointment.time} is not in the note", "high", line, invented=True))
        elif not appointment.time:
            findings.append(_issue(f"{field}.time", "The visit time is missing from the note", "medium", line))

    # Visits and tests in the note that the plan leaves out (medicine lines are checked above)
    covered = {_best_line(care_lines, f"{item.what} {item.where}") for item in plan.appointments}
    covered |= {_best_line(care_lines, f"{item.name} {item.where}") for item in plan.tests}
    for line in care_lines:
        if line in covered or MEDICINE_LINE.search(line):
            continue
        if TEST_LINE.search(line):
            findings.append(_issue("tests", "A test in the note is not in the plan", "high", line))
        elif VISIT_LINE.search(line):
            findings.append(_issue("appointments", "A visit in the note is not in the plan", "high", line))

    for index, test in enumerate(plan.tests):
        field = f"tests[{index}]"
        line = _best_line(care_lines, f"{test.name} {test.where}")
        if not line:
            findings.append(_issue(f"{field}.name", "This test is not in the note", "high", invented=True))
            continue
        findings += _check_date(f"{field}.date", test.date, line, discharged, "test")

    lowered = note.lower()
    for index, symptom in enumerate(plan.symptoms_to_watch):
        if symptom.lower() not in lowered:
            findings.append(_issue(f"symptoms_to_watch[{index}]", f'"{symptom}" is not in the note', "medium"))

    medicine_times = {time for medication in plan.medications for time in medication.times}
    for index, time in enumerate(plan.reminder_times):
        if time not in medicine_times:
            findings.append(_issue(f"reminder_times[{index}]", f"Reminder at {time} does not match any medicine time", "medium"))

    return findings


def issues(note: str, plan: PlanDraft, patient_name: str = "") -> list[PlanIssue]:
    return [finding.issue for finding in check(note, plan, patient_name)]


def has_blocking(found: list[PlanIssue]) -> bool:
    return any(issue.severity == "high" for issue in found)
