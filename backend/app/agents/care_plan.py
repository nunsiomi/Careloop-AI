"""Care Plan Agent: discharge note + profile -> structured plan JSON (owner: Mary).

Returns structured findings or proposed actions only. Never writes care records
directly; the orchestrator validates and invokes approved tools.

The model drafts the plan; then the rule checks in plan_rules remove anything the note does not support
(a medicine, visit or test that is not in the note; a dose, date, time or length of treatment that does not
match it). Whatever is missing or unclear comes back as `unresolved`, and any high-severity item keeps the
plan from being delivered until the clinician fixes it and approves.
"""

import json
import os
import re
from pathlib import Path
from typing import Any

from groq import AsyncGroq, GroqError
from pydantic import ValidationError

from app.agents import plan_rules
from app.models import CarePlanResult, PlanDraft, PlanIssue

PROMPT_PATH = Path(__file__).parent / "prompts" / "care_plan_prompt.md"
FIELD_PATH = re.compile(r"^(medications|appointments|tests)\[(\d+)\]\.(\w+)$")
MAX_ATTEMPTS = 2


async def ask_groq_json(system_prompt: str, user_content: str) -> dict[str, Any]:
    """One Groq call that must return a JSON object. Shared by the Care Plan Agent and the Plan Verifier
    (move to the shared Groq client once it exists; launch checklist, section 3)."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is missing or empty.")
    client = AsyncGroq(api_key=api_key, timeout=30)
    response = await client.chat.completions.create(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    data = json.loads(response.choices[0].message.content or "")
    if not isinstance(data, dict):
        raise ValueError("model did not return a JSON object")
    return data


def _ground(note: str, plan: PlanDraft) -> PlanDraft:
    """Drop or blank every value the rule checks find unsupported by the note."""
    for _ in range(3):  # dropping an item renumbers the rest, so check again
        invented = [finding.issue.field for finding in plan_rules.check(note, plan) if finding.invented]
        if not invented:
            break
        data = plan.model_dump()
        drop: dict[str, set[int]] = {}
        for field in invented:
            match = FIELD_PATH.match(field)
            if not match:
                continue
            section, index, key = match.group(1), int(match.group(2)), match.group(3)
            if key in ("name", "what"):
                drop.setdefault(section, set()).add(index)  # the whole medicine, visit or test is not in the note
            else:
                data[section][index][key] = [] if key == "times" else ""
        for section, indexes in drop.items():
            data[section] = [item for position, item in enumerate(data[section]) if position not in indexes]
        data["reminder_times"] = sorted({time for medication in data["medications"] for time in medication["times"]})
        plan = PlanDraft.model_validate(data)
    return plan


def _model_unclear(note: str, raw: Any) -> list[PlanIssue]:
    """Keep the model's own 'unclear' notes when they quote the note exactly."""
    kept = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field", ""))
        high = field.split(".")[-1] in ("name", "dose", "frequency", "duration")
        try:
            issue = PlanIssue(field=field, issue=str(item.get("issue", "")), source_text=str(item.get("source_text", "")),
                              severity="high" if high else "medium")
        except ValidationError:
            continue
        if issue.field and issue.issue and issue.source_text and issue.source_text in note:
            kept.append(issue)
    return kept


def _merge(rule_issues: list[PlanIssue], extra: list[PlanIssue]) -> list[PlanIssue]:
    fields = {issue.field for issue in rule_issues}
    return rule_issues + [issue for issue in extra if issue.field not in fields]


async def run(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Care Plan Agent entry point called by Olamide's orchestrator.
    Expects payload with 'source_note' and optionally 'patient' ({'name': ...}).
    Returns CarePlanResult as a dict, plus 'error' when no draft could be made.
    """
    note = payload.get("source_note", "") or ""
    patient_name = (payload.get("patient") or {}).get("name", "")
    if not note.strip():
        return _failed("The discharge note is empty")
    if not os.getenv("GROQ_API_KEY"):
        raise ValueError("GROQ_API_KEY environment variable is missing or empty.")

    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    user_content = f"[Discharge note]\n{note}"
    raw: dict[str, Any] = {}
    draft = None
    for _ in range(MAX_ATTEMPTS):
        try:
            raw = await ask_groq_json(system_prompt, user_content)
            draft = PlanDraft.model_validate(raw)
            break
        except (ValueError, ValidationError, GroqError):  # ValueError covers bad JSON
            continue
    if draft is None:
        return _failed("The model did not return a valid plan")

    plan = _ground(note, draft)
    unresolved = _merge(plan_rules.issues(note, plan, patient_name), _model_unclear(note, raw.get("unclear")))
    return CarePlanResult(plan=plan, unresolved=unresolved, deliverable=not plan_rules.has_blocking(unresolved)).model_dump()


def _failed(reason: str) -> dict[str, Any]:
    issue = PlanIssue(field="plan", issue=f"{reason}; enter the plan by hand", severity="high")
    result = CarePlanResult(plan=PlanDraft(), unresolved=[issue], deliverable=False).model_dump()
    return {**result, "error": reason}
