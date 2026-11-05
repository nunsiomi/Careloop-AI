"""Numeric/term preservation checks for translated or adapted messages.

Any number in text going to a patient (a dose, a time, a count of days, a date) must already appear in the approved
source: the clinician-approved plan and tasks. A model-written reply that adds or changes a number is not sent; the
caller falls back to a fixed, approved line. Used for Check-in Agent replies and Escalation Summary briefs.
"""

import re
from dataclasses import dataclass, field

from app.safety.rules import normalize

NUMBER_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                "ten": 10, "eleven": 11, "twelve": 12, "fourteen": 14, "fifteen": 15, "twenty": 20, "thirty": 30, "half": 0.5}
_CLOCK = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")
_AM_PM = re.compile(r"\b(1[0-2]|0?[1-9])\s*(am|pm)\b")


def numbers(text: str) -> set[str]:
    """Times as HH:MM, everything else as a plain number string ('5', '0.5', '30')."""
    clean = normalize(text)
    found = {f"{int(hour):02d}:{minute}" for hour, minute in _CLOCK.findall(clean)}
    for hour, half in _AM_PM.findall(clean):
        found.add(f"{int(hour) % 12 + (12 if half == 'pm' else 0):02d}:00")
    rest = _AM_PM.sub(" ", _CLOCK.sub(" ", clean))
    for value in re.findall(r"\d+(?:\.\d+)?", rest):
        found.add(_plain(float(value)))
    for word, value in NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", rest):
            found.add(_plain(value))
    return found


def _plain(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


@dataclass
class NumberCheck:
    passed: bool
    unexpected: list[str] = field(default_factory=list)


def check(outgoing: str, approved_sources: list[str], allowed: set[str] | None = None) -> NumberCheck:
    approved = set().union(*(numbers(source) for source in approved_sources)) if approved_sources else set()
    approved |= allowed or set()
    unexpected = sorted(numbers(outgoing) - approved)
    return NumberCheck(not unexpected, unexpected)
