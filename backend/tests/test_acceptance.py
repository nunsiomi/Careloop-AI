# backend/tests/test_acceptance.py
# Section 17 of the project documentation, "Evaluation and Acceptance Tests", one block per row of its table.
# Rows already covered elsewhere: care plan integrity (test_plan_verifier.py, test_care_plan.py), the red-flag phrase
# lists (test_safety.py) and PIN verification (test_api.py). The parts that need people (native speakers, provider
# tests) are tracked in docs/acceptance-tests.md.
import asyncio
import json
import re
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest

from app.adapters import SendResult
from app.db import store
from app.safety import rules
from app.services import care, escalations, notifications, outbox
from app.util import iso, now
from tests.test_api import patient_sign_in, staff_sign_in

ROOT = Path(__file__).resolve().parents[2]
WORKER = {"Authorization": "Bearer test-worker-token"}
ADA_EMAIL = "ada.okafor@kestrelgeneral.ng"


def verified_call(client, phone="+2348000000102") -> str:
    call = client.post("/api/voice/calls", json={"direction": "inbound", "phone_e164": phone}, headers=WORKER).json()["call"]
    assert client.post(f"/api/voice/calls/{call['id']}/verify-pin", json={"phone_e164": phone, "pin": "1234"}, headers=WORKER).json()["ok"]
    return call["id"]


def future_task(task_id="t-acc", patient_id="p-tola", hours=6) -> dict:
    return store().add("tasks", {"id": task_id, "patient_id": patient_id, "type": "medication", "title": "Amlodipine 5 mg tablet", "detail": "1 tablet",
                                 "due_at": iso(now() + timedelta(hours=hours)), "criticality": "high", "status": "pending", "last_reported_at": None})


# ----- Voice languages: the automated half. Native speakers still judge accents, noise and wording (docs/acceptance-tests.md).

@pytest.mark.parametrize("language, code, danger", [
    ("Hausa", "ha", "Ƙirjina yana ciwo"), ("Yoruba", "yo", "Àyà mi ń dùn"), ("Igbo", "ig", "enweghi m ike iku ume"), ("English", "en", "my chest hurts"),
])
def test_each_language_reaches_the_emergency_path_on_a_call(client, language, code, danger):
    store().get("patients", "p-tola")["language"] = language
    call_id = verified_call(client)

    result = client.post(f"/api/voice/calls/{call_id}/turns/check", json={"text": danger, "language": code}, headers=WORKER).json()

    assert result["action"] == "escalate"
    emergency = care.emergency_in(language)
    assert emergency["language"] == language and emergency["text"].endswith(care.EMERGENCY_LINE)


def test_every_rule_has_phrases_in_each_language_except_the_recorded_gaps():
    gaps = {(rule["id"], code) for rule in rules.load()["rules"] for code in ("en", "ha", "yo", "ig") if not rule["terms"].get(code)}
    # Recorded, not hidden: no Igbo phrase for a seizure yet. Native speakers are asked for one (docs/acceptance-tests.md).
    assert gaps == {("possible_seizure", "ig")}


# ----- Red flags: indirect phrasings and the human-safe path for uncertain speech

@pytest.mark.parametrize("text, rule_id", [
    ("it feels like something heavy is sitting on my chest", "possible_chest_pain"),
    ("I keep gasping for air", "possible_breathing_problem"),
    ("my mother collapsed and she is not responding", "possible_fainting"),
    ("there is blood in my vomit", "possible_heavy_bleeding"),
    ("his arm is weak on one side", "possible_stroke"),
    ("he is shaking all over", "possible_seizure"),
    ("my lips are swelling", "possible_allergic_reaction"),
    ("I feel like giving up on life", "possible_self_harm"),
])
def test_indirect_phrasings_escalate(text, rule_id):
    assert (rules.check(text).action, rules.check(text).rule_id) == ("escalate", rule_id)


def test_uncertain_dangerous_speech_on_a_call_goes_to_a_person(client):
    call_id = verified_call(client)
    check = lambda text, confidence: client.post(f"/api/voice/calls/{call_id}/turns/check", json={"text": text, "language": "en", "confidence": confidence}, headers=WORKER).json()

    assert check("mm ... ba ...", 0.3) == {"action": "clarify"}
    assert check("mm ... breathing ... ba", 0.9) == {"action": "continue"}     # clear speech: no danger phrase
    unclear_danger = check("mm ... breathing ... ba", 0.35)                  # unclear speech with a danger word
    assert unclear_danger["action"] == "escalate"
    assert store().get("escalations", unclear_danger["escalation"]["id"])["rule_id"] == "possible_red_flag_low_confidence"


# ----- Event provenance: who reported it, and corrections append

def test_every_event_says_who_reported_it_and_how_it_was_verified(client, mailbox):
    future_task()
    call_id = verified_call(client)
    client.post(f"/api/voice/calls/{call_id}/task-updates", json={"task_id": "t-acc", "status": "done"}, headers=WORKER)
    staff_sign_in(client, mailbox)
    client.post("/api/appointments/a-t1/attendance", json={"status": "attended"})

    events = client.get("/api/patients/p-tola/events").json()["events"]
    allowed = {"self_reported", "clinician_verified", "provider_status", "system_recorded"}
    assert all(event["verification_status"] in allowed and event["actor_type"] and event["source_channel"] for event in events)
    by_type = {event["event_type"]: event for event in events}
    assert (by_type["task_reported"]["actor_type"], by_type["task_reported"]["verification_status"]) == ("patient", "self_reported")
    assert (by_type["attendance_recorded"]["actor_type"], by_type["attendance_recorded"]["verification_status"]) == ("clinician", "clinician_verified")


def test_a_correction_is_a_new_event_that_points_at_the_old_one(client):
    future_task()
    call_id = verified_call(client)
    client.post(f"/api/voice/calls/{call_id}/task-updates", json={"task_id": "t-acc", "status": "done"}, headers=WORKER)
    first = dict(store().first("events", event_type="task_reported", target_id="t-acc"))

    client.post(f"/api/voice/calls/{call_id}/task-updates", json={"task_id": "t-acc", "status": "not_done"}, headers=WORKER)

    reports = sorted(store().where("events", event_type="task_reported", target_id="t-acc"), key=lambda item: item["recorded_at"])
    assert len(reports) == 2
    assert reports[0] == first                                   # the first report is never edited
    assert reports[1]["supersedes_event_id"] == first["id"] and reports[1]["summary"].endswith("not yet done.")


# ----- Appointment integrity

def test_a_reschedule_stays_pending_until_a_clinician_approves(client, mailbox):
    patient_sign_in(client, mailbox, "0800 000 0102", "tola.adeyemi@kestrelmail.ng")
    before = dict(store().get("appointments", "a-t1"))

    client.post("/api/appointments/a-t1/reschedule-requests", json={"reason": "No transport that day"})

    after = store().get("appointments", "a-t1")
    assert after["status"] == "reschedule_requested" and after["starts_at"] == before["starts_at"]
    assert not store().first("appointments", replaces="a-t1")


def test_a_full_slot_is_refused_and_the_old_reminder_is_kept(client, mailbox):
    zainab = store().get("patients", "p-zainab")
    reminder = outbox.queue_message(zainab, channel="email", template="visit", appointment_id="a-z1", scheduled_for=iso(now() + timedelta(days=1)))
    staff_sign_in(client, mailbox)

    full = client.post("/api/reschedule-requests/rr-1/decision", json={"decision": "approve", "slot_id": "s-3"})   # capacity 1, already taken

    assert full.status_code == 409
    assert store().get("appointments", "a-z1")["status"] == "reschedule_requested" and reminder["status"] == "scheduled"
    assert store().get("clinic_slots", "s-3")["reserved_count"] == 1


def test_an_approved_move_reserves_once_then_cancels_the_old_reminder(client, mailbox):
    zainab = store().get("patients", "p-zainab")
    reminder = outbox.queue_message(zainab, channel="email", template="visit", appointment_id="a-z1", scheduled_for=iso(now() + timedelta(days=1)))
    staff_sign_in(client, mailbox)

    moved = client.post("/api/reschedule-requests/rr-1/decision", json={"decision": "approve", "slot_id": "s-1"})
    again = client.post("/api/reschedule-requests/rr-1/decision", json={"decision": "approve", "slot_id": "s-1"})

    assert moved.status_code == 200 and again.status_code == 409
    assert store().get("clinic_slots", "s-1")["reserved_count"] == 1
    assert store().get("appointments", "a-z1")["status"] == "cancelled" and reminder["status"] == "cancelled"
    replacement = store().first("appointments", replaces="a-z1")
    assert replacement["status"] == "rescheduled"
    assert store().first("notifications", appointment_id=replacement["id"], template="visit_moved")


# ----- Reminder reliability: timeouts, retries and repeated runs never double-send

def test_a_provider_timeout_is_retried_and_sends_once(client, mailbox, monkeypatch):
    attempts = []

    async def flaky(to, subject, text):
        attempts.append(to)
        return SendResult(ok=False, error="timed out", retryable=True) if len(attempts) == 1 else SendResult(ok=True, provider_id="<ok@test>")

    monkeypatch.setattr(notifications, "send_email", flaky)
    monkeypatch.setattr(notifications, "RETRY_WAITS", (0, 0))
    message = outbox.queue_message(store().get("patients", "p-tola"), channel="email", template="medicine", scheduled_for="2020-01-01T00:00:00.000Z")

    asyncio.run(outbox.send_due())
    asyncio.run(outbox.send_due())                              # a second scheduler run picks nothing up

    assert len(attempts) == 2 and message["status"] == "sent" and message["provider_id"] == "<ok@test>"
    assert len(store().where("events", event_type="notification_sent", patient_id="p-tola")) == 1


def test_rescheduling_reminders_again_queues_no_duplicates(client):
    future_task()
    tola = store().get("patients", "p-tola")
    outbox.schedule_reminders(tola)
    count = len(store().where("notifications", task_id="t-acc"))
    outbox.schedule_reminders(tola)
    outbox.schedule_reminders(tola)

    assert count == 1 and len(store().where("notifications", task_id="t-acc")) == 1


def test_a_failed_message_can_be_sent_again_only_once(client, mailbox):
    failed = outbox.queue_message(store().get("patients", "p-tola"), channel="email", template="medicine", status="failed")
    staff_sign_in(client, mailbox)

    first = client.post(f"/api/notifications/{failed['id']}/retry")
    second = client.post(f"/api/notifications/{failed['id']}/retry")

    assert first.status_code == 200 and second.status_code == 409
    assert len(store().where("notifications", retry_of=failed["id"])) == 1
    assert client.post(f"/api/notifications/{first.json()['notification']['id']}/retry").status_code == 409   # not failed


# ----- Escalation delivery: not acknowledged until a person acts; backup contact

def test_escalation_is_delivered_then_backed_up_until_someone_acknowledges(client, mailbox):
    patient_sign_in(client, mailbox, "0800 000 0102", "tola.adeyemi@kestrelmail.ng")
    escalation_id = client.post("/api/patients/p-tola/messages", json={"original_text": "I cannot breathe", "language": "English"}).json()["escalation"]["id"]
    escalation = store().get("escalations", escalation_id)

    assert escalation["status"] == "delivered"                  # emailed, but nobody has looked yet
    alert = next(mail for mail in mailbox.sent if mail["to"] == ADA_EMAIL and mail["subject"] == "A CareLoop escalation needs review")
    assert "Tola" not in alert["text"] and "breathe" not in alert["text"]

    escalation["alert_sent_at"] = iso(now() - timedelta(minutes=16))
    asyncio.run(escalations.send_alerts())
    assert escalation["status"] == "delivered" and escalation["backup_sent_at"]
    assert any(mail["subject"].startswith("Reminder: a CareLoop escalation") for mail in mailbox.sent)

    client.post("/api/auth/patient/sign-out")
    staff_sign_in(client, mailbox)
    acknowledged = client.post(f"/api/escalations/{escalation_id}/acknowledge").json()["escalation"]
    assert acknowledged["status"] == "acknowledged" and acknowledged["history"][-1]["by"] == "Dr. Ada Okafor"

    sent = len(mailbox.sent)
    escalation["backup_sent_at"] = None
    asyncio.run(escalations.send_alerts())
    assert len(mailbox.sent) == sent                            # acknowledged: no more chasing

    client.post(f"/api/escalations/{escalation_id}/resolve", json={"note": "Called the patient; went to the emergency unit."})
    assert client.post(f"/api/escalations/{escalation_id}/acknowledge").json()["escalation"]["status"] == "resolved"


# ----- Channel fallback

def test_when_phone_calls_are_not_set_up_the_dashboard_says_so_and_chat_still_works(client, mailbox, monkeypatch):
    monkeypatch.setenv("CARELOOP_DEMO", "0")
    staff_sign_in(client, mailbox)
    refused = client.post("/api/calls/outbound", json={"patient_id": "p-tola"})
    assert refused.status_code == 503 and refused.json()["detail"] == "Phone calls are not set up yet."
    assert not store().first("calls", lambda item: item["status"] == "initiated", patient_id="p-tola")

    client.post("/api/auth/staff/sign-out", json={})
    patient_sign_in(client, mailbox, "0800 000 0102", "tola.adeyemi@kestrelmail.ng")
    assert client.post("/api/patients/p-tola/messages", json={"original_text": "I took my morning tablet", "language": "English"}).status_code == 200


def test_a_refused_email_is_logged_and_shown_to_the_care_team(client, mailbox, monkeypatch):
    async def refused(to, subject, text):
        return SendResult(ok=False, error="The mailbox does not exist.")

    monkeypatch.setattr(notifications, "send_email", refused)
    message = outbox.queue_message(store().get("patients", "p-tola"), channel="email", template="medicine", scheduled_for="2020-01-01T00:00:00.000Z")
    asyncio.run(outbox.send_due())

    assert message["status"] == "failed" and message["failure_reason"] == "Not delivered. The mailbox does not exist."
    assert store().first("events", event_type="notification_failed", patient_id="p-tola")
    staff_sign_in(client, mailbox)
    problems = client.get("/api/notifications", params={"status": "problem"}).json()["notifications"]
    assert message["id"] in {item["id"] for item in problems}
    assert client.get("/api/patients/p-tola").json()["patient"]["failed_messages"] >= 1


# ----- Security

def test_patient_and_caregiver_sessions_cannot_reach_care_team_routes(client, mailbox):
    patient_sign_in(client, mailbox, "0800 000 0102", "tola.adeyemi@kestrelmail.ng")
    for method, path in [("get", "/api/escalations"), ("get", "/api/events"), ("get", "/api/admin/facility"), ("get", "/api/staff"),
                         ("post", "/api/assistant/drafts"), ("post", "/api/notifications"), ("post", "/api/escalations/e-1/acknowledge")]:
        assert getattr(client, method)(path).status_code in (401, 403), path
    assert client.get("/api/patients/p-zainab/events").status_code == 404


def test_worker_routes_refuse_a_wrong_service_token(client):
    assert client.post("/api/voice/calls", json={"direction": "inbound"}, headers={"Authorization": "Bearer guess"}).status_code == 401


def _tracked_files() -> list[Path]:
    try:
        names = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git is not available")
    return [ROOT / name for name in names]


def test_no_secrets_or_databases_in_the_repo():
    files = _tracked_files()
    assert not [path.name for path in files if path.name == ".env" or path.suffix in (".db", ".sqlite", ".pem", ".key")]
    secret = re.compile(r"gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[bp]-[A-Za-z0-9-]{20,}")
    leaks = [str(path.relative_to(ROOT)) for path in files
             if path.is_file() and path.suffix not in (".docx", ".png", ".jpg", ".ico", ".woff2") and secret.search(path.read_text(encoding="utf-8", errors="ignore"))]
    assert leaks == []


def test_sample_patients_use_reserved_numbers_and_sample_mail_domains(client):
    for patient in store().all("patients"):
        assert re.fullmatch(r"\+2348000000\d{3}", patient["phone_e164"]), patient["name"]
        assert patient["email"] is None or patient["email"].split("@")[1] in ("kestrelmail.ng", "example.com"), patient["name"]
    synthetic = json.loads((ROOT / "data" / "synthetic_patients.json").read_text(encoding="utf-8"))
    phones = re.findall(r"\+?234\s?\d[\d\s]{8,}", json.dumps(synthetic))
    assert all(re.sub(r"\D", "", phone).startswith("2348000000") for phone in phones)
