# backend/tests/test_chat.py
# Chat with safety first and the Check-in Agent's proposals confirmed by the patient; escalation alerts and backup.
import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from app.db import store
from app.services import escalations
from app.util import iso, now
from tests.test_api import patient_sign_in


def tola(client, mailbox):
    patient_sign_in(client, mailbox, "0800 000 0102", "tola.adeyemi@kestrelmail.ng")


def say(client, text, **extra):
    response = client.post("/api/patients/p-tola/messages", json={"original_text": text, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def proposal(intent="general_checkin", task_id=None, barrier_type=None, reply="Thank you for telling me."):
    return {"intent": intent, "task_id": task_id, "barrier_type": barrier_type, "requires_confirmation": intent != "general_checkin",
            "confidence_state": "confident", "reply_draft": reply}


def future_task():
    return store().add("tasks", {"id": "t-t9", "patient_id": "p-tola", "type": "medication", "title": "Amlodipine 5 mg tablet", "detail": "1 tablet",
                                 "due_at": iso(now() + timedelta(hours=3)), "criticality": "high", "status": "pending", "last_reported_at": None})


def test_negated_red_flag_is_checked_then_escalated_on_yes(client, mailbox):
    tola(client, mailbox)
    asked = say(client, "I have no chest pain today")
    assert asked["escalation"] is None and "nearest hospital" in asked["reply"]["original_text"]

    confirmed = say(client, "yes")
    assert confirmed["escalation"]["call_number"] == "112"


def test_negated_red_flag_answered_no_does_not_escalate(client, mailbox):
    tola(client, mailbox)
    say(client, "I have no chest pain today")
    answered = say(client, "no")
    assert answered["escalation"] is None
    assert not store().where("escalations", patient_id="p-tola", status="created")


def test_task_done_from_free_text_waits_for_the_patients_yes(client, mailbox):
    tola(client, mailbox)
    task = future_task()
    with patch("app.agents.checkin.run", AsyncMock(return_value=proposal("mark_task_done", task_id=task["id"]))):
        asked = say(client, "I took my pills just now")
    assert "Is that right?" in asked["reply"]["original_text"] and task["status"] == "pending"

    say(client, "yes")
    assert task["status"] == "patient_reported_done"


def test_task_done_answered_no_changes_nothing(client, mailbox):
    tola(client, mailbox)
    task = future_task()
    with patch("app.agents.checkin.run", AsyncMock(return_value=proposal("mark_task_done", task_id=task["id"]))):
        say(client, "I took my pills just now")
    say(client, "no")
    assert task["status"] == "pending"


def test_checkin_barrier_opens_an_approved_option(client, mailbox):
    tola(client, mailbox)
    with patch("app.agents.checkin.run", AsyncMock(return_value=proposal("report_barrier", task_id="t-t1", barrier_type="cost"))):
        result = say(client, "Money is hard this week")
    assert result["barrier"]["type"] == "cost" and result["barrier"]["options"][0]["name"] == "Kestrel Patient Support Desk"


def test_model_reply_with_a_new_number_or_advice_is_replaced(client, mailbox):
    tola(client, mailbox)
    for draft in ["Take 2 tablets tonight to catch up.", "You can stop taking it if you feel better."]:
        with patch("app.agents.checkin.run", AsyncMock(return_value=proposal(reply=draft))):
            result = say(client, "How am I doing?")
        assert result["reply"]["original_text"] == "Thank you. Your message has been received. Your care team can see it."


def test_red_flag_skips_the_checkin_agent(client, mailbox):
    tola(client, mailbox)
    agent = AsyncMock(return_value=proposal())
    with patch("app.agents.checkin.run", agent):
        result = say(client, "I took it but I passed out after")
    agent.assert_not_awaited()
    assert result["escalation"]


def test_barrier_not_solved_after_two_tries_escalates_once(client, mailbox):
    tola(client, mailbox)
    say(client, "Transport", quick_reply="transport")
    say(client, "Transport", quick_reply="transport")
    say(client, "It did not work", quick_reply="did_not_work")
    say(client, "It did not work", quick_reply="did_not_work")
    raised = store().where("escalations", patient_id="p-tola", rule_id="barrier_unresolved")
    assert len(raised) == 1 and raised[0]["severity"] == "amber"


def test_care_team_is_emailed_without_patient_details_then_backup(client, mailbox):
    tola(client, mailbox)
    record = say(client, "My chest hurts")["escalation"]
    escalation = store().get("escalations", record["id"])
    alert = mailbox.sent[-1]
    assert alert["to"] == "ada.okafor@kestrelgeneral.ng" and "Tola" not in alert["text"] and "chest" not in alert["text"].lower()
    assert [entry["status"] for entry in escalation["history"]] == ["created", "notification_attempted", "delivered"]

    escalation["alert_sent_at"] = iso(now() - timedelta(minutes=16))
    asyncio.run(escalations.send_alerts())
    assert escalation["history"][-1]["status"] == "backup_contacted"
    assert mailbox.sent[-1]["subject"].startswith("Reminder")


def test_overdue_critical_task_raises_one_amber_escalation(client):
    from app.scheduler import mark_overdue
    task = store().add("tasks", {"id": "t-late", "patient_id": "p-chidi", "type": "medication", "title": "Amlodipine 5 mg tablet", "detail": "1 tablet",
                                 "due_at": iso(now() - timedelta(hours=3)), "criticality": "high", "status": "pending", "last_reported_at": None})
    mark_overdue()
    mark_overdue()
    raised = store().where("escalations", rule_id="missed_critical_task", target_id=task["id"])
    assert task["status"] == "overdue" and len(raised) == 1 and raised[0]["severity"] == "amber"


def test_worker_turn_with_a_negated_flag_continues(client):
    headers = {"Authorization": "Bearer test-worker-token"}
    call = client.post("/api/voice/calls", json={"direction": "inbound", "phone_e164": "+2348000000101"}, headers=headers).json()["call"]
    client.post(f"/api/voice/calls/{call['id']}/verify-pin", json={"phone_e164": "+2348000000101", "pin": "1234"}, headers=headers)
    result = client.post(f"/api/voice/calls/{call['id']}/turns/check", json={"text": "I have no chest pain", "language": "en"}, headers=headers).json()
    assert result == {"action": "continue"}


def test_worker_unclear_turn_is_clarified_unless_it_holds_a_danger_word(client):
    headers = {"Authorization": "Bearer test-worker-token"}
    call = client.post("/api/voice/calls", json={"direction": "inbound", "phone_e164": "+2348000000101"}, headers=headers).json()["call"]
    client.post(f"/api/voice/calls/{call['id']}/verify-pin", json={"phone_e164": "+2348000000101", "pin": "1234"}, headers=headers)
    check = lambda text: client.post(f"/api/voice/calls/{call['id']}/turns/check", json={"text": text, "language": "ha", "confidence": 0.4}, headers=headers).json()
    assert check("mm ba") == {"action": "clarify"}
    assert check("mm kirji ba")["action"] == "escalate"


def test_patient_not_joined_after_24_hours_gets_one_reminder(client, mailbox):
    from app.scheduler import invite_followups
    store().get("patients", "p-chidi")["email"] = "chidi.okeke@example.com"
    invite = store().get("invites", "CL-7K4Q")
    invite["created_at"] = iso(now() - timedelta(hours=25))
    asyncio.run(invite_followups())
    asyncio.run(invite_followups())
    reminders = [mail for mail in mailbox.sent if mail["subject"] == "Reminder: your CareLoop invite"]
    assert len(reminders) == 1 and "CL-7K4Q" in reminders[0]["text"]
    assert store().first("events", patient_id="p-chidi", event_type="invite_follow_up")


def test_patient_without_email_is_flagged_for_the_care_team(client, mailbox):
    from app.scheduler import invite_followups
    invite = store().get("invites", "CL-7K4Q")
    invite["created_at"] = iso(now() - timedelta(hours=25))
    asyncio.run(invite_followups())
    event = store().first("events", patient_id="p-chidi", event_type="invite_follow_up")
    assert "no email address" in event["summary"] and not mailbox.sent
