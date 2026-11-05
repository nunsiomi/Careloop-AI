"""Deterministic red-flag, consent and low-confidence rules (owner: Dorcas spec, Olamide enforcement).

`check()` runs on every patient message and voice turn before any agent or reply. It never calls a model.
- A red-flag term (any language, red_flags.json) -> "escalate": routine replies stop, the approved emergency line
  is given and an escalation opens.
- A red-flag term after a negation ("no chest pain") -> "confirm": Tomi asks once, with the emergency advice, instead
  of ignoring it or escalating outright.
- Low speech confidence with a word from any red-flag term -> "escalate" (the uncertain-but-dangerous path).
- Low speech confidence otherwise -> "clarify".
The rules are a DRAFT until the clinical mentor signs docs/clinical-safety-review.md.
"""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

RULES_PATH = Path(__file__).with_name("red_flags.json")
_HOOKED = str.maketrans({"ƙ": "k", "Ƙ": "k", "ɗ": "d", "Ɗ": "d", "ɓ": "b", "Ɓ": "b", "ƴ": "y", "’": "'", "‘": "'", "ʼ": "'"})
_cache: dict = {"mtime": None, "rules": None}


def normalize(text: str) -> str:
    """Lower case, no tone marks or dots under letters, hooked letters mapped, single spaces."""
    text = unicodedata.normalize("NFD", str(text or "").translate(_HOOKED))
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    return re.sub(r"\s+", " ", text).strip()


def load() -> dict:
    mtime = RULES_PATH.stat().st_mtime
    if _cache["mtime"] != mtime:
        _cache.update(mtime=mtime, rules=json.loads(RULES_PATH.read_text(encoding="utf-8")))
    return _cache["rules"]


def policy(name: str) -> dict:
    return load().get("policies", {}).get(name, {})


def emergency_line() -> str:
    return load()["emergency_line"]


@dataclass
class SafetyResult:
    action: str                      # "escalate" | "confirm" | "clarify" | "continue"
    rule_id: str | None = None
    label: str | None = None
    severity: str | None = None
    matched: str | None = None
    negated: list[str] = field(default_factory=list)

    @property
    def escalate(self) -> bool:
        return self.action == "escalate"

    def confirm_line(self) -> str:
        return load()["confirm_line"].format(label=self.label or "this")


def _term_pattern(term: str) -> re.Pattern:
    return re.compile(rf"(?<![a-z0-9']){re.escape(normalize(term))}(?![a-z0-9])")


def _negated(prefix: str, cues: list[str]) -> bool:
    """A negation cue in the three words just before the match ('I do not have any chest pain')."""
    pattern = rf"(?:^|[^a-z'])(?:{'|'.join(re.escape(normalize(cue)) for cue in sorted(cues, key=len, reverse=True))})(?:\s+[a-z']+){{0,2}}\s*$"
    return re.search(pattern, prefix) is not None


def check(text: str, confidence: float | None = None) -> SafetyResult:
    rules = load()
    clean = normalize(text)
    cues = [cue for language in rules.get("negation_cues", {}).values() for cue in language]
    negated: list[tuple[dict, str]] = []
    for rule in rules["rules"]:
        terms = sorted({term for language in rule["terms"].values() for term in language}, key=len, reverse=True)
        for term in terms:
            for match in _term_pattern(term).finditer(clean):
                if _negated(clean[:match.start()], cues):
                    negated.append((rule, term))
                    continue
                return SafetyResult("escalate", rule["id"], rule["label"], rule["severity"], term)
    if negated:
        rule, term = negated[0]
        return SafetyResult("confirm", rule["id"], rule["label"], rule["severity"], term, [item[1] for item in negated])
    threshold = rules.get("low_confidence_threshold", 0.6)
    if confidence is not None and confidence < threshold:
        words = set(re.findall(r"[a-z']{4,}", clean))
        for rule in rules["rules"]:
            hint = next((word for language in rule["terms"].values() for term in language for word in normalize(term).split() if len(word) >= 4 and word in words), None)
            if hint:
                return SafetyResult("escalate", "possible_red_flag_low_confidence", f"possible {rule['label']} (unclear speech)", "red", hint)
        return SafetyResult("clarify")
    return SafetyResult("continue")


def consent_allows(patient: dict, channel: str) -> bool:
    """A channel may be used only with the patient's recorded consent (checked again at send time)."""
    return bool(patient.get("consent_at")) and channel in (patient.get("channels") or [])
