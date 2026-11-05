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


async def ask_groq_with_tools(system_prompt: str, messages: list[dict], tools: list[dict], handlers: dict[str, Any],
                              rounds: int = 3, temperature: float = 0.2) -> str:
    """A conversation in which the model may call our tools (handlers: name -> async function returning a dict).
    Returns the model's final text. Raises ValueError or groq.GroqError like ask_groq_json."""
    conversation = [{"role": "system", "content": system_prompt}, *messages]
    for round_number in range(rounds):
        last = round_number == rounds - 1  # the last round must answer with what it has
        response = await groq_client().chat.completions.create(
            model=model(), messages=conversation, tools=tools, tool_choice="none" if last else "auto", temperature=temperature)
        message = response.choices[0].message
        if not message.tool_calls:
            return (message.content or "").strip()
        conversation.append({"role": "assistant", "content": message.content or "",
                             "tool_calls": [{"id": call.id, "type": "function", "function": {"name": call.function.name, "arguments": call.function.arguments}}
                                            for call in message.tool_calls]})
        for call in message.tool_calls:
            handler = handlers.get(call.function.name)
            try:
                arguments = json.loads(call.function.arguments or "{}")
                result = await handler(**arguments) if handler else {"error": "No such tool."}
            except (TypeError, ValueError) as error:
                result = {"error": f"Bad arguments: {error}"}
            if result is None:
                result = {"error": "Not available right now. Say you could not check it."}
            conversation.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False)})
    raise ValueError("model kept calling tools without answering")
