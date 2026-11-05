"""Language & Literacy Agent: meaning-preserving adaptation/translation with uncertainty flags (owner: Nunsi).

Returns structured findings or proposed actions only. Never writes care records
directly; the orchestrator validates and invokes approved tools.

Input is an approved English line (a fixed reply or a checked agent reply). Output is the same message in the
patient's language and reading level, kept only if every check passes:
- every number in the English (doses, times, days) appears in the translation, and no new one does;
- every protected term (medicine names, places) appears exactly as written;
- the translation is not much longer than the source (a sign of added content).
Otherwise the patient gets the English, and the app says "Shown in English so the numbers stay exact."
Hausa, Yoruba and Igbo output stays Beta until native speakers have checked it.
"""

import json
from typing import Any

from groq import GroqError

from app.agents.llm import ask_groq_json
from app.safety import number_check

LANGUAGES = {"Hausa": "Hausa", "Yoruba": "Yoruba (with tone marks)", "Igbo": "Igbo (with dots under letters)", "English": "plain English"}
LEVELS = {
    "basic": "Very short sentences and everyday words, for someone who reads with difficulty.",
    "standard": "Clear, everyday language.",
    "caregiver": "Clear, everyday language for a family member helping the patient.",
}
SYSTEM_PROMPT = """You translate short messages from a care team to a patient. Keep the meaning exactly.
Rules:
- Translate only what is written. Do not add advice, reassurance, greetings or explanations.
- Copy every number, time and dose exactly as written, using digits (for example 5 mg, 08:00, 1 tablet).
- Copy medicine names and the protected terms exactly; do not translate them.
- Follow the reading level.
Return JSON: {"text": "the translated message", "unsure": ["any word or phrase you were not sure how to translate"]}"""


def _checks(source: str, adapted: str, protected: list[str]) -> list[str]:
    problems = []
    outgoing = number_check.numbers(adapted)
    if not number_check.numbers(source) <= outgoing:
        problems.append("a number from the English is missing")
    if not number_check.check(adapted, [source]).passed:
        problems.append("a number was added or changed")
    problems += [f'"{term}" was not kept exactly' for term in protected if term and term not in adapted]
    if len(adapted) > max(60, len(source) * 2.5):
        problems.append("much longer than the English")
    return problems


async def run(payload: dict[str, Any]) -> dict[str, Any]:
    """payload: {text, language, reading_level?, protected_terms?[]}.
    Returns {text, english, language, adapted, number_check_passed, uncertainty_flags[]}."""
    source = str(payload.get("text") or "").strip()
    language = payload.get("language") or "English"
    level = payload.get("reading_level") or "standard"
    protected = [term for term in payload.get("protected_terms") or [] if term and term in source]
    english = {"text": source, "english": source, "language": "English", "adapted": False, "number_check_passed": True, "uncertainty_flags": []}
    if not source or (language == "English" and level != "basic") or language not in LANGUAGES:
        return english
    request = {"message": source, "language": LANGUAGES[language], "reading_level": LEVELS.get(level, LEVELS["standard"]), "protected_terms": protected}
    try:
        reply = await ask_groq_json(SYSTEM_PROMPT, json.dumps(request, ensure_ascii=False))
    except (ValueError, GroqError):
        return {**english, "uncertainty_flags": ["translation unavailable"]}
    adapted = str(reply.get("text") or "").strip()
    problems = _checks(source, adapted, protected) if adapted else ["empty translation"]
    if problems:
        return {**english, "number_check_passed": not any("number" in problem for problem in problems), "uncertainty_flags": problems}
    unsure = [str(item) for item in reply.get("unsure") or [] if str(item).strip()][:5]
    return {"text": adapted, "english": source, "language": language, "adapted": True, "number_check_passed": True,
            "uncertainty_flags": [f"unsure: {item}" for item in unsure]}
