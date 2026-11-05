"""Clinician Assistant Agent (proposed seventh agent, owner Nunsi): a clinician's instruction -> proposed actions.

Returns structured findings or proposed actions only. Never writes care records
directly; the orchestrator validates and invokes approved tools.

The model only proposes. services/assistant.py checks every value against the clinician's own words, applies
consent, and falls back to rules-based drafting when the model is unavailable.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.agents.llm import ask_groq_json

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
