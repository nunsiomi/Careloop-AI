"""Barrier Resolution Agent: barrier + context -> options from approved resources (owner: Olamide; Dorcas tests
unresolved-barrier escalation).

Returns structured findings or proposed actions only. Never writes care records
directly; the orchestrator validates and invokes approved tools.

Options come only from data/resources.json (approved by the care facility). It never invents a facility, a cost or
availability, and every option keeps its "not guaranteed" note. Deterministic on purpose: there is nothing here a
model could add safely.
"""

import json
from pathlib import Path
from typing import Any

from app.safety.rules import policy

RESOURCES_PATH = Path(__file__).resolve().parents[3] / "data" / "resources.json"
BARRIER_TYPES = ["cost", "transport", "stock", "understanding"]
# Words patients and the voice worker use for the four stored types (docs/api_shapes.md)
TYPE_ALIASES = {"distance": "transport", "no_helper": "understanding", "other": "understanding", "confusion": "understanding", "stock_out": "stock"}
FALLBACK_NOTE = "Ask them to explain your plan again."


def approved_resources(facility: str | None) -> dict[str, list[dict]]:
    try:
        listed = json.loads(RESOURCES_PATH.read_text(encoding="utf-8"))["resources"]
    except (OSError, ValueError, KeyError):
        listed = []
    grouped: dict[str, list[dict]] = {}
    for item in listed:
        if facility and item.get("facility") not in (facility, None):
            continue
        grouped.setdefault(item["type"], []).append(
            {"name": item["name"], "type": item["kind"], "distance": item["area"], "phone": item["phone_e164"], "note": item["note"]})
    return grouped


def normalize_type(kind: str | None) -> str:
    kind = TYPE_ALIASES.get(kind or "", kind or "")
    return kind if kind in BARRIER_TYPES else "understanding"


def options_for(kind: str, facility: str | None, care_team_phone: str) -> list[dict]:
    """Approved options for one barrier, or the care team itself when the facility listed nothing for it."""
    approved = approved_resources(facility)
    return approved.get(kind) or [{"name": "Your care team", "type": "Care team", "distance": facility or "", "phone": care_team_phone, "note": FALLBACK_NOTE}]


def should_escalate(attempts: int) -> bool:
    """Unresolved after the policy's number of offered options (red_flags.json, policies.barrier_unresolved)."""
    rule = policy("barrier_unresolved")
    return bool(rule.get("enabled")) and attempts >= int(rule.get("after_attempts", 2))


async def run(payload: dict[str, Any]) -> dict[str, Any]:
    """payload: {type, facility, attempts, care_team_phone}. Returns options and whether policy says to escalate."""
    kind = normalize_type(payload.get("type"))
    return {
        "type": kind,
        "options": options_for(kind, payload.get("facility"), payload.get("care_team_phone", "")),
        "escalate": should_escalate(int(payload.get("attempts") or 0)),
        "reply_draft": "Thank you for telling me. Here is an option your care team shared. Please tell me if it worked.",
    }
