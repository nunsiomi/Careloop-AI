"""Synthetic starting data: the same facilities, care team, patients and history as the frontend mock
(frontend/shared/mock-server.js and mock-auth.js), so the app looks the same with ?mock=0. Every person, number
and record is invented. Times are relative to today, in the care facility's time zone.

Loaded once into an empty database, or again by POST /api/demo/reset (only with CARELOOP_DEMO=1).
"""

from datetime import datetime, timedelta

from app.agents import barrier as barrier_agent
from app.security import hash_secret
from app.services import care, notifications, outbox
from app.util import iso, make_id, mask_email, now_iso, parse_iso

FACILITY = "Kestrel General Hospital"
REVIEWER = "Dr. Ada Okafor"
DEMO_PIN = "1234"
FACILITIES = [
    ("kestrel", "hospital", "Kestrel General Hospital", "Abuja", "Nigeria", "KGH-4821"),
    ("egret", "hospital", "Egret Teaching Hospital", "Ibadan", "Nigeria", "ETH-3067"),
    ("hornbill", "hospital", "Hornbill Specialist Hospital", "Kano", "Nigeria", "HSH-5914"),
    ("weaverbird", "hospital", "Weaverbird Medical Centre", "Enugu", "Nigeria", "WMC-2738"),
    ("heron-bay", "hospital", "Heron Bay General Hospital", "Lagos", "Nigeria", "HBG-6409"),
    ("sunbird", "pharmacy", "Sunbird Pharmacy", "Abuja", "Nigeria", "SBP-1956"),
    ("ibis", "clinic", "Ibis Family Clinic", "Accra", "Ghana", "IFC-4173"),
    ("kingfisher", "care_home", "Kingfisher Care Home", "Nairobi", "Kenya", "KCH-8352"),
]


def at(days: int, hhmm: str) -> str:
    hours, minutes = (int(part) for part in hhmm.split(":"))
    local = datetime.now(care.zone()).replace(hour=hours, minute=minutes, second=0, microsecond=0) + timedelta(days=days)
    return iso(local)


def date_only(iso_text: str) -> str:
    return parse_iso(iso_text).astimezone(care.zone()).date().isoformat()


def build() -> dict[str, list[dict]]:
    pin_hash = hash_secret(DEMO_PIN)
    zainab_note = ("Discharge summary: Zainab Musa, Kestrel General Hospital.\nAmlodipine 5 mg tablet, one tablet every morning at 08:00 for 30 days.\n"
                   "Bisoprolol 5 mg tablet, one tablet every evening at 20:00 for 30 days.\nFollow-up at the Heart Clinic, room 3, at 10:00.\n"
                   "Kidney function blood test at the hospital laboratory within 7 days.\nReturn to hospital at once for chest pain, trouble breathing or fainting.")
    ibrahim_note = ("Discharge summary: Ibrahim Danjuma, Kestrel General Hospital.\nAmoxicillin 500 mg capsule, take as directed for 7 days.\n"
                    "Wound check at the Wound Clinic next week.\nReturn to hospital at once for high fever or spreading redness.")
    grace_note = ("Discharge summary: Grace Bassey, Kestrel General Hospital.\nMetformin 500 mg tablet, one tablet twice daily with food at 08:00 and 20:00.\n"
                  "Review at the Diabetes Clinic at 09:30.\nReturn to hospital at once for confusion or fainting.")

    def simple_note(name: str) -> str:
        return (f"Discharge summary: {name}, Kestrel General Hospital.\nAmlodipine 5 mg tablet, one tablet every morning at 09:00 for 14 days.\n"
                "Review visit at Medical Outpatients.\nReturn to hospital at once for chest pain or trouble breathing.")

    base = {"facility": FACILITY, "facility_id": "kestrel", "timezone": "Africa/Lagos", "assigned_to": {"id": "u-ada", "name": REVIEWER}}
    patients = [
        {"id": "p-zainab", "name": "Zainab Musa", "age": 58, "language": "Hausa", "literacy_level": "basic", "caregiver_mode": True,
         "caregiver": {"name": "Hadiza Musa", "relation": "Daughter", "scope": "Reminders and help with tasks"}, "phone_e164": "+2348000000101",
         "email": "zainab.musa@kestrelmail.ng", "channels": ["web", "voice", "email"], "contact_window": "08:00-11:00", "pin_set": True,
         "pin_hash": pin_hash, "consent_at": at(-3, "09:00"), "activation_status": "active", **base},
        {"id": "p-tola", "name": "Tola Adeyemi", "age": 44, "language": "Yoruba", "literacy_level": "standard", "caregiver_mode": False, "caregiver": None,
         "phone_e164": "+2348000000102", "email": "tola.adeyemi@kestrelmail.ng", "channels": ["web", "email", "voice"], "contact_window": "16:00-19:00",
         "pin_set": True, "pin_hash": pin_hash, "consent_at": at(-6, "14:00"), "activation_status": "active", **base},
        {"id": "p-chidi", "name": "Chidi Okeke", "age": 63, "language": "Igbo", "literacy_level": "standard", "caregiver_mode": False, "caregiver": None,
         "phone_e164": "+2348000000103", "email": None, "channels": [], "contact_window": None, "pin_set": False, "pin_hash": None, "consent_at": None,
         "activation_status": "invited", **base},
        {"id": "p-grace", "name": "Grace Bassey", "age": 51, "language": "English", "literacy_level": "standard", "caregiver_mode": False, "caregiver": None,
         "phone_e164": "+2348000000104", "email": "grace.bassey@kestrelmail.ng", "channels": [], "contact_window": None, "pin_set": False, "pin_hash": None,
         "consent_at": None, "activation_status": "plan_review", **base},
        {"id": "p-ibrahim", "name": "Ibrahim Danjuma", "age": 37, "language": "Hausa", "literacy_level": "basic", "caregiver_mode": False, "caregiver": None,
         "phone_e164": "+2348000000105", "email": None, "channels": [], "contact_window": None, "pin_set": False, "pin_hash": None, "consent_at": None,
         "activation_status": "plan_review", **base},
    ]

    def plan(pid, status, note, issues, medications, appointments, tests, symptoms, reminders, approved=None):
        return {"id": f"plan-{pid[2:]}", "patient_id": pid, "status": status, "clinician_approved_at": approved, "approved_by": REVIEWER if approved else None,
                "source_note": note, "verifier_issues": issues, "medications": medications, "appointments": appointments, "tests": tests,
                "symptoms_to_watch": symptoms, "reminder_times": reminders}

    med = lambda name, dose, freq, times, duration, instructions: {"name": name, "dose": dose, "frequency": freq, "times": times, "duration": duration, "instructions": instructions}
    plans = [
        plan("p-zainab", "approved", zainab_note, [], [med("Amlodipine 5 mg tablet", "1 tablet", "Every morning", ["08:00"], "30 days", "Take with water"),
                                                       med("Bisoprolol 5 mg tablet", "1 tablet", "Every evening", ["20:00"], "30 days", "Take with water")],
             [{"what": "Cardiology follow-up", "where": "Heart Clinic, room 3", "date": date_only(at(2, "10:00")), "time": "10:00"}],
             [{"name": "Kidney function blood test", "where": "Hospital laboratory", "date": date_only(at(4, "09:00"))}],
             ["Chest pain", "Trouble breathing", "Fainting"], ["08:00", "20:00"], at(-3, "08:45")),
        plan("p-tola", "approved", simple_note("Tola Adeyemi"), [], [med("Amlodipine 5 mg tablet", "1 tablet", "Every morning", ["09:00"], "14 days", "Take after breakfast")],
             [{"what": "Review visit", "where": "Medical Outpatients", "date": date_only(at(0, "11:30")), "time": "11:30"}], [],
             ["Chest pain", "Trouble breathing"], ["09:00"], at(-6, "11:00")),
        plan("p-chidi", "approved", simple_note("Chidi Okeke"), [], [med("Amlodipine 5 mg tablet", "1 tablet", "Every morning", ["09:00"], "14 days", "Take after breakfast")],
             [{"what": "Review visit", "where": "Medical Outpatients", "date": date_only(at(0, "14:00")), "time": "14:00"}], [],
             ["Chest pain", "Trouble breathing"], ["09:00"], at(-1, "15:00")),
        plan("p-grace", "needs_review", grace_note,
             [{"field": "appointments[0].date", "issue": "Visit date is missing from the note", "severity": "medium", "source_text": "Review at the Diabetes Clinic at 09:30."}],
             [med("Metformin 500 mg tablet", "1 tablet", "Twice daily with food", ["08:00", "20:00"], "", "Take with food")],
             [{"what": "Diabetes review", "where": "Diabetes Clinic", "date": "", "time": "09:30"}], [], ["Confusion", "Fainting"], ["08:00", "20:00"]),
        plan("p-ibrahim", "needs_review", ibrahim_note,
             [{"field": "medications[0].frequency", "issue": "How often to take it is not stated", "severity": "high", "source_text": "take as directed"},
              {"field": "appointments[0].date", "issue": '"Next week" is not an exact date', "severity": "medium", "source_text": "next week"}],
             [med("Amoxicillin 500 mg capsule", "", "", [], "7 days", "")],
             [{"what": "Wound check", "where": "Wound Clinic", "date": "", "time": ""}], [], ["High fever", "Spreading redness"], []),
    ]

    task = lambda tid, pid, kind, title, detail, due, crit, status, reported=None: {
        "id": tid, "patient_id": pid, "type": kind, "title": title, "detail": detail, "due_at": due, "criticality": crit, "status": status, "last_reported_at": reported}
    tasks = [
        task("t-z1", "p-zainab", "medication", "Amlodipine 5 mg tablet", "1 tablet", at(0, "08:00"), "high", "patient_reported_done", at(0, "08:20")),
        task("t-z2", "p-zainab", "medication", "Bisoprolol 5 mg tablet", "1 tablet", at(-1, "20:00"), "high", "unable", at(-1, "09:17")),
        task("t-z3", "p-zainab", "medication", "Bisoprolol 5 mg tablet", "1 tablet", at(0, "20:00"), "high", "pending"),
        task("t-z4", "p-zainab", "test", "Kidney function blood test", "Hospital laboratory", at(4, "09:00"), "medium", "pending"),
        task("t-t1", "p-tola", "medication", "Amlodipine 5 mg tablet", "1 tablet", at(0, "09:00"), "high", "overdue"),
        task("t-c1", "p-chidi", "medication", "Amlodipine 5 mg tablet", "1 tablet", at(0, "09:00"), "high", "pending"),
    ]

    visit = lambda aid, pid, what, where, starts, status: {"id": aid, "patient_id": pid, "what": what, "where": where, "starts_at": starts, "status": status, "created_by": REVIEWER}
    appointments = [
        visit("a-z1", "p-zainab", "Cardiology follow-up", "Heart Clinic, room 3", at(2, "10:00"), "reschedule_requested"),
        visit("a-t1", "p-tola", "Review visit", "Medical Outpatients", at(0, "11:30"), "confirmed"),
        visit("a-c1", "p-chidi", "Review visit", "Medical Outpatients", at(0, "14:00"), "scheduled"),
        visit("a-i1", "p-ibrahim", "Dressing change", "Wound Clinic", at(-1, "10:00"), "scheduled"),
        visit("a-g1", "p-grace", "Diabetes review", "Diabetes Clinic", at(5, "09:30"), "scheduled"),
    ]
    slots = [{"id": f"s-{index}", "where": "Heart Clinic, room 3", "starts_at": at(day, time), "capacity": cap, "reserved_count": taken, "facility_id": "kestrel"}
             for index, (day, time, cap, taken) in enumerate([(3, "10:00", 1, 0), (3, "14:00", 1, 0), (4, "09:30", 1, 1), (6, "11:00", 2, 0)], start=1)]
    requests = [{"id": "rr-1", "appointment_id": "a-z1", "patient_id": "p-zainab", "reason": "Travel cost to the clinic on the booked day",
                 "original_text": "Ba zan iya biyan kuɗin mota ranar ba.", "channel": "voice", "requested_at": at(0, "09:20"), "status": "pending", "reviewer": None}]
    stock_options = barrier_agent.approved_resources(FACILITY).get("stock", [])
    barriers = [
        {"id": "b-z1", "patient_id": "p-zainab", "task_id": "t-z2", "type": "stock", "status": "option_offered", "attempts": 1, "opened_at": at(-1, "09:17"), "options": stock_options},
        {"id": "b-t1", "patient_id": "p-tola", "task_id": "t-t1", "type": "transport", "status": "open", "attempts": 0, "opened_at": at(0, "10:05"), "options": []},
    ]

    def ev(pid, when, actor_type, actor_id, channel, kind, summary, verification):
        return {"id": make_id("ev"), "patient_id": pid, "reported_at": when, "recorded_at": when, "actor_type": actor_type, "actor_id": actor_id,
                "source_channel": channel, "event_type": kind, "summary": summary, "verification_status": verification, "supersedes_event_id": None}
    events = [
        ev("p-zainab", at(-3, "08:30"), "agent", "Care Plan Agent", "system", "plan_drafted", "Plan drafted from discharge note. 1 dose line flagged.", "system_recorded"),
        ev("p-zainab", at(-3, "08:45"), "clinician", REVIEWER, "dashboard", "plan_approved", "Plan corrected and approved.", "clinician_verified"),
        ev("p-zainab", at(-3, "09:00"), "patient", "Zainab Musa", "clinic", "consent_recorded", "Agreed at the clinic to phone calls, email and chat in the app. PIN set.", "clinician_verified"),
        ev("p-zainab", at(-1, "09:15"), "system", "Scheduler", "voice", "call_answered", "Reminder call answered. Identity verified by PIN.", "provider_status"),
        ev("p-zainab", at(-1, "09:17"), "patient", "Zainab Musa", "voice", "task_reported", "Morning medicine reported as taken.", "self_reported"),
        ev("p-zainab", at(-1, "09:17"), "patient", "Zainab Musa", "voice", "barrier_opened", "Could not get the evening medicine.", "self_reported"),
        ev("p-zainab", at(-1, "09:18"), "agent", "Barrier Resolution Agent", "voice", "barrier_option_offered", "Possible pharmacy contact shared. Barrier not resolved.", "system_recorded"),
        ev("p-zainab", at(-1, "09:19"), "provider", "Email provider", "email", "notification_delivered", "Email with a pharmacy contact delivered.", "provider_status"),
        ev("p-zainab", at(0, "08:05"), "provider", "Telephony provider", "voice", "call_unanswered", "Reminder call not answered. Not treated as a missed dose.", "provider_status"),
        ev("p-zainab", at(0, "08:20"), "patient", "Zainab Musa", "web", "task_reported", "Morning medicine reported as taken.", "self_reported"),
        ev("p-zainab", at(0, "09:20"), "patient", "Zainab Musa", "voice", "reschedule_requested", "Asked to move the cardiology visit because of travel cost.", "self_reported"),
        ev("p-zainab", at(0, "09:24"), "system", "Safety engine", "voice", "escalation_created", "Possible emergency phrase. Escalation created and care team notified.", "system_recorded"),
        ev("p-tola", at(-6, "11:00"), "clinician", REVIEWER, "dashboard", "plan_approved", "Plan approved.", "clinician_verified"),
        ev("p-tola", at(-2, "17:10"), "patient", "Tola Adeyemi", "browser_voice", "task_reported", "Morning medicine reported as taken.", "self_reported"),
        ev("p-tola", at(-1, "16:30"), "provider", "Email provider", "email", "notification_delivered", "Medicine reminder email delivered.", "provider_status"),
        ev("p-tola", at(0, "10:05"), "patient", "Tola Adeyemi", "web", "barrier_opened", "Said transport to the clinic is a problem.", "self_reported"),
        ev("p-tola", at(0, "10:30"), "system", "Safety engine", "system", "escalation_created", "Critical medicine task overdue. Escalation created.", "system_recorded"),
        ev("p-chidi", at(-1, "15:00"), "clinician", REVIEWER, "dashboard", "plan_approved", "Plan approved. Invite sent by email.", "clinician_verified"),
        ev("p-grace", at(0, "07:50"), "agent", "Plan Verifier Agent", "system", "plan_drafted", "Plan drafted. 1 field needs review.", "system_recorded"),
        ev("p-ibrahim", at(0, "08:10"), "agent", "Plan Verifier Agent", "system", "plan_drafted", "Plan drafted. 2 fields need review.", "system_recorded"),
    ]

    def turn(speaker, transcript, english=None, confidence=None, confirmed=None, keypad=None):
        return {"speaker": speaker, "transcript": transcript, "english": english, "confidence": confidence, "confirmed": confirmed, "keypad": keypad}
    greeting = "Hello, this is Tomi, an automated assistant from your care team."
    calls = [
        {"id": "c-1", "patient_id": "p-zainab", "direction": "outbound", "channel": "phone", "status": "completed", "verification_state": "verified", "language": "Hausa",
         "started_at": at(-1, "09:15"), "ended_at": at(-1, "09:19"), "outcome": "Task reported, barrier opened", "turns": [
            turn("tomi", f"{greeting} To keep your details private, please enter your PIN."), turn("patient", "PIN entered", keypad=True, confirmed=True),
            turn("tomi", "Thank you, Zainab. Your morning medicine was due at 08:00. Did you take it?"),
            turn("patient", "Na sha na safe, amma ban samu ɗayan maganin ba.", "I took the morning one but could not get the other medicine.", 0.86),
            turn("tomi", "I heard that you took the morning medicine, and you could not get the evening medicine. Is that right?"),
            turn("patient", "Eh.", "Yes.", 0.95, True),
            turn("tomi", "Thank you. Your care team shared a possible pharmacy contact. I will send it by email. Stock is not guaranteed.")]},
        {"id": "c-2", "patient_id": "p-zainab", "direction": "outbound", "channel": "phone", "status": "failed", "verification_state": "not_reached", "language": "Hausa",
         "started_at": at(0, "08:05"), "ended_at": at(0, "08:06"), "outcome": "No answer", "turns": []},
        {"id": "c-3", "patient_id": "p-zainab", "direction": "inbound", "channel": "phone", "status": "completed", "verification_state": "verified", "language": "Hausa",
         "started_at": at(0, "09:18"), "ended_at": at(0, "09:25"), "outcome": "Reschedule requested, escalation created", "turns": [
            turn("tomi", f"{greeting} Please enter your PIN."), turn("patient", "PIN entered", keypad=True, confirmed=True),
            turn("patient", "Ba zan iya biyan kuɗin mota ranar ba.", "I cannot pay for transport on that day.", 0.81),
            turn("tomi", "I can ask the clinic for a new time. Your current visit stays booked until the clinic confirms. Shall I ask?"),
            turn("patient", "Eh.", "Yes.", 0.94, True),
            turn("patient", "Ƙirjina yana ciwo, kuma numfashi yana min wuya.", "My chest hurts and it is hard to breathe.", 0.71),
            turn("tomi", care.EMERGENCY_LINE)]},
        {"id": "c-4", "patient_id": "p-tola", "direction": "browser", "channel": "browser_voice", "status": "completed", "verification_state": "verified", "language": "Yoruba",
         "started_at": at(-2, "17:08"), "ended_at": at(-2, "17:11"), "outcome": "Task reported", "turns": [
            turn("tomi", "Hello Tola, this is Tomi. Did you take your morning medicine today?"),
            turn("patient", "Bẹ́ẹ̀ni, mo ti lò ó.", "Yes, I have taken it.", 0.9), turn("tomi", "I heard that you took it. Is that right?"),
            turn("patient", "Bẹ́ẹ̀ni.", "Yes.", 0.96, True), turn("tomi", "Thank you. I have noted it.")]},
    ]

    history = lambda entries: [{"status": status, "at": when, "by": by} for status, when, by in entries]
    escalations = [
        {"id": "e-1", "patient_id": "p-zainab", "rule_id": "possible_chest_pain", "rule_label": "Possible emergency phrase", "severity": "red", "status": "delivered",
         "channel": "voice", "call_id": "c-3", "original_text": "Ƙirjina yana ciwo, kuma numfashi yana min wuya.", "english_text": "My chest hurts and it is hard to breathe.",
         "confidence": 0.71, "brief_ready": True, "outstanding": "Evening medicine barrier open. Appointment move pending.", "created_at": at(0, "09:24"), "note": None,
         "brief": ("During an inbound call at 09:24 the patient said, in Hausa, that her chest hurts and breathing is hard (speech confidence 0.71). Approved emergency "
                   "guidance was given. Open items: evening medicine not obtained since yesterday (barrier open); appointment move requested for travel cost."),
         "history": history([("created", at(0, "09:24"), None), ("notification_attempted", at(0, "09:24"), None), ("delivered", at(0, "09:25"), None)])},
        {"id": "e-2", "patient_id": "p-tola", "rule_id": "missed_critical_task", "rule_label": "Critical medicine overdue", "severity": "amber", "status": "acknowledged",
         "channel": "system", "call_id": None, "original_text": "Ọkọ̀ ò rọrùn láti rí.", "english_text": "Transport is hard to find.", "confidence": 0.88,
         "brief": "Morning medicine due 09:00 has no report. Patient reported a transport problem at 10:05 in web chat.", "brief_ready": True,
         "outstanding": "Morning medicine not reported.", "created_at": at(0, "10:30"), "note": None,
         "history": history([("created", at(0, "10:30"), None), ("notification_attempted", at(0, "10:30"), None), ("delivered", at(0, "10:31"), None), ("acknowledged", at(0, "10:40"), REVIEWER)])},
        {"id": "e-3", "patient_id": "p-chidi", "rule_id": "barrier_unresolved", "rule_label": "Barrier not resolved after 2 attempts", "severity": "amber", "status": "resolved",
         "channel": "web", "call_id": None, "original_text": "Enweghị m ego ịzụta ọgwụ.", "english_text": "I do not have money to buy the medicine.", "confidence": 0.9,
         "brief": "Patient reported cost barrier twice. Two support options offered; neither confirmed.", "brief_ready": True, "outstanding": "None.", "created_at": at(-4, "12:00"),
         "note": "Hospital social worker arranged help with the cost of medicine.",
         "history": history([("created", at(-4, "12:00"), None), ("delivered", at(-4, "12:01"), None), ("acknowledged", at(-4, "12:30"), REVIEWER), ("resolved", at(-4, "15:00"), REVIEWER)])},
    ]
    messages = [
        {"id": "m-1", "patient_id": "p-zainab", "direction": "careloop", "channel": "web", "original_text": "Good morning, Zainab. It is time for your morning medicine: Amlodipine 5 mg tablet, 1 tablet.",
         "language": "Hausa", "created_at": at(0, "08:00"), "task_id": "t-z1", "number_check_passed": True, "answered": True},
        {"id": "m-2", "patient_id": "p-zainab", "direction": "patient", "channel": "web", "original_text": "Done", "language": "Hausa", "created_at": at(0, "08:20")},
        {"id": "m-3", "patient_id": "p-zainab", "direction": "careloop", "channel": "web", "original_text": "Thank you. I have noted that you took it.", "language": "Hausa",
         "created_at": at(0, "08:20"), "number_check_passed": True},
    ]

    data = {
        "facilities": [{"id": fid, "type": kind, "name": name, "city": city, "country": country, "join_code": code} for fid, kind, name, city, country, code in FACILITIES],
        "staff": [{"id": "u-ada", "name": REVIEWER, "email": "ada.okafor@kestrelgeneral.ng", "password_hash": hash_secret("Blue-ward-morning-24"),
                   "role": "Clinician reviewer", "facility": FACILITY, "facility_id": "kestrel", "failures": 0, "locked_until": None,
                   "is_admin": True, "created_at": at(-30, "09:00")}],
        "staff_invites": [{"id": "join-7f3k", "token": "join-7f3k", "name": "Bisi Ola", "email": "bisi.ola@kestrelgeneral.ng", "role": "Follow-up nurse",
                           "facility": FACILITY, "invited_by": REVIEWER, "status": "pending"}],
        "invites": [
            {"id": "CL-7K4Q", "code": "CL-7K4Q", "kind": "patient", "patient_id": "p-chidi", "facility": FACILITY, "invited_by": REVIEWER, "status": "pending"},
            {"id": "CG-3M9D", "code": "CG-3M9D", "kind": "caregiver", "patient_id": "p-tola", "name": "Femi Adeyemi", "relation": "Son", "facility": FACILITY,
             "invited_by": "Tola Adeyemi", "status": "pending"},
        ],
        "caregivers": [{"id": "cg-1", "patient_id": "p-zainab", "name": "Hadiza Musa", "relation": "Daughter", "phone_e164": "+2348000000201",
                        "email": "hadiza.musa@kestrelmail.ng", "scope": "Reminders and help with tasks", "added_at": at(-3, "09:00"), "pin_hash": pin_hash}],
        "patients": patients, "plans": plans, "tasks": tasks, "appointments": appointments, "clinic_slots": slots, "reschedule_requests": requests,
        "barriers": barriers, "events": events, "calls": calls, "escalations": escalations, "messages": messages, "notifications": [],
    }
    _keep_history_in_the_past(data)
    _sent_messages(data)
    return data


def _sent_messages(data: dict) -> None:
    """Messages already sent, with provider outcomes. The scheduler adds the upcoming ones once the store is open."""
    zainab, tola = data["patients"][0], data["patients"][1]
    tasks = {item["id"]: item for item in data["tasks"]}
    delivered_event = next(event for event in data["events"] if event["event_type"] == "notification_delivered")
    missed = next(call for call in data["calls"] if call["id"] == "c-2")
    tola_event = next(event for event in data["events"] if event["actor_id"] == "Email provider" and event["patient_id"] == "p-tola")

    def sent(patient, template, scheduled_for, status="delivered", task_id=None, created_by="Reminder scheduler", failure=None, delivered_after=1):
        subject, body = notifications.render(template, patient, "email")
        sent_time = parse_iso(scheduled_for)
        data["notifications"].append({
            "id": make_id("n"), "patient_id": patient["id"], "channel": "email", "template": template, "title": notifications.TEMPLATES[template][0],
            "subject": subject, "body": body, "to": mask_email(patient["email"]), "status": status, "scheduled_for": scheduled_for, "sent_at": scheduled_for,
            "delivered_at": iso(sent_time + timedelta(minutes=delivered_after)) if status == "delivered" else None, "failure_reason": failure,
            "task_id": task_id, "appointment_id": None, "created_by": created_by})

    before = lambda iso_text, minutes: iso(parse_iso(iso_text) - timedelta(minutes=minutes))
    sent(zainab, "medicine", before(tasks["t-z2"]["due_at"], 30), "failed", "t-z2", failure="Not delivered. The mailbox was full. Check the address with the patient.")
    sent(zainab, "support", delivered_event["reported_at"], created_by="Barrier Resolution Agent")
    sent(zainab, "missed_call", before(missed["ended_at"], -2))
    sent(zainab, "medicine", before(tasks["t-z1"]["due_at"], 30), task_id="t-z1")
    sent(tola, "medicine", tola_event["reported_at"], delivered_after=2)


def _keep_history_in_the_past(data: dict) -> None:
    """Seed times are clock times ("today at 09:24"); early in the morning some are still ahead. Move those back a day."""
    stamp = now_iso()
    day = timedelta(days=1)
    back = lambda value: iso(parse_iso(value) - day) if value and value > stamp else value
    for event in data["events"]:
        event["reported_at"] = event["recorded_at"] = back(event["reported_at"])
    for collection, key in (("messages", "created_at"), ("barriers", "opened_at"), ("reschedule_requests", "requested_at"),
                            ("plans", "clinician_approved_at"), ("patients", "consent_at")):
        for item in data[collection]:
            item[key] = back(item.get(key))
    for call in data["calls"]:
        if call["started_at"] > stamp:
            call["started_at"] = back(call["started_at"])
            call["ended_at"] = call["ended_at"] and iso(parse_iso(call["ended_at"]) - day)
    for escalation in data["escalations"]:
        if escalation["created_at"] > stamp:
            escalation["created_at"] = back(escalation["created_at"])
            for entry in escalation["history"]:
                entry["at"] = iso(parse_iso(entry["at"]) - day)
    for item in data["tasks"]:
        if item["status"] != "pending" and item["due_at"] > stamp:
            item["due_at"] = back(item["due_at"])
            item["last_reported_at"] = back(item["last_reported_at"])


def load_into(db) -> None:
    db.replace_all(build())
    for patient in db.all("patients"):
        outbox.schedule_reminders(patient)
