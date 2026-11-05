"""Shared Groq client for the agents (owner: Olamide). The model comes from GROQ_MODEL, so it can be changed in
one place. Agents check the JSON they get back against their Pydantic contract (app/models.py) and retry once.
"""

import json
import os
from typing import Any

from groq import AsyncGroq

DEFAULT_MODEL = "openai/gpt-oss-120b"
TIMEOUT_SECONDS = 30


def model() -> str:
    return os.getenv("GROQ_MODEL") or DEFAULT_MODEL


def groq_client() -> AsyncGroq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is missing or empty.")
    return AsyncGroq(api_key=api_key, timeout=TIMEOUT_SECONDS, max_retries=2)


async def ask_groq_json(system_prompt: str, user_content: str) -> dict[str, Any]:
    """One call that must return a JSON object; raises ValueError (bad JSON) or groq.GroqError (API trouble)."""
    response = await groq_client().chat.completions.create(
        model=model(),
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    data = json.loads(response.choices[0].message.content or "")
    if not isinstance(data, dict):
        raise ValueError("model did not return a JSON object")
    return data
