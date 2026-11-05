"""Plan Verifier Agent: source note + plan JSON -> field diff and verdict (owner: Mary).

Returns structured findings or proposed actions only. Never writes care records
directly; the orchestrator validates and invokes approved tools.

Two passes: the rule checks in plan_rules always run; then the model looks for anything the rules cannot see
(meaning changes, things left out). Model findings are kept only when they point at a real plan field and quote
the note exactly. A "clean" verdict never replaces clinician approval, and any high-severity issue makes the plan
not deliverable.
"""

import os
import re
from pathlib import Path
from typing import Any

from groq import GroqError
from pydantic import BaseModel, ValidationError

from app.agents import plan_rules
from app.agents.llm import ask_groq_json
from app.models import PlanDraft, PlanIssue, VerifierResult

PROMPT_PATH = Path(__file__).parent / "prompts" / "plan_verifier_prompt.md"
LISTS = ("medications", "appointments", "tests", "symptoms_to_watch", "reminder_times")
ITEM_FIELD = re.compile(r"^(medications|appointments|tests|symptoms_to_watch|reminder_times)\[(\d+)\](?:\.(\w+))?$")


def _field_exists(plan: PlanDraft, field: str) -> bool:
    if field in LISTS:
        return True
    match = ITEM_FIELD.match(field)
    if not match:
        return False
    items = getattr(plan, match.group(1))
    if int(match.group(2)) >= len(items):
        return False
    item, key = items[int(match.group(2))], match.group(3)
    if key is None:
        return True
    return isinstance(item, BaseModel) and key in type(item).model_fields


def _model_issues(note: str, plan: PlanDraft, raw: Any) -> list[PlanIssue]:
    kept = []
    for item in (raw.get("issues") if isinstance(raw, dict) else None) or []:
        if not isinstance(item, dict):
            continue
        try:
            issue = PlanIssue.model_validate({key: item.get(key, "") for key in ("field", "issue", "severity", "source_text")})
        except ValidationError:
            continue
        if not issue.issue or not _field_exists(plan, issue.field) or issue.field.startswith("reminder_times"):
            continue  # reminder times come from the medicine times; the rule checks cover them exactly
        if issue.source_text not in note:
            continue  # the dashboard highlights source_text in the note, so it must be an exact quote
        kept.append(issue)
    return kept


def _invalid_plan(error: ValidationError) -> list[PlanIssue]:
    found = []
    for problem in error.errors():
        location = problem["loc"]
        path = "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in location).lstrip(".")
        found.append(PlanIssue(field=path or "plan", issue=f"Not a valid value: {problem['msg']}", severity="high"))
    return found


async def run(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Plan Verifier entry point called by Olamide's orchestrator.
    Expects payload with 'source_note', 'plan' (the plan JSON; extra keys such as id and status are ignored),
    and optionally 'patient' ({'name': ...}) and 'use_model' (default True).
    Returns VerifierResult as a dict.
    """
    note = payload.get("source_note", "") or ""
    patient_name = (payload.get("patient") or {}).get("name", "")
    try:
        plan = PlanDraft.model_validate(payload.get("plan") or {})
    except ValidationError as error:
        found = _invalid_plan(error)
        return VerifierResult(verdict="flagged", issues=found, deliverable=False, model_checked=False).model_dump()

    found = plan_rules.issues(note, plan, patient_name)

    model_checked = False
    if payload.get("use_model", True) and os.getenv("GROQ_API_KEY"):
        prompt = PROMPT_PATH.read_text(encoding="utf-8")
        content = f"[Discharge note]\n{note}\n\n[Draft plan]\n{plan.model_dump_json(indent=2)}"
        try:
            raw = await ask_groq_json(prompt, content)
            flagged = {issue.field for issue in found}
            found += [issue for issue in _model_issues(note, plan, raw) if issue.field not in flagged]
            model_checked = True
        except (ValueError, GroqError):
            pass  # the rule checks still stand; model_checked tells the dashboard the second pass did not run

    return VerifierResult(
        verdict="flagged" if found else "clean",
        issues=found,
        deliverable=not plan_rules.has_blocking(found),
        model_checked=model_checked,
    ).model_dump()
