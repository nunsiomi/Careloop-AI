# backend/tests/test_end_to_end.py
# The full run from the launch checklist: discharge note -> approved plan -> reminder email -> Tomi call ->
# escalation on the dashboard. Every step goes through the HTTP API the frontend and the voice worker use; only Groq
# (the plan agents' replies) and the email provider are stood in for.
import asyncio
import re
from unittest.mock import AsyncMock, patch

from app.db import store
from app.services import escalations, outbox
from app.util import iso, now
from tests.test_api import ADA, SAMPLES, staff_sign_in, tola_reply

WORKER = {"Authorization": "Bearer test-worker-token"}
PHONE, EMAIL = "+2348000000160", "amaka.obi@example.com"


def test_discharge_note_to_escalation_on_the_dashboard(client, mailbox):
    # 1. The care team adds the patient and pastes the discharge note. Tomi drafts the plan; nothing is sent yet.
    staff_sign_in(client, mailbox)
    patient = client.post("/api/patients", json={"name": "Amaka Obi", "phone_e164": PHONE, "email": EMAIL, "language": "Igbo"}).json()["patient"]
    note = (SAMPLES / "tola-adeyemi.txt").read_text(encoding="utf-8").replace("Tola Adeyemi", "Amaka Obi")
    with patch("app.agents.care_plan.ask_groq_json", AsyncMock(return_value=tola_reply())), \
         patch("app.agents.plan_verifier.ask_groq_json", AsyncMock(return_value={"issues": []})):
        plan = client.post(f"/api/patients/{patient['id']}/plan", json={"patient_id": patient["id"], "source_note": note}).json()["plan"]
    assert plan["status"] == "needs_review"
    assert not store().where("tasks", patient_id=patient["id"]) and not store().where("notifications", patient_id=patient["id"])
    assert not [mail for mail in mailbox.sent if mail["to"] == EMAIL]

    # 2. A clinician approves it. Tasks are made and the patient is invited by email.
    assert client.post(f"/api/plans/{plan['id']}/approve", json={"override_issues": False}).json()["plan"]["status"] == "approved"
    tasks = store().where("tasks", patient_id=patient["id"])
    assert tasks and all(task["title"] == "Amlodipine 5 mg tablet" for task in tasks)
    invite = re.search(r"invite code is (CL-[A-Z0-9]{4})", next(mail["text"] for mail in mailbox.sent if mail["to"] == EMAIL)).group(1)
    client.post("/api/auth/staff/sign-out", json={})

    # 3. The patient joins with the invite code and an email code, sets a PIN and agrees to email and calls.
    challenge = client.post(f"/api/auth/invites/{invite}/otp", json={"via": "email", "email": EMAIL}).json()
    session = client.post(f"/api/auth/patient/otp/{challenge['challenge_id']}/verify", json={"code": mailbox.last_code(EMAIL)}).json()["session"]
    assert session["patient_id"] == patient["id"] and session["consent_needed"] is True
    client.post(f"/api/patients/{patient['id']}/consent", json={"channels": ["web", "email", "voice"], "pin": "4826", "scope": "patient_follow_up", "version": "v1"})
    queued = store().where("notifications", patient_id=patient["id"], status="scheduled")
    assert queued and {item["channel"] for item in queued} == {"email"}

    # 4. The first reminder comes due and goes by email. It names no medicine.
    first = min(queued, key=lambda item: item["scheduled_for"])
    first["scheduled_for"] = iso(now())
    asyncio.run(outbox.send_due())
    assert first["status"] == "sent"
    reminder = [mail for mail in mailbox.sent if mail["to"] == EMAIL][-1]
    assert reminder["subject"] == "A reminder from your care team" and "Amlodipine" not in reminder["text"]
    client.post("/api/auth/patient/sign-out")

    # 5. The patient calls Tomi. Their number is on file, so there is no PIN; they report the medicine taken,
    #    then say something that sounds like an emergency.
    call = client.post("/api/voice/calls", json={"direction": "inbound", "phone_e164": PHONE}, headers=WORKER).json()["call"]
    assert call["known"] is True
    context = client.get(f"/api/voice/calls/{call['id']}/context", headers=WORKER).json()["context"]
    assert context["patient"]["language"] == "Igbo" and context["plan"]["status"] == "approved"
    client.post(f"/api/voice/calls/{call['id']}/task-updates", json={"task_id": context["tasks"][0]["id"], "status": "done"}, headers=WORKER)
    turn = client.post(f"/api/voice/calls/{call['id']}/turns/check", json={"text": "obi m na-afu m ufu", "language": "ig"}, headers=WORKER).json()
    assert turn["action"] == "escalate" and turn["escalation"]["call_number"] == "112"
    client.post(f"/api/voice/calls/{call['id']}/end", json={"outcome": "escalated"}, headers=WORKER)

    # 6. The care team is emailed (no patient details) and sees the escalation on the dashboard.
    asyncio.run(escalations.send_alerts())
    alert = [mail for mail in mailbox.sent if mail["to"] == ADA["email"] and "escalation" in mail["subject"]][-1]
    assert "Amaka" not in alert["text"]
    staff_sign_in(client, mailbox)
    open_items = client.get("/api/escalations", params={"status": "open"}).json()["escalations"]
    escalation = next(item for item in open_items if item["id"] == turn["escalation"]["id"])
    assert escalation["status"] == "delivered" and escalation["call_id"] == call["id"] and escalation["channel"] == "voice"
    assert '"obi m na-afu m ufu"' in escalation["brief"]

    timeline = [event["event_type"] for event in reversed(client.get(f"/api/patients/{patient['id']}/events").json()["events"])]
    expected = ["patient_created", "plan_approved", "consent_recorded", "notification_sent", "task_reported", "escalation_created", "call_completed"]
    positions = [timeline.index(kind) for kind in expected]
    assert positions == sorted(positions), timeline

    # 7. A clinician acknowledges and resolves it; the record keeps who did what.
    client.post(f"/api/escalations/{escalation['id']}/acknowledge")
    resolved = client.post(f"/api/escalations/{escalation['id']}/resolve", json={"note": "Spoke to Amaka; she went to the emergency unit."}).json()["escalation"]
    assert [step["status"] for step in resolved["history"]] == ["created", "notification_attempted", "delivered", "acknowledged", "resolved"]
