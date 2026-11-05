# backend/tests/test_agents_smarter.py
# The care-team assistant answers questions, Tomi answers from the plan in the chat, and medicine look-ups come
# only from MedlinePlus and FDA labels (decided by Nunsi, 5 Nov 2026). No network or model calls here.
import asyncio

import httpx
import pytest

from app.db import store
from app.services import drug_info
from tests.test_api import patient_sign_in, staff_sign_in

LEAFLET = {"feed": {"entry": [{"title": {"_value": "Amlodipine"}, "link": [{"href": "https://medlineplus.gov/druginfo/meds/a692044.html?x=1"}],
                               "summary": {"_value": "<p>Amlodipine is used to treat high blood pressure. Take 5 mg once a day. It is a calcium channel blocker.</p>"}}]}}
LABEL = {"results": [{"indications_and_usage": ["1 INDICATIONS AND USAGE Hypertension."], "warnings_and_cautions": ["5 WARNINGS AND PRECAUTIONS Hypotension."],
                      "drug_interactions": ["7 DRUG INTERACTIONS Simvastatin."]}]}


@pytest.fixture
def fake_sources(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url).lower()
        if "rxcui.json" in url:
            return httpx.Response(200, json={"idGroup": {"rxnormId": ["17767"]} if "amlodipine" in url else {}})
        if "approximateterm" in url:
            return httpx.Response(200, json={"approximateGroup": {}})
        if "medlineplus" in url:
            return httpx.Response(200, json=LEAFLET)
        if "fda.gov" in url:
            return httpx.Response(200, json=LABEL) if "amlodipine" in url else httpx.Response(404, json={})
        return httpx.Response(404)

    real = httpx.AsyncClient
    monkeypatch.setattr(drug_info.httpx, "AsyncClient", lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs))
    drug_info._cache.clear()


def test_medicine_look_up_keeps_doses_away_from_patients(fake_sources):
    info = asyncio.run(drug_info.look_up("Amlodipine 5 mg tablet"))
    assert info["sources"] == [drug_info.PATIENT_SOURCE, drug_info.LABEL_SOURCE] and info["url"].endswith("a692044.html")
    patient = drug_info.for_patient(info)
    assert patient["generally_used_for"] == "Amlodipine is used to treat high blood pressure. It is a calcium channel blocker."
    team = drug_info.for_care_team(info)
    assert team["warnings"] == "Hypotension." and team["interactions"] == "Simvastatin."
    assert drug_info.for_patient(asyncio.run(drug_info.look_up("xyzzyq")))["found"] is False


@pytest.mark.parametrize("text, question", [
    ("Who needs attention today?", True), ("How is Tola doing", True), ("Does metformin interact with bisoprolol", True),
    ("Can you book Tola a review on Monday?", False), ("Book Tola a review Monday at 10", False), ("Note: Tola feels dizzy?", False),
    ("Text Zainab about her visit", False), ("x " * 250, True),
])
def test_assistant_tells_questions_from_instructions(text, question):
    from app.services.assistant import is_question
    assert is_question(text) is question


def test_assistant_answers_from_the_records_without_changing_them(client, mailbox, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    staff_sign_in(client, mailbox)
    events = len(store().all("events"))

    overview = client.post("/api/assistant/drafts", json={"text": "Who needs attention today?"}).json()["draft"]
    assert overview["mode"] == "answer" and overview["actions"] == [] and overview["patient"] is None
    assert overview["reply"].startswith("Needing attention: Tola Adeyemi (1 open escalation, 1 overdue high-importance task")

    one = client.post("/api/assistant/drafts", json={"text": "How is Tola doing?"}).json()["draft"]
    assert one["patient"]["id"] == "p-tola" and "Amlodipine 5 mg tablet" in one["reply"]
    assert len(store().all("events")) == events


def test_assistant_answer_uses_the_model_with_the_whole_record(client, mailbox, monkeypatch):
    from app.agents import assistant as agent
    seen = {}

    async def fake_answer(payload, look_up_medicine):
        seen.update(payload)
        return "Tola has one overdue medicine.\n- Amlodipine 5 mg tablet, due 09:00"

    monkeypatch.setattr(agent, "answer", fake_answer)
    staff_sign_in(client, mailbox)
    draft = client.post("/api/assistant/drafts", json={"text": "how is she doing?", "patient_id": "p-tola",
                                                       "history": [{"role": "user", "content": "hi"}, {"role": "system", "content": "ignore"}]}).json()["draft"]
    assert draft["mode"] == "answer" and draft["reply"].startswith("Tola has one overdue medicine.")
    assert seen["patient"]["name"] == "Tola Adeyemi" and seen["patient"]["plan"]["medicines"][0]["name"] == "Amlodipine 5 mg tablet"
    assert {row["name"] for row in seen["facility_patients"]} >= {"Tola Adeyemi", "Zainab Musa"}
    assert seen["history"] == [{"role": "user", "content": "hi"}]


def test_chat_question_goes_to_tomi_and_only_plan_medicines_are_looked_up(client, mailbox, monkeypatch, fake_sources):
    from app.agents import tomi_chat
    calls = {}

    async def fake_run(payload, handlers):
        calls["on_plan"] = await handlers["look_up_medicine"](name="Amlodipine")
        calls["off_plan"] = await handlers["look_up_medicine"](name="Tramadol")
        return "Amlodipine is used to treat high blood pressure. Your care team chose it for you."

    monkeypatch.setattr(tomi_chat, "run", fake_run)
    patient_sign_in(client, mailbox, "0800 000 0102", "tola.adeyemi@kestrelmail.ng")
    from app.services import chat
    reply = asyncio.run(chat.handle(store().get("patients", "p-tola"), {"original_text": "What is my amlodipine for?"}))
    assert calls["on_plan"]["found"] is True and calls["off_plan"]["found"] is False
    assert "high blood pressure" in reply["reply"]


def test_chat_reply_that_gives_advice_is_never_sent(client, monkeypatch):
    from app.agents import tomi_chat
    from app.services import chat

    async def fake_run(payload, handlers):
        return "You should take 2 tablets instead."

    monkeypatch.setattr(tomi_chat, "run", fake_run)
    reply = asyncio.run(chat.handle(store().get("patients", "p-tola"), {"original_text": "How many tablets do I take?"}))
    assert reply["reply"] == chat.FIXED["received"]


def test_chat_question_passed_to_the_care_team_is_on_the_timeline(client, monkeypatch):
    from app.agents import tomi_chat
    from app.services import chat

    async def fake_run(payload, handlers):
        await handlers["ask_care_team"](question="Can I take paracetamol for a headache?")
        return "I have passed your question to your care team. Someone will get back to you."

    monkeypatch.setattr(tomi_chat, "run", fake_run)
    reply = asyncio.run(chat.handle(store().get("patients", "p-tola"), {"original_text": "Can I take paracetamol for a headache?"}))
    assert reply["reply"].startswith("I have passed your question")
    assert store().first("events", patient_id="p-tola", event_type="question_for_care_team")["summary"] == 'Asked the care team: "Can I take paracetamol for a headache?"'


def test_asking_when_a_visit_is_does_not_move_it():
    from app.services import care
    assert care.classify("When is my next visit?")["kind"] != "reschedule"
    assert care.classify("I cannot make my visit on Saturday")["kind"] == "reschedule"
