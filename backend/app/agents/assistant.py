"""Clinician Assistant Agent (proposed seventh agent, owner Nunsi): a clinician's instruction -> proposed actions.

Returns structured findings or proposed actions only. Never writes care records
directly; the orchestrator validates and invokes approved tools.

The model only proposes. services/assistant.py checks every value against the clinician's own words, applies
consent, and falls back to rules-based drafting when the model is unavailable.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.agents.llm import ask_groq_json, ask_groq_with_tools

PROMPT_PATH = Path(__file__).parent / "prompts" / "assistant_prompt.md"
KINDS = {"medicine", "test", "visit", "send_text", "call_patient", "note"}


async def run(payload: dict[str, Any]) -> list[dict]:
    """payload: {instruction, patient_name, today (aware datetime), timezone, templates[]}. Returns raw proposed actions."""
    today: datetime = payload["today"]
    context = {"instruction": payload["instruction"], "patient": payload["patient_name"], "timezone": payload["timezone"],
               "today": today.strftime("%A %Y-%m-%d %H:%M"), "templates": payload.get("templates", [])}
    reply = await ask_groq_json(PROMPT_PATH.read_text(encoding="utf-8"), json.dumps(context, ensure_ascii=False))
    actions = reply.get("actions")
    if not isinstance(actions, list):
        raise ValueError("model did not return a list of actions")
    return [action for action in actions if isinstance(action, dict) and action.get("kind") in KINDS]


ANSWER_PROMPT_PATH = Path(__file__).parent / "prompts" / "assistant_answer_prompt.md"
LOOK_UP_MEDICINE = {
    "type": "function",
    "function": {
        "name": "look_up_medicine",
        "description": "What a medicine is used for, main warnings, interactions and contraindications, from MedlinePlus and US FDA drug labels.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string", "description": "Medicine name, generic or brand, e.g. amlodipine or Coartem"}},
                       "required": ["name"]},
    },
}


async def answer(payload: dict[str, Any], look_up_medicine) -> str:
    """payload: {question, today, facility_patients[], patient (or None), history[]}. Returns the answer text."""
    context = {key: payload[key] for key in ("today", "facility_patients", "patient")}
    messages = [*payload.get("history", []),
                {"role": "user", "content": f"[Records]\n{json.dumps(context, ensure_ascii=False, default=str)}\n\n[Question]\n{payload['question']}"}]
    text = await ask_groq_with_tools(ANSWER_PROMPT_PATH.read_text(encoding="utf-8"), messages, [LOOK_UP_MEDICINE],
                                     {"look_up_medicine": look_up_medicine})
    text = re.sub(r"\*\*|__|^#+\s*", "", text, flags=re.M)  # the dashboard shows plain text
    if not text.strip():
        raise ValueError("model gave an empty answer")
    return text.strip()
