"""Check-in Agent: verified inbound text + task history -> intent/tool proposal (owner: Dorcas).

Returns structured findings or proposed actions only. Never writes care records
directly; the orchestrator validates and invokes approved tools.
"""

# backend/app/agents/checkin.py
import json
from pathlib import Path
from typing import Any
from app.agents.llm import groq_client, model as groq_model

# 1. Load System Prompt from Markdown
PROMPT_PATH = Path(__file__).parent / "prompts" / "checkin_prompt.md"

# Barrier types as stored on a Barrier record (docs/api_shapes.md)
BARRIER_TYPES = ["cost", "transport", "stock", "understanding"]

def load_system_prompt() -> str:
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "You are the Check-in Agent for CareLoop AI, supporting patients with post-discharge care plans. "
        "Process messages, track tasks, and log barriers safely without giving medical advice."
    )

# 2. Define Tools for Groq Function Calling
CHECKIN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "report_barrier",
            "description": "Use when the patient reports a barrier: cost, transport, stock (not available) or understanding (unsure what to do).",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "The ID of the task associated with the barrier"},
                    "barrier_type": {"type": "string", "enum": BARRIER_TYPES}
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

def _task_ids(care_plan: dict[str, Any]) -> set[str]:
    return {task.get("id") for task in care_plan.get("tasks", []) if isinstance(task, dict)}

async def run(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Check-in Agent entry point called by Olamide's orchestrator.
    Expects payload with 'message', 'care_plan', and 'history'.
    Returns structured action intent, tool proposals, and reply draft.
    """
    # Shared Groq client (agents/llm.py): model from GROQ_MODEL, timeouts and retries in one place
    client = groq_client()
    model = groq_model()

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

    # Call the Groq model with tools enabled
    response = await client.chat.completions.create(
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
    confidence_state = "confident"

    # Parse any tool call the model proposed, and only keep it if it matches the care plan
    if getattr(response_message, "tool_calls", None):
        tool_call = response_message.tool_calls[0]
        func_name = tool_call.function.name
        try:
            func_args = json.loads(tool_call.function.arguments or "{}")
        except json.JSONDecodeError:
            func_args = {}

        valid = (
            func_name in ("report_barrier", "mark_task_done")
            and func_args.get("task_id") in _task_ids(care_plan)
            and (func_name != "report_barrier" or func_args.get("barrier_type") in BARRIER_TYPES)
        )
        if valid:
            intent = func_name
            task_id = func_args["task_id"]
            barrier_type = func_args.get("barrier_type") if func_name == "report_barrier" else None
            # Both change the patient's record, so the patient confirms first
            requires_confirmation = True
        else:
            confidence_state = "needs_confirmation"
            if not response_message.content:
                reply_draft = "Sorry, I did not quite follow. Which part of your care plan do you mean?"

    # Return the clean structured contract dictionary expected by Olamide
    return {
        "intent": intent,
        "task_id": task_id,
        "barrier_type": barrier_type,
        "requires_confirmation": requires_confirmation,
        "confidence_state": confidence_state,
        "reply_draft": reply_draft
    }
