"""Escalation Summary Agent: logged escalation + events -> fact-only brief (owner: Dorcas).

Returns structured findings or proposed actions only. Never writes care records
directly; the orchestrator validates and invokes approved tools.

`build_brief` writes the brief from the record alone, at once, so the care team never waits for a model.
`run` asks Groq for a shorter brief from the same facts and keeps it only if it passes every check: it quotes the
patient's own words, adds no number that is not in the facts, and uses none of the words that would choose a
diagnosis or urgency or suggest help is on the way. Otherwise the rule-written brief stands.
"""

import json
import re
from typing import Any

from groq import GroqError

from app.agents.llm import ask_groq_json
from app.safety import number_check

FORBIDDEN = re.compile(r"\b(diagnos\w*|likely|probabl\w*|suggests?|consistent with|heart attack|myocardial|infarction|cardiac arrest|angina|"
                       r"sepsis|pneumonia|emergency services|ambulance|dispatched|on (?:the|their) way|critical(?:ly)?|life[- ]threatening|"
                       r"urgent(?:ly)?|immediately|must|should)\b", re.I)
SYSTEM_PROMPT = """You write a short factual brief for a clinician about one escalation in CareLoop.
Use only the facts given. Quote the patient's words exactly. Do not name a diagnosis or condition, do not judge how
urgent it is, do not suggest what to do, and do not say anyone has been sent or called. No numbers that are not in the
facts. At most four sentences.
Return JSON: {"brief": "..."}"""


def facts(escalation: dict, open_items: list[str], when: str) -> dict:
    return {
        "when": when, "channel": escalation.get("channel"), "rule": escalation.get("rule_label"),
        "patient_words": escalation.get("original_text"), "english_meaning": escalation.get("english_text"),
        "speech_confidence": escalation.get("confidence"), "open_items": open_items,
        "guidance_given": escalation.get("severity") == "red",
    }


def build_brief(escalation: dict, open_items: list[str], when: str) -> str:
    said = "said" if escalation.get("channel") in ("voice", "browser_voice") else "wrote"
    parts = [f'At {when}, by {escalation.get("channel") or "message"}, the patient {said}: "{escalation.get("original_text")}".']
    if escalation.get("english_text") and escalation["english_text"] != escalation.get("original_text"):
        parts.append(f'In English: "{escalation["english_text"]}".')
    if escalation.get("confidence") is not None:
        parts.append(f"Speech confidence {escalation['confidence']:.2f}.")
    parts.append(f"Rule: {escalation.get('rule_label')}.")
    if escalation.get("severity") == "red":
        parts.append("The approved emergency guidance was given.")
    parts.append(f"Open items: {'; '.join(open_items) if open_items else 'none recorded'}.")
    return " ".join(parts)


def passes_checks(brief: str, fact_set: dict) -> bool:
    source = json.dumps(fact_set, ensure_ascii=False)
    words = str(fact_set.get("patient_words") or "")
    if not brief or (words and words not in brief):
        return False
    allowed_terms = FORBIDDEN.findall(source)  # e.g. a rule label the clinic itself wrote
    if any(term.lower() not in (item.lower() for item in allowed_terms) for term in FORBIDDEN.findall(brief)):
        return False
    return number_check.check(brief, [source]).passed


async def run(payload: dict[str, Any]) -> dict[str, Any]:
    """payload: {escalation, open_items[], when, use_model?}. Returns {brief, model_used}."""
    escalation, open_items, when = payload["escalation"], payload.get("open_items") or [], payload.get("when") or ""
    fallback = build_brief(escalation, open_items, when)
    if not payload.get("use_model", True):
        return {"brief": fallback, "model_used": False}
    fact_set = facts(escalation, open_items, when)
    try:
        reply = await ask_groq_json(SYSTEM_PROMPT, json.dumps(fact_set, ensure_ascii=False))
    except (ValueError, GroqError):
        return {"brief": fallback, "model_used": False}
    brief = str(reply.get("brief") or "").strip()
    return {"brief": brief, "model_used": True} if passes_checks(brief, fact_set) else {"brief": fallback, "model_used": False}
