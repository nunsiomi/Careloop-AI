"""Tomi's chat answers (decided by Nunsi, 5 Nov 2026): questions about the patient's own plan, what a medicine on
the plan is generally for (MedlinePlus only), and handing anything else to the care team.

Returns a reply draft only. services/chat.py runs it after the Check-in Agent found nothing to record, and still
applies the safety rules, the advice guard and the number check before anything is sent.
"""

import json
from pathlib import Path
from typing import Any

from app.agents.llm import ask_groq_with_tools

PROMPT_PATH = Path(__file__).parent / "prompts" / "tomi_chat_prompt.md"
TOOLS = [
    {"type": "function", "function": {
        "name": "look_up_medicine",
        "description": "What a medicine on the patient's plan is generally used for, from MedlinePlus (US National Library of Medicine).",
        "parameters": {"type": "object", "properties": {"name": {"type": "string", "description": "The medicine name as written on the plan"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "ask_care_team",
        "description": "Pass the patient's question to their care team when the plan does not answer it, including any medical question.",
        "parameters": {"type": "object", "properties": {"question": {"type": "string", "description": "The question, in the patient's own words"}}, "required": ["question"]}}},
    {"type": "function", "function": {
        "name": "ask_to_move_visit",
        "description": "Ask the clinic for a new time for the patient's next visit. The current visit stays booked until the clinic confirms.",
        "parameters": {"type": "object", "properties": {"reason": {"type": "string", "description": "Why, in the patient's own words"}}, "required": ["reason"]}}},
]


async def run(payload: dict[str, Any], handlers: dict[str, Any]) -> str:
    """payload: {message, patient (patients brief), speaker, history[]}. handlers: look_up_medicine, ask_care_team, ask_to_move_visit."""
    about = {"today": payload.get("today"), "speaker": payload.get("speaker"), **payload["patient"]}
    messages = [*payload.get("history", []),
                {"role": "user", "content": f"[About the patient]\n{json.dumps(about, ensure_ascii=False)}\n\n[Message]\n{payload['message']}"}]
    return await ask_groq_with_tools(PROMPT_PATH.read_text(encoding="utf-8"), messages, TOOLS, handlers)
