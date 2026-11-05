# backend/tests/test_care_plan.py
import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.agents import care_plan

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "sample_discharges"
EXPECTED = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))


def note(name: str) -> str:
    return (SAMPLES / name).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def groq_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "mock_key_for_testing")


async def draft(name: str, model_reply, **payload) -> tuple[dict, AsyncMock]:
    mock = AsyncMock(side_effect=model_reply) if isinstance(model_reply, list) else AsyncMock(return_value=model_reply)
    with patch("app.agents.care_plan.ask_groq_json", mock):
        result = await care_plan.run({"source_note": note(name), **payload})
    return result, mock


@pytest.mark.asyncio
async def test_faithful_draft_of_a_complete_note_is_deliverable():
    reply = copy.deepcopy(EXPECTED["tola-adeyemi.txt"]["plan"])

    result, _ = await draft("tola-adeyemi.txt", reply, patient={"name": "Tola Adeyemi"})

    assert result["plan"] == EXPECTED["tola-adeyemi.txt"]["plan"]
    assert result["unresolved"] == []
    assert result["deliverable"] is True


@pytest.mark.asyncio
async def test_incomplete_dose_line_blocks_delivery():
    reply = copy.deepcopy(EXPECTED["zainab-musa.txt"]["plan"])

    result, _ = await draft("zainab-musa.txt", reply)

    assert ("medications[1].name", "high") in [(issue["field"], issue["severity"]) for issue in result["unresolved"]]
    assert result["deliverable"] is False


@pytest.mark.asyncio
async def test_invented_values_are_removed_not_delivered():
    reply = copy.deepcopy(EXPECTED["ibrahim-danjuma.txt"]["plan"])
    reply["medications"][0].update(dose="1 capsule", frequency="Three times daily", times=["08:00", "14:00", "20:00"])
    reply["medications"].append({"name": "Paracetamol 500 mg tablet", "dose": "2 tablets", "frequency": "As needed"})
    reply["appointments"][0].update(date="2026-11-09", time="10:00")
    reply["tests"].append({"name": "Full blood count", "where": "Laboratory", "date": ""})
    reply["reminder_times"] = ["08:00", "14:00", "20:00"]

    result, _ = await draft("ibrahim-danjuma.txt", reply)
    plan = result["plan"]

    assert [medication["name"] for medication in plan["medications"]] == ["Amoxicillin 500 mg capsule"]
    assert plan["medications"][0]["dose"] == ""          # "1 capsule" is not in the note
    assert plan["appointments"][0]["date"] == ""          # the note only says "next week"
    assert plan["appointments"][0]["time"] == ""
    assert plan["tests"] == []
    assert plan["medications"][0]["times"] == []          # no clock times in the note
    assert plan["reminder_times"] == []
    fields = {issue["field"] for issue in result["unresolved"]}
    assert {"medications[0].dose", "medications[0].frequency", "appointments[0].date"} <= fields
    assert result["deliverable"] is False


@pytest.mark.asyncio
async def test_model_unclear_notes_kept_only_with_exact_quotes():
    reply = copy.deepcopy(EXPECTED["grace-bassey.txt"]["plan"])
    reply["unclear"] = [
        {"field": "medications[0].duration", "issue": "No length of treatment given", "source_text": "Metformin 500 mg tablet"},
        {"field": "tests", "issue": "Made-up quote", "source_text": "HbA1c in 3 months"},
    ]

    result, _ = await draft("grace-bassey.txt", reply)

    unresolved = {issue["field"]: issue for issue in result["unresolved"]}
    assert unresolved["medications[0].duration"]["severity"] == "high"
    assert "tests" not in unresolved


@pytest.mark.asyncio
async def test_malformed_model_output_is_retried_then_reported():
    result, mock = await draft("tola-adeyemi.txt", [ValueError("not JSON"), {"medications": [{"times": ["morning"]}]}])

    assert mock.await_count == care_plan.MAX_ATTEMPTS
    assert result["error"] == "The model did not return a valid plan"
    assert result["deliverable"] is False
    assert result["plan"]["medications"] == []


@pytest.mark.asyncio
async def test_retry_recovers_from_one_bad_reply():
    reply = copy.deepcopy(EXPECTED["tola-adeyemi.txt"]["plan"])

    result, mock = await draft("tola-adeyemi.txt", [ValueError("not JSON"), reply])

    assert mock.await_count == 2
    assert "error" not in result
    assert result["deliverable"] is True


@pytest.mark.asyncio
async def test_empty_note_never_calls_the_model():
    with patch("app.agents.care_plan.ask_groq_json", AsyncMock()) as mock:
        result = await care_plan.run({"source_note": "   "})

    mock.assert_not_awaited()
    assert result["error"] == "The discharge note is empty"
