"""Check-in Agent: verified inbound text + task history -> intent/tool proposal (owner: Dorcas).

Returns structured findings or proposed actions only. Never writes care records
directly; the orchestrator validates and invokes approved tools.
"""

# backend/app/agents/checkin.py
import json
import os
from pathlib import Path
from typing import Any
from groq import Groq

# 1. Load System Prompt from Markdown
PROMPT_PATH = Path(__file__).parent / "prompts" / "checkin_prompt.md"

def load_system_prompt() -> str:
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "You are the Check-in Agent for CareLoop AI, supporting patients with post-discharge care plans. "
        "Process messages, track tasks, and log barriers safely without giving medical advice."
    )

# 2. Define Tools for Grok Function Calling
CHECKIN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "report_barrier",
            "description": "Use when the patient reports a barrier like cost, transport, or stock-out.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "The ID of the task associated with the barrier"},
                    "barrier_type": {"type": "string", "enum": ["cost", "transport", "stock_out", "confusion"]}
                },
                "required": ["task_id", "barrier_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mark_task_done",
            "description": "Mark a care plan task as completed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "The ID of the task completed"}
                },
                "required": ["task_id"]
            }
        }
    }
]

async def run(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Check-in Agent entry point called by Olamide's orchestrator.
    Expects payload with 'message', 'care_plan', and 'history'.
    Returns structured action intent, tool proposals, and reply draft.
    """
    # Initialize Groq client using environment variables
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is missing or empty.")
    
    client = Groq(api_key=api_key)
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

    patient_message = payload.get("message", "")
    care_plan = payload.get("care_plan", {})
    history = payload.get("history", [])

    system_prompt = load_system_prompt()

    # Construct messages array for the Groq client
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({
        "role": "user", 
        "content": f"[Care Plan Context]: {json.dumps(care_plan)}\n\n[Patient Message]: {patient_message}"
    })

    # Call Grok model with tools enabled
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=CHECKIN_TOOLS,
        tool_choice="auto"
    )

    response_message = response.choices[0].message
    reply_draft = response_message.content or "Thank you for your update. Keep following your care plan."
    
    intent = "general_checkin"
    task_id = None
    barrier_type = None
    requires_confirmation = False

    # Parse any tool calls requested by Grok
    if hasattr(response_message, "tool_calls") and response_message.tool_calls:
        tool_call = response_message.tool_calls[0]
        func_name = tool_call.function.name
        func_args = json.loads(tool_call.function.arguments)

        intent = func_name
        task_id = func_args.get("task_id")
        if func_name == "report_barrier":
            barrier_type = func_args.get("barrier_type")
            requires_confirmation = True

    # Return the clean structured contract dictionary expected by Olamide
    return {
        "intent": intent,
        "task_id": task_id,
        "barrier_type": barrier_type,
        "requires_confirmation": requires_confirmation,
        "confidence_state": "confident",
        "reply_draft": reply_draft
    }


