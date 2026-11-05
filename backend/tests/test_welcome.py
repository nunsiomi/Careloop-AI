# backend/tests/test_welcome.py
# Every assistant is Tomi, and she opens with a greeting by first name, what she can do, and questions to tap
# (decided by Nunsi, 5 Nov 2026). Patients get prepared lines in their language; staff get their own patients.
import asyncio

from app.db import store
from app.services import welcome
from tests.test_api import patient_sign_in, staff_sign_in


def test_patient_chat_opens_with_tomi_in_their_language(client, mailbox):
    patient_sign_in(client, mailbox, "zainab.musa@kestrelmail.ng")
    greeting = client.get("/api/patients/p-zainab/messages").json()["welcome"]
    assert greeting["text"].startswith("Sannu Zainab, ni ce Tomi")
    assert greeting["suggestions"][0] == "Me ke cikin tsarin yau?"
    assert all("{" not in item for item in greeting["suggestions"])


def test_english_welcome_names_only_what_is_on_the_plan(client):
    patient = {**store().get("patients", "p-tola"), "language": "English"}
    greeting = welcome.for_patient(patient, "Tola Adeyemi")
    assert greeting["text"].split("\n") == [
        "Hello Tola, I am Tomi, your CareLoop assistant.",
        "I can tell you what is on the plan today, when the next visit is, and what a medicine on the plan is for. Anything else, I pass to the care team.",
        "What would you like to ask?",
    ]
    assert "What is Amlodipine for?" in greeting["suggestions"]


def test_a_caregiver_is_greeted_by_their_own_name(client):
    greeting = welcome.for_patient(store().get("patients", "p-zainab"), "Hadiza Musa")
    assert greeting["text"].startswith("Sannu Hadiza,")


def test_staff_welcome_uses_their_first_name_and_their_patients(client, mailbox):
    staff_sign_in(client, mailbox)
    greeting = client.get("/api/assistant/welcome").json()["welcome"]
    assert ", Ada. I am Tomi, your CareLoop assistant." in greeting["text"].split("\n")[0]
    assert greeting["suggestions"][:2] == ["Who needs attention today?", "How is Tola doing?"]

    one = client.get("/api/assistant/welcome", params={"patient_id": "p-zainab"}).json()["welcome"]
    assert one["suggestions"][:2] == ["How is Zainab doing?", "What medicines is Zainab on?"]
    assert client.get("/api/assistant/welcome", params={"patient_id": "p-nobody"}).status_code == 404


def test_tapped_questions_are_answered_from_the_plan_without_a_model(client, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    from app.services import chat
    patient = store().get("patients", "p-tola")
    today = asyncio.run(chat.handle(patient, {"original_text": "What is on the plan today?"}))["reply"]
    assert today.startswith("Today on the plan:\n- ") or today == "There is nothing on the plan for today."
    visit = asyncio.run(chat.handle(patient, {"original_text": "When is the next visit?"}))["reply"]
    assert visit.startswith("The next visit: ") or visit.startswith("There is no visit booked")
    problem = asyncio.run(chat.handle(patient, {"original_text": "Is it okay that the medicine costs too much today?"}))
    assert problem["barrier"] and not problem["reply"].startswith("Today on the plan")


def test_titles_are_not_first_names():
    assert welcome.first_name("Dr. Ada Okafor") == "Ada"
    assert welcome.first_name("Nurse Bisi Ola") == "Bisi"
    assert welcome.first_name("") == ""
