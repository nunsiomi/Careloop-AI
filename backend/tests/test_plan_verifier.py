# backend/tests/test_plan_verifier.py
# Plan integrity tests (project documentation, section 17): five synthetic notes with seeded dose and date errors.
import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.agents import plan_verifier

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "sample_discharges"
EXPECTED = {name: case for name, case in json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8")).items()
            if not name.startswith("_")}


def note(name: str) -> str:
    return (SAMPLES / name).read_text(encoding="utf-8")


async def verify(source_note: str, plan: dict, **extra) -> dict:
    return await plan_verifier.run({"source_note": source_note, "plan": plan, "use_model": False, **extra})


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(EXPECTED))
async def test_sample_notes_raise_the_expected_issues(name):
    case = EXPECTED[name]
    result = await verify(note(name), case["plan"])

    assert sorted((issue["field"], issue["severity"]) for issue in result["issues"]) == \
        sorted((issue["field"], issue["severity"]) for issue in case["issues"])
    for issue in result["issues"]:
        assert issue["source_text"] in note(name)  # the dashboard highlights it, so it must be an exact quote
    assert result["verdict"] == ("flagged" if case["issues"] else "clean")
    assert result["deliverable"] == all(issue["severity"] != "high" for issue in case["issues"])
    assert result["model_checked"] is False


def tola_plan() -> dict:
    return copy.deepcopy(EXPECTED["tola-adeyemi.txt"]["plan"])


@pytest.mark.asyncio
@pytest.mark.parametrize("change, field", [
    (lambda plan: plan["medications"][0].update(dose="2 tablets"), "medications[0].dose"),
    (lambda plan: plan["medications"][0].update(name="Amlodipine 10 mg tablet"), "medications[0].name"),
    (lambda plan: plan["medications"][0].update(duration="30 days"), "medications[0].duration"),
    (lambda plan: plan["medications"][0].update(frequency=""), "medications[0].frequency"),
    (lambda plan: plan["appointments"][0].update(date="2026-11-16"), "appointments[0].date"),
    (lambda plan: plan["appointments"][0].update(time="10:00"), "appointments[0].time"),
    (lambda plan: plan["medications"].append({"name": "Aspirin 75 mg tablet", "dose": "1 tablet", "frequency": "Daily", "times": []}), "medications[1].name"),
    (lambda plan: plan.update(medications=[]), "medications"),
])
async def test_seeded_plan_errors_block_delivery(change, field):
    plan = tola_plan()
    change(plan)

    result = await verify(note("tola-adeyemi.txt"), plan)

    assert (field, "high") in [(issue["field"], issue["severity"]) for issue in result["issues"]]
    assert result["verdict"] == "flagged"
    assert result["deliverable"] is False


@pytest.mark.asyncio
async def test_wording_changes_with_the_same_meaning_pass():
    plan = tola_plan()
    plan["medications"][0].update(dose="One tablet", frequency="Each morning")

    result = await verify(note("tola-adeyemi.txt"), plan)

    assert result["verdict"] == "clean"


@pytest.mark.asyncio
async def test_extra_instructions_and_symptoms_are_flagged():
    plan = tola_plan()
    plan["medications"][0]["instructions"] = "Take with water"
    plan["symptoms_to_watch"].append("Headache")

    result = await verify(note("tola-adeyemi.txt"), plan)

    fields = {issue["field"]: issue["severity"] for issue in result["issues"]}
    assert fields == {"medications[0].instructions": "medium", "symptoms_to_watch[2]": "medium"}
    assert result["deliverable"] is True  # medium issues need review but do not block on their own


@pytest.mark.asyncio
async def test_wrong_patient_is_flagged():
    result = await verify(note("tola-adeyemi.txt"), tola_plan(), patient={"name": "Zainab Musa"})

    assert ("source_note", "high") in [(issue["field"], issue["severity"]) for issue in result["issues"]]


@pytest.mark.asyncio
async def test_malformed_plan_is_flagged_not_crashed():
    plan = tola_plan()
    plan["medications"][0]["times"] = ["9am"]

    result = await verify(note("tola-adeyemi.txt"), plan)

    assert result["verdict"] == "flagged"
    assert result["deliverable"] is False
    assert result["issues"][0]["field"].startswith("medications[0].times")


@pytest.mark.asyncio
async def test_model_findings_must_quote_the_note_and_name_a_real_field(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "mock_key_for_testing")
    source = note("grace-bassey.txt")
    model_reply = {"issues": [
        {"field": "medications[0].frequency", "issue": "Plan says twice daily; check it matches", "severity": "medium", "source_text": "twice daily"},
        {"field": "medications[0].dose", "issue": "Invented quote", "severity": "high", "source_text": "two tablets twice daily"},
        {"field": "medications[5].dose", "issue": "No such medicine", "severity": "high", "source_text": "Metformin"},
        {"field": "appointments[0].date", "issue": "Duplicate of a rule finding", "severity": "high", "source_text": ""},
        {"field": "tests", "issue": "Bad severity", "severity": "urgent", "source_text": ""},
    ]}

    with patch("app.agents.plan_verifier.ask_groq_json", AsyncMock(return_value=model_reply)):
        result = await plan_verifier.run({"source_note": source, "plan": EXPECTED["grace-bassey.txt"]["plan"]})

    assert result["model_checked"] is True
    assert [(issue["field"], issue["severity"]) for issue in result["issues"]] == [
        ("appointments[0].date", "medium"),       # the rule finding wins over the model's duplicate
        ("medications[0].frequency", "medium"),   # the only model finding that quotes the note and names a real field
    ]


@pytest.mark.asyncio
async def test_rule_checks_stand_when_the_model_fails(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "mock_key_for_testing")

    with patch("app.agents.plan_verifier.ask_groq_json", AsyncMock(side_effect=ValueError("bad JSON"))):
        result = await plan_verifier.run({"source_note": note("ibrahim-danjuma.txt"), "plan": EXPECTED["ibrahim-danjuma.txt"]["plan"]})

    assert result["model_checked"] is False
    assert result["deliverable"] is False
    assert len(result["issues"]) == len(EXPECTED["ibrahim-danjuma.txt"]["issues"])
