# backend/tests/test_api.py
# End-to-end checks of the HTTP API against docs/api_shapes.md, with the seeded sample facility.
import asyncio
import copy
import json
import re
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.db import store
from app.services import outbox
from app.util import iso, now

ADA = {"email": "ada.okafor@kestrelgeneral.ng", "password": "Blue-ward-morning-24"}
SAMPLES = Path(__file__).resolve().parents[2] / "data" / "sample_discharges"


def staff_sign_in(client: TestClient, mailbox, email=ADA["email"], password=ADA["password"]) -> dict:
    started = client.post("/api/auth/staff/sign-in", json={"email": email, "password": password})
    assert started.status_code == 200, started.text
    verified = client.post("/api/auth/staff/mfa", json={"mfa_token": started.json()["mfa_token"], "code": mailbox.last_code(email)})
    assert verified.status_code == 200, verified.text
    return verified.json()["session"]


def patient_sign_in(client: TestClient, mailbox, phone: str, email: str) -> dict:
    challenge = client.post("/api/auth/patient/otp", json={"phone": phone, "via": "email"}).json()
    verified = client.post(f"/api/auth/patient/otp/{challenge['challenge_id']}/verify", json={"code": mailbox.last_code(email)})
    assert verified.status_code == 200, verified.text
    return verified.json()["session"]


# ----- care team

def test_staff_sign_in_needs_password_and_email_code(client, mailbox):
    wrong = client.post("/api/auth/staff/sign-in", json={"email": ADA["email"], "password": "not-the-password"})
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == "That email and password do not match. Check both and try again."
    assert client.get("/api/patients").status_code == 401

    session = staff_sign_in(client, mailbox)

    assert session["user"]["facility"] == "Kestrel General Hospital"
    assert session["user"]["initials"] == "AO"
    assert "set-cookie" not in {key.lower() for key in session}
    patients = client.get("/api/patients").json()["patients"]
    assert {item["id"] for item in patients} == {"p-zainab", "p-tola", "p-chidi", "p-grace", "p-ibrahim"}
    assert not any("pin_hash" in item for item in patients)
    assert client.get("/api/auth/staff/session").json()["session"]["user"]["email"] == ADA["email"]


def test_unknown_staff_email_gets_the_same_answer(client, mailbox):
    unknown = client.post("/api/auth/staff/sign-in", json={"email": "nobody@example.com", "password": ADA["password"]})
    reset = client.post("/api/auth/staff/password-reset", json={"email": "nobody@example.com"})

    assert unknown.status_code == 401 and unknown.json()["detail"].startswith("That email and password do not match")
    assert reset.json() == {"ok": True}
    assert mailbox.sent == []


def test_staff_password_reset_link_sets_a_new_password_once(client, mailbox):
    assert client.post("/api/auth/staff/password-reset", json={"email": ADA["email"]}).json() == {"ok": True}
    mail = mailbox.sent[-1]
    assert mail["to"] == ADA["email"]
    link = re.search(r"http://localhost:5173/clinician/#/reset-password/(\S+)", mail["text"])
    assert link, mail["text"]
    token = link.group(1)

    assert client.get(f"/api/auth/staff/password-reset/{token}").json()["email_masked"].endswith("@kestrelgeneral.ng")
    assert client.post(f"/api/auth/staff/password-reset/{token}", json={"password": "short1"}).status_code == 400
    assert client.post(f"/api/auth/staff/password-reset/{token}", json={"password": "ward4day"}).status_code == 200
    assert client.post(f"/api/auth/staff/password-reset/{token}", json={"password": "ward4day"}).status_code == 410

    assert client.post("/api/auth/staff/sign-in", json=ADA).status_code == 401
    staff_sign_in(client, mailbox, password="ward4day")


def test_patient_forgot_pin_emails_a_code_then_sets_a_new_pin(client, mailbox):
    phone, email = "0800 000 0102", "tola.adeyemi@kestrelmail.ng"
    patient_sign_in(client, mailbox, phone, email)
    assert mailbox.sent[-1]["to"] == email
    assert client.post("/api/auth/patient/pin", json={"pin": "4071"}).status_code == 200

    assert client.post("/api/auth/patient/pin-sign-in", json={"phone_e164": "+2348000000102", "pin": "1234"}).status_code == 401
    assert client.post("/api/auth/patient/pin-sign-in", json={"phone_e164": "+2348000000102", "pin": "4071"}).status_code == 200


def test_staff_from_another_facility_see_none_of_kestrels_patients(client, mailbox):
    facilities = client.get("/api/facilities").json()
    assert all("join_code" not in item and "demo_join_code" not in item for item in facilities["facilities"])
    form = {"name": "Kemi Ade", "email": "kemi.ade@example.com", "password": "quiet-river-lantern-9", "facility_id": "egret", "role": "Nurse", "confirmed": True}

    wrong = client.post("/api/auth/staff/sign-up", json={**form, "join_code": "KGH-4821"})
    assert wrong.status_code == 403 and wrong.json()["field"] == "join_code"

    started = client.post("/api/auth/staff/sign-up", json={**form, "join_code": "eth-3067"}).json()
    session = client.post("/api/auth/staff/sign-up/verify", json={"signup_token": started["signup_token"], "code": mailbox.last_code("kemi.ade@example.com")}).json()["session"]

    assert session["user"]["facility"] == "Egret Teaching Hospital"
    assert client.get("/api/patients").json()["patients"] == []
    assert client.get("/api/patients/p-zainab").status_code == 404
    assert client.get("/api/escalations").json()["escalations"] == []
    assert client.post("/api/escalations/e-1/acknowledge").status_code == 404


# ----- patients

def test_patient_signs_in_with_an_email_code_and_sees_only_their_record(client, mailbox):
    session = patient_sign_in(client, mailbox, "0800 000 0101", "zainab.musa@kestrelmail.ng")

    assert (session["kind"], session["patient_id"], session["pin_set"]) == ("patient", "p-zainab", True)
    assert client.get("/api/patients/p-zainab").status_code == 200
    assert client.get("/api/patients/p-tola").status_code == 404
    assert client.get("/api/patients").status_code == 401  # the dashboard list is staff only


def test_unknown_number_gets_the_same_answer_and_no_email(client, mailbox):
    known = client.post("/api/auth/patient/otp", json={"phone": "0800 000 0101"}).json()
    sent_before = len(mailbox.sent)
    unknown = client.post("/api/auth/patient/otp", json={"phone": "0800 000 0999"}).json()

    assert set(known) == set(unknown) and known["masked_email"] is None and unknown["masked_email"] is None
    assert len(mailbox.sent) == sent_before
    assert client.post(f"/api/auth/patient/otp/{unknown['challenge_id']}/verify", json={"code": "123456"}).status_code == 401


def test_codes_by_phone_are_not_offered_yet(client):
    response = client.post("/api/auth/patient/otp", json={"phone": "0800 000 0101", "via": "sms"})
    assert response.status_code == 503
    assert client.post("/api/auth/patient/otp", json={"phone": "0800 000 0101", "via": "voice"}).status_code == 503  # no Termii key


def test_code_by_text_goes_only_to_known_numbers(client, monkeypatch):
    from app.adapters import SendResult
    from app.services import identity
    texts = []

    async def fake_text(to_e164, code):
        texts.append((to_e164, code))
        return SendResult(ok=True, provider_id="t-2")

    monkeypatch.setattr(identity, "sms_available", lambda: True)
    monkeypatch.setattr(identity, "send_sign_in_code_sms", fake_text)

    known = client.post("/api/auth/patient/otp", json={"phone": "0800 000 0101", "via": "sms"}).json()
    unknown = client.post("/api/auth/patient/otp", json={"phone": "0800 000 0999", "via": "sms"}).json()

    assert set(known) == set(unknown) and known["via"] == unknown["via"] == "sms"
    assert [to for to, _ in texts] == ["+2348000000101"]
    verified = client.post(f"/api/auth/patient/otp/{known['challenge_id']}/verify", json={"code": texts[0][1]})
    assert verified.status_code == 200 and verified.json()["session"]["patient_id"] == "p-zainab"


def test_code_by_phone_call_rings_only_known_numbers(client, monkeypatch):
    from app.adapters import SendResult
    from app.services import identity
    calls = []

    async def fake_call(to_e164, code):
        calls.append((to_e164, code))
        return SendResult(ok=True, provider_id="t-1")

    monkeypatch.setenv("VOICE_CODE_PROVIDER", "termii")
    monkeypatch.setattr(identity, "call_code", fake_call)

    known = client.post("/api/auth/patient/otp", json={"phone": "0800 000 0101", "via": "voice"}).json()
    unknown = client.post("/api/auth/patient/otp", json={"phone": "0800 000 0999", "via": "voice"}).json()

    assert set(known) == set(unknown) and known["via"] == unknown["via"] == "voice"
    assert [to for to, _ in calls] == ["+2348000000101"]
    verified = client.post(f"/api/auth/patient/otp/{known['challenge_id']}/verify", json={"code": calls[0][1]})
    assert verified.status_code == 200 and verified.json()["session"]["patient_id"] == "p-zainab"


def test_five_wrong_pins_lock_pin_sign_in(client):
    for _ in range(4):
        assert client.post("/api/auth/patient/pin-sign-in", json={"phone_e164": "+2348000000102", "pin": "9999"}).status_code == 401
    locked = client.post("/api/auth/patient/pin-sign-in", json={"phone_e164": "+2348000000102", "pin": "9999"})
    assert locked.status_code == 401 and locked.json()["locked"] is True
    assert client.post("/api/auth/patient/pin-sign-in", json={"phone_e164": "+2348000000102", "pin": "1234"}).status_code == 429


def test_invite_collects_email_then_consent_starts_email_reminders(client, mailbox):
    invite = client.get("/api/auth/invites/CL-7K4Q").json()["invite"]
    assert invite["patient_first_name"] == "Chidi" and invite["masked_phone"].endswith("0103")

    challenge = client.post("/api/auth/invites/CL-7K4Q/otp", json={"via": "email", "email": "chidi.okeke@example.com"}).json()
    assert challenge["masked_email"].endswith("@example.com")
    session = client.post(f"/api/auth/patient/otp/{challenge['challenge_id']}/verify", json={"code": mailbox.last_code("chidi.okeke@example.com")}).json()["session"]
    assert session["consent_needed"] is True
    store().add("tasks", {"id": "t-c2", "patient_id": "p-chidi", "type": "medication", "title": "Amlodipine 5 mg tablet", "detail": "1 tablet",
                          "due_at": iso(now() + timedelta(days=1)), "criticality": "high", "status": "pending", "last_reported_at": None})

    consented = client.post("/api/patients/p-chidi/consent", json={"channels": ["web", "email"], "scope": "patient_follow_up", "version": "v1"}).json()["patient"]
    assert consented["email"] == "chidi.okeke@example.com" and consented["activation_status"] == "active"
    queued = client.get("/api/notifications", params={"patient_id": "p-chidi", "status": "upcoming"}).json()["notifications"]
    assert queued and {item["channel"] for item in queued} == {"email"}
    assert client.get("/api/auth/invites/CL-7K4Q").status_code == 410


def test_red_flag_in_chat_opens_an_escalation_for_the_care_team(client, mailbox):
    patient_sign_in(client, mailbox, "0800 000 0102", "tola.adeyemi@kestrelmail.ng")
    sent = client.post("/api/patients/p-tola/messages", json={"original_text": "My chest hurts and I cannot breathe", "language": "Yoruba"}).json()

    assert sent["escalation"]["call_number"] == "112"
    assert sent["reply"]["original_text"].endswith("This may need urgent care. Please go to the nearest hospital now, or call 112. I have sent this to your care team.")
    client.post("/api/auth/patient/sign-out")
    staff_sign_in(client, mailbox)
    open_items = client.get("/api/escalations", params={"status": "open"}).json()["escalations"]
    assert any(item["id"] == sent["escalation"]["id"] and item["brief_ready"] for item in open_items)


# ----- plans

def tola_reply():
    return copy.deepcopy(json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))["tola-adeyemi.txt"]["plan"])


def test_plan_flow_drafts_verifies_approves_and_creates_tasks(client, mailbox):
    staff_sign_in(client, mailbox)
    created = client.post("/api/patients", json={"name": "Amaka Obi", "phone_e164": "+234 0800 000 0150", "email": "amaka.obi@example.com", "language": "Igbo"})
    assert created.status_code == 200, created.text
    patient = created.json()["patient"]
    note = (SAMPLES / "tola-adeyemi.txt").read_text(encoding="utf-8").replace("Tola Adeyemi", "Amaka Obi")

    with patch("app.agents.care_plan.ask_groq_json", AsyncMock(return_value=tola_reply())), \
         patch("app.agents.plan_verifier.ask_groq_json", AsyncMock(return_value={"issues": []})):
        plan = client.post(f"/api/patients/{patient['id']}/plan", json={"patient_id": patient["id"], "source_note": note}).json()["plan"]

    assert plan["status"] == "needs_review" and plan["verifier_issues"] == [] and plan["deliverable"] is True
    assert plan["medications"][0]["name"] == "Amlodipine 5 mg tablet"
    approved = client.post(f"/api/plans/{plan['id']}/approve", json={"override_issues": False}).json()["plan"]
    assert approved["status"] == "approved" and approved["approved_by"] == "Dr. Ada Okafor"

    detail = client.get(f"/api/patients/{patient['id']}/plan").json()
    assert detail["tasks"] and all(task["title"] == "Amlodipine 5 mg tablet" for task in detail["tasks"])
    assert any("invite code is CL-" in mail["text"] for mail in mailbox.sent if mail["to"] == "amaka.obi@example.com")


def test_plan_with_a_serious_issue_needs_explicit_acknowledgement(client, mailbox):
    staff_sign_in(client, mailbox)
    plan = client.get("/api/patients/p-ibrahim/plan").json()["plan"]

    blocked = client.post(f"/api/plans/{plan['id']}/approve", json={"override_issues": False})
    assert blocked.status_code == 409
    assert client.post(f"/api/plans/{plan['id']}/approve", json={"override_issues": True}).status_code == 200


def test_editing_a_plan_rechecks_it_against_the_note(client, mailbox):
    staff_sign_in(client, mailbox)
    plan = client.get("/api/patients/p-grace/plan").json()["plan"]

    edited = client.patch(f"/api/plans/{plan['id']}", json={"medications": [{**plan["medications"][0], "dose": "2 tablets"}]}).json()["plan"]

    assert ("medications[0].dose", "high") in [(item["field"], item["severity"]) for item in edited["verifier_issues"]]
    assert edited["deliverable"] is False


# ----- reminders

def test_due_reminders_are_sent_by_email(client, mailbox):
    zainab = store().get("patients", "p-zainab")
    message = outbox.queue_message(zainab, channel="email", template="medicine", scheduled_for="2020-01-01T00:00:00.000Z")

    asyncio.run(outbox.send_due())

    assert message["status"] == "sent" and message["provider_id"]
    assert mailbox.sent[-1]["to"] == "zainab.musa@kestrelmail.ng"
    assert "Amlodipine" not in mailbox.sent[-1]["text"]


# ----- Tomi worker

def test_worker_routes_need_the_service_token(client):
    assert client.post("/api/voice/calls", json={"direction": "inbound"}).status_code == 401


def test_worker_phone_call_pin_context_and_safety_check(client):
    headers = {"Authorization": "Bearer test-worker-token"}
    call = client.post("/api/voice/calls", json={"direction": "inbound", "phone_e164": "+2348000000101"}, headers=headers).json()["call"]
    assert client.get(f"/api/voice/calls/{call['id']}/context", headers=headers).status_code == 403

    wrong = client.post(f"/api/voice/calls/{call['id']}/verify-pin", json={"phone_e164": "+2348000000101", "pin": "0000"}, headers=headers).json()
    unknown = client.post(f"/api/voice/calls/{call['id']}/verify-pin", json={"phone_e164": "+2348000000999", "pin": "1234"}, headers=headers).json()
    assert wrong["ok"] is False and unknown["ok"] is False and set(wrong) == set(unknown)

    verified = client.post(f"/api/voice/calls/{call['id']}/verify-pin", json={"phone_e164": "+2348000000101", "pin": "1234"}, headers=headers).json()
    assert verified == {"ok": True, "patient_id": "p-zainab"}
    context = client.get(f"/api/voice/calls/{call['id']}/context", headers=headers).json()["context"]
    assert context["patient"]["first_name"] == "Zainab" and context["plan"]["status"] == "approved"

    assert client.post(f"/api/voice/calls/{call['id']}/turns/check", json={"text": "I took it", "language": "ha"}, headers=headers).json() == {"action": "continue"}
    escalated = client.post(f"/api/voice/calls/{call['id']}/turns/check", json={"text": "my chest hurts", "language": "ha"}, headers=headers).json()
    assert escalated["action"] == "escalate" and store().get("escalations", escalated["escalation"]["id"])["call_id"] == call["id"]


# ----- assistant and demo

def test_assistant_drafts_then_applies_only_after_confirming(client, mailbox):
    staff_sign_in(client, mailbox)
    draft = client.post("/api/assistant/drafts", json={"text": "Note that Tola prefers evening calls"}).json()["draft"]
    assert draft["patient"]["id"] == "p-tola" and draft["actions"][0]["kind"] == "note"
    events_before = len(store().where("events", patient_id="p-tola"))

    result = client.post("/api/assistant/apply", json={"patient_id": "p-tola", "actions": draft["actions"]}).json()

    assert result["results"][0]["ok"] is True
    assert len(store().where("events", patient_id="p-tola")) == events_before + 1


def test_scripted_browser_voice_when_livekit_is_not_set_up(client, mailbox):
    patient_sign_in(client, mailbox, "0800 000 0102", "tola.adeyemi@kestrelmail.ng")
    session = client.post("/api/voice/sessions", json={"patient_id": "p-tola"}).json()["session"]
    assert session["mode"] == "mock"

    greeting = client.post(f"/api/voice/sessions/{session['id']}/input", json={}).json()
    assert greeting["pin_required"] is True
    after_pin = client.post(f"/api/voice/sessions/{session['id']}/input", json={"pin": "1234"}).json()
    assert after_pin["turns"][0]["transcript"].startswith("Thank you, Tola.")


# ----- assignment and facility admin

def test_patients_can_be_assigned_to_a_colleague(client, mailbox):
    staff_sign_in(client, mailbox)
    team = client.get("/api/staff").json()["staff"]
    assert [member["name"] for member in team] == ["Dr. Ada Okafor"]
    assert client.get("/api/patients/p-tola").json()["patient"]["assigned_to"]["id"] == "u-ada"

    cleared = client.patch("/api/patients/p-tola/assignment", json={"staff_id": None}).json()["patient"]
    assert cleared["assigned_to"] is None
    assert client.patch("/api/patients/p-tola/assignment", json={"staff_id": "u-nobody"}).status_code == 400


def test_admin_sees_the_join_code_changes_it_and_removes_staff(client, mailbox):
    form = {"name": "Kemi Ade", "email": "kemi.ade@example.com", "password": "quiet-river-lantern-9", "facility_id": "kestrel",
            "role": "Nurse", "confirmed": True, "join_code": "KGH-4821"}
    started = client.post("/api/auth/staff/sign-up", json=form).json()
    kemi = client.post("/api/auth/staff/sign-up/verify", json={"signup_token": started["signup_token"], "code": mailbox.last_code("kemi.ade@example.com")}).json()["session"]
    assert kemi["user"]["is_admin"] is False
    assert client.get("/api/admin/facility").status_code == 403
    client.post("/api/auth/staff/sign-out", json={})

    session = staff_sign_in(client, mailbox)
    assert session["user"]["is_admin"] is True
    page = client.get("/api/admin/facility").json()
    assert page["facility"]["join_code"] == "KGH-4821" and page["staff"][0]["name"] == "Kemi Ade"  # newest first

    new_code = client.post("/api/admin/join-code").json()["join_code"]
    assert new_code.startswith("KGH-") and new_code != "KGH-4821"
    assert client.delete(f"/api/admin/staff/{session['user']['id']}").status_code == 409
    assert client.delete(f"/api/admin/staff/{page['staff'][0]['id']}").json()["ok"] is True
    assert [member["name"] for member in client.get("/api/staff").json()["staff"]] == ["Dr. Ada Okafor"]


def test_join_codes_show_only_for_sample_facilities_when_switched_on(client, monkeypatch):
    from app.db import store
    store().add("facilities", {"id": "real-clinic", "type": "clinic", "name": "A Real Clinic", "city": "Jos", "country": "Nigeria", "join_code": "ARC-1111"})
    monkeypatch.setenv("CARELOOP_SHOW_JOIN_CODES", "1")

    shown = {item["id"]: item.get("demo_join_code") for item in client.get("/api/facilities").json()["facilities"]}

    assert shown["kestrel"] == "KGH-4821" and shown["real-clinic"] is None
    assert all("join_code" not in item for item in client.get("/api/facilities").json()["facilities"])
