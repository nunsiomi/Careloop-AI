# backend/tests/test_assistant.py
# Clinician Assistant: the model only proposes; anything not in the clinician's own words is cleared and flagged.
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def groq_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "mock_key_for_testing")


def draft(client, mailbox, text, proposed):
    from tests.test_api import staff_sign_in
    staff_sign_in(client, mailbox)
    with patch("app.agents.assistant.ask_groq_json", AsyncMock(return_value={"actions": proposed})):
        response = client.post("/api/assistant/drafts", json={"text": text, "patient_id": "p-zainab"})
    assert response.status_code == 200, response.text
    return response.json()["draft"]["actions"]


def test_invented_dose_place_and_date_are_cleared(client, mailbox, groq_key):
    actions = draft(client, mailbox, "Start her on paracetamol and book a review", [
        {"kind": "medicine", "title": "Paracetamol 500 mg tablet", "detail": "2 tablets", "times": ["08:00", "20:00"], "days": 5, "issues": []},
        {"kind": "visit", "what": "Review visit", "where": "Medical Outpatients", "starts_at": "2026-12-01T10:00:00+01:00", "issues": []},
    ])
    medicine, visit = actions
    assert medicine["detail"] == "" and medicine["title"] in ("", "Paracetamol")
    assert medicine["days"] == 7 and medicine["times"] == ["08:00"]
    assert any("dose" in issue for issue in medicine["issues"])
    assert visit["where"] == "" and visit["starts_at"] is None
    assert {"No place given. Add where the visit is.", "No date or time given. Set when the visit is."} <= set(visit["issues"])


def test_values_the_clinician_said_are_kept(client, mailbox, groq_key):
    actions = draft(client, mailbox, "Add paracetamol 500mg, 2 tablets twice a day for 5 days", [
        {"kind": "medicine", "title": "Paracetamol 500 mg tablet", "detail": "2 tablets", "times": ["08:00", "20:00"], "days": 5, "issues": []},
    ])
    assert actions[0]["title"] == "Paracetamol 500 mg tablet" and actions[0]["detail"] == "2 tablets"
    assert actions[0]["days"] == 5 and actions[0]["issues"] == []


def test_consent_is_enforced_whatever_the_model_says(client, mailbox, groq_key):
    from app.db import store
    store().get("patients", "p-zainab")["channels"] = ["web"]
    actions = draft(client, mailbox, "Email her about the visit and call her", [
        {"kind": "send_text", "template": "visit", "issues": []}, {"kind": "call_patient", "issues": []},
    ])
    assert all(action["blocked"] for action in actions)


def test_without_the_model_the_rules_draft_is_used(client, mailbox, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    actions = draft(client, mailbox, "Note that she prefers evening calls", [{"kind": "medicine", "title": "Invented"}])
    assert [action["kind"] for action in actions] == ["note"]  # no GROQ_API_KEY: the model was never asked
