# CareLoop frontend API contract

**Status: PROPOSED. Olamide owns the final routes and Pydantic models; change this file when they change.**
Routes follow section 11 of the project documentation v2. Routes marked *(added)* are not in section 11 but the UI needs them.

## How the frontend calls the API

- Every call goes through `frontend/shared/api.js`, which exports `CareLoopAPI` and `USE_MOCKS`.
- `USE_MOCKS` is on by default. Add `?mock=0` to a page URL to call FastAPI instead.
- With mocks on, `frontend/shared/mock-server.js` answers in the browser and saves state in local storage. The demo controls can reset it.
- Real calls go to `/api/...`. In development, Vite proxies `/api` to `http://127.0.0.1:8000`.
- On an error, the frontend reads `detail` (FastAPI's default) or `message` and shows it as written. Please make these messages readable by a clinician or patient.
- Times are ISO-8601 UTC strings. The UI displays them in local time (Africa/Lagos).

## Shared shapes

### Patient

`GET` responses add the summary fields after `activation_status`.

```json
{
  "id": "p-zainab", "name": "Zainab Musa", "age": 58,
  "language": "Hausa", "literacy_level": "basic | standard | caregiver", "caregiver_mode": true,
  "caregiver": { "name": "string", "relation": "string", "scope": "string" },
  "phone_e164": "+2348000000101", "email": "string or null",
  "channels": ["web", "voice", "sms", "email"], "contact_window": "08:00-11:00", "pin_set": true,
  "consent_at": "ISO or null", "activation_status": "plan_review | invited | active",
  "assigned_to": { "id": "u-ada", "name": "Dr. Ada Okafor" } or null,  (added: the lead clinician)

  "plan_status": "needs_review | approved | not_created",
  "open_tasks": 2, "overdue_critical": 0, "open_barriers": 1, "open_escalations": 1,
  "last_contact": { "at": "ISO", "channel": "voice", "summary": "string" }
}
```

`language` is one of `Hausa`, `Yoruba`, `Igbo` or `English`. Pidgin is removed from the MVP.

### Plan

```json
{
  "id": "plan-zainab", "patient_id": "p-zainab", "status": "needs_review | approved",
  "source_note": "string", "clinician_approved_at": "ISO or null", "approved_by": "string or null",
  "verifier_issues": [{ "field": "medications[0].frequency", "issue": "string", "severity": "high | medium", "source_text": "exact substring of source_note" }],
  "medications": [{ "name": "", "dose": "", "frequency": "", "times": ["08:00"], "duration": "", "instructions": "" }],
  "appointments": [{ "what": "", "where": "", "date": "YYYY-MM-DD or empty", "time": "HH:MM or empty" }],
  "tests": [{ "name": "", "where": "", "date": "YYYY-MM-DD" }],
  "symptoms_to_watch": ["string"], "reminder_times": ["HH:MM"]
}
```

The UI highlights `verifier_issues[].source_text` inside `source_note`, so it must be an exact substring.

Where a plan comes from (backend only; Pydantic models in `backend/app/models.py`): the Care Plan Agent
(`agents/care_plan.py`) takes `{ source_note, patient: { name } }` and returns
`{ plan, unresolved: [issue], deliverable, error? }`; the Plan Verifier (`agents/plan_verifier.py`) takes
`{ source_note, plan, patient }` and returns `{ verdict: "clean | flagged", issues: [issue], deliverable, model_checked }`.
The orchestrator stores the verifier's `issues` as `verifier_issues`, and must not send the plan to the patient
while `deliverable` is false or before a clinician approves it. Severity rules: `docs/plan-review-criteria.md`.

### Task

```json
{ "id": "t-z3", "patient_id": "p-zainab", "type": "medication | test | appointment", "title": "string", "detail": "string",
  "due_at": "ISO", "criticality": "high | medium", "status": "pending | patient_reported_done | clinician_verified | unable | overdue | cancelled",
  "last_reported_at": "ISO or null" }
```

### Appointment, clinic slot and reschedule request

```json
{ "id": "a-z1", "patient_id": "p-zainab", "what": "string", "where": "string", "starts_at": "ISO",
  "status": "requested | scheduled | confirmed | reschedule_requested | rescheduled | attended | no_show | cancelled",
  "created_by": "string", "replaces": "appointment id or absent" }

{ "id": "s-1", "where": "string", "starts_at": "ISO", "capacity": 1, "reserved_count": 0 }

{ "id": "rr-1", "appointment_id": "a-z1", "patient_id": "p-zainab", "reason": "string", "original_text": "patient's words",
  "channel": "voice | web", "requested_at": "ISO", "status": "pending | approved | rejected", "reviewer": "string or null",
  "appointment": "Appointment (in list responses)" }
```

### Care event (timeline)

```json
{ "id": "ev-1", "patient_id": "p-zainab", "reported_at": "ISO", "recorded_at": "ISO",
  "actor_type": "patient | caregiver | clinician | agent | system | provider", "actor_id": "Zainab Musa | Care Plan Agent | Telephony provider",
  "source_channel": "voice | browser_voice | web | sms | email | dashboard | clinic | system",
  "event_type": "task_reported | barrier_opened | call_answered | plan_approved | ...", "summary": "string",
  "verification_status": "self_reported | clinician_verified | system_recorded | provider_status",
  "supersedes_event_id": "string or null" }
```

`verification_status` drives the timeline marker, so a patient report never looks clinician-verified. Feed list responses also include `patient_name` and `patient_language`.

### Barrier

```json
{ "id": "b-z1", "patient_id": "p-zainab", "task_id": "t-z2", "type": "cost | transport | stock | understanding",
  "status": "open | option_offered | awaiting_response | resolved_patient_reported | resolved_verified | escalated",
  "attempts": 1, "opened_at": "ISO",
  "options": [{ "name": "string", "type": "string", "distance": "string", "phone": "+234...", "note": "string" }] }
```

### Call session

```json
{ "id": "c-1", "patient_id": "p-zainab", "direction": "outbound | inbound | browser", "channel": "phone | browser_voice",
  "status": "initiated | ringing | answered | verified | unverified | disconnected | completed | failed",
  "verification_state": "pending | verified | unverified | not_reached", "language": "Hausa",
  "started_at": "ISO", "ended_at": "ISO or null", "outcome": "string or null",
  "turns": [{ "speaker": "tomi | patient", "transcript": "original language", "english": "string or null",
              "confidence": 0.86, "confirmed": true, "keypad": false }] }
```

No raw audio. `turns` holds text only.

### Escalation

```json
{ "id": "e-1", "patient_id": "p-zainab", "rule_id": "possible_chest_pain", "rule_label": "string", "severity": "red | amber",
  "status": "created | notification_attempted | delivered | acknowledged | acted_on | resolved", "channel": "voice", "call_id": "c-3 or null",
  "original_text": "string", "english_text": "string", "confidence": 0.71,
  "brief": "string or null", "brief_ready": true, "outstanding": "string", "created_at": "ISO",
  "history": [{ "status": "delivered", "at": "ISO", "by": "string or null" }], "note": "string or null" }
```

While `brief_ready` is false, the UI polls every 3 s and shows "Escalation Summary Agent is writing the brief".

`Patient` list and detail responses also carry `"task_counts": { "done": 1, "due": 1, "missed": 1 }` *(added)*, which draws the patient loop on the dashboard.

Patient responses also carry `"failed_messages": 0` and `"next_message": { "channel": "sms", "scheduled_for": "ISO", "title": "Medicine reminder" } or null` *(added)*.

## Email (and later SMS) reminders *(doc v2, section 8; routes added)*

Email is the live channel until CareLoop has an SMS provider (Nunsi, 3 Nov 2026). `sms` stays in every shape so it can return without changes; the backend only uses it once `adapters/sms.py` is set up, and the app hides it while `SMS_AVAILABLE` is false. Backend rules and templates: `backend/app/services/notifications.py`.

Rules the backend scheduler follows, and the UI assumes:
- Only on channels the patient agreed to (`patient.channels`). Re-check consent at send time; if it was withdrawn, cancel instead of sending.
- One message 30 minutes before each pending task and one at 18:00 the evening before each visit. Nothing between 21:00 and 07:00; move it to 07:00.
- Bodies are fixed templates that never name a medicine, condition or test. Replies are not read, so every message ends "Do not reply." Emails add a link to the app.
- Cancel a scheduled reminder when the patient reports the task done, when a visit is moved (then send `visit_moved`), or when the channel is turned off.
- A delivered text is not proof the patient did anything. Delivery status comes from the provider webhook.

```json
Notification: { "id": "n-1", "patient_id": "p-zainab", "channel": "sms | email", "template": "medicine | test | visit | visit_moved | support | missed_call | call_clinic",
  "title": "Medicine reminder", "subject": "email only, or null", "body": "exact text sent", "to": "+234 ••• ••• 0101",
  "status": "scheduled | sent | delivered | failed | cancelled", "scheduled_for": "ISO", "sent_at": "ISO or null", "delivered_at": "ISO or null",
  "failure_reason": "readable text or null", "task_id": "string or null", "appointment_id": "string or null", "created_by": "Reminder scheduler | clinician name | agent name",
  "retry_of": "id or absent", "retried": false }
```

| `CareLoopAPI` method | HTTP | Request body | Response |
|---|---|---|---|
| `listNotifications(filters)` | `GET /notifications?patient_id=&status=` | `status`: `upcoming`, `sent`, `problem` (failed) or `cancelled` | `{ notifications[] }` with `patient_name` |
| `listMessageTemplates({ patient_id })` | `GET /patients/{id}/message-templates` | | `{ templates: [{ id, title, body }] }` (bodies with the patient's first name filled in) |
| `sendPatientMessage(body)` | `POST /notifications` | `{ patient_id, channel, template, by }` | `{ notification }`; 403 without consent |
| `cancelNotification(id, body)` | `POST /notifications/{id}/cancel` | `{ by }` | `{ notification }`; 409 if already sent |
| `retryNotification(id, body)` | `POST /notifications/{id}/retry` | `{ by }` | `{ notification }` (a new message with `retry_of`). 409 unless the message failed and has not been sent again already |
| `updateConsent(patientId, body)` | `PATCH /patients/{id}/consent` | `{ channels }` | `{ patient }`; logs a `consent_withdrawn` event for anything removed |

## Sign-in and accounts *(added; section 11 does not cover auth)*

Sessions live in httpOnly, Secure, SameSite=Lax cookies set by the backend. The frontend never stores a token when mocks are off.
Error rules: sign-in and reset responses must not reveal whether an account exists. Return `locked: true` in the error body when too many wrong PINs mean the patient must use a code instead.

### Patients and family helpers

- Patients and helpers sign in with their **email address**, not a phone number (decided by Nunsi, 5 Nov 2026). Codes are 6 digits, sent by email only, valid 300 s, resend after 60 s, 5 wrong tries per code.
- `masked_email` always echoes the address the person typed. An address with no account gets the same answer and nothing is sent, so the screen cannot reveal whether it has an account. Matching is case-insensitive.
- Invites ask for the person's own `email`; it is saved to the patient or caregiver once the code is verified, and becomes how they sign in. One account per address: an address already used by another account gets 409 (the person holds a valid invite code, so this tells a stranger nothing). A patient's own address on file is fine.
- A helper's phone number comes from the patient's "add a helper" form and is saved on their account when they join, so Tomi knows them when they call. The patient's phone is set by the care team. Phones are for calls, never for sign-in.
- The PIN is 4 digits, any 4 digits (simple PINs are allowed). It opens the app on a remembered phone, which remembers the account's email address; phone calls have no PIN. 5 wrong PINs locks PIN sign-in until a code is used.
- The app locks after `idle_lock_minutes` (10) without activity.
- Phone numbers (the care team's patient form, a helper's number) can be from any country. The app sends `phone` as `+<country code> <number as typed>` (for example `+234 0803 123 4567` or `+44 7400 123456`); a number typed without `+` is read as Nigerian. The backend normalises to E.164 and drops a leading trunk `0` after the country code.

```json
PatientSession: { "id": "ps_...", "kind": "patient | caregiver", "patient_id": "p-zainab", "user_name": "Hadiza Musa",
  "acting_for_name": "Zainab Musa or null", "relation": "Daughter or null", "email": "hadiza.musa@example.com", "pin_set": true,
  "consent_needed": false, "idle_lock_minutes": 10, "expires_at": "ISO" }
Challenge: { "challenge_id": "ch_...", "masked_email": "t••••@example.com", "via": "email", "expires_in": 300, "resend_in": 60 }
Invite: { "code": "CL-7K4Q", "kind": "patient | caregiver", "facility": "string", "invited_by": "string",
  "patient_first_name": "Chidi", "caregiver_name": "string or null", "relation": "string or null", "masked_email": "the patient's address on file, or null" }
Caregiver: { "id": "cg-1", "patient_id": "p-zainab", "name": "Hadiza Musa", "relation": "Daughter", "masked_phone": "string or null", "scope": "string", "added_at": "ISO" }
```

| `CareLoopAPI` method | HTTP | Request body | Response |
|---|---|---|---|
| `getPatientSession()` | `GET /auth/patient/session` | | `{ session: PatientSession or null }` |
| `startEmailSignIn(body)` | `POST /auth/patient/otp` | `{ email }` | `Challenge` (same answer for unknown addresses); 400 for an address that is not valid |
| `startInviteSignIn(code, body)` | `POST /auth/invites/{code}/otp` | `{ email }` | `Challenge`; 409 if the address belongs to another account |
| `resendCode(id)` | `POST /auth/patient/otp/{id}/resend` | | `Challenge`; 429 before `resend_in` |
| `verifyCode({ challenge_id, code })` | `POST /auth/patient/otp/{id}/verify` | `{ code }` | `{ session }`; 401 wrong, 410 expired |
| `signInWithPin(body)` | `POST /auth/patient/pin-sign-in` | `{ email, pin }` | `{ session }`; 401 with `locked`; 404 if the remembered address has no account |
| `setPin(body)` | `POST /auth/patient/pin` | `{ pin }` | `{ session }` |
| `getInvite(code)` | `GET /auth/invites/{code}` | | `{ invite }`; 404 or 410 |
| `signOutPatient()` | `POST /auth/patient/sign-out` | | `{ ok }` |
| `listCaregivers(patientId)` | `GET /patients/{id}/caregivers` | | `{ caregivers[], invites[] }` |
| `inviteCaregiver(patientId, body)` | `POST /patients/{id}/caregivers` | `{ name, relation, phone }` | `{ invite }` (backend texts the code) |
| `removeCaregiver(patientId, id)` | `DELETE /patients/{id}/caregivers/{caregiverId or invite code}` | | `{ ok }` |

### Care team

- Password: at least 8 characters, no composition rules, block common and breached passwords and the user's email (NIST SP 800-63B). Lock for a short time after 5 failures.
- Every sign-in needs a second step: a 6-digit code emailed to the account's address (15 minutes, 5 tries, resend after 60 s). There are no authenticator apps or backup codes. Someone who loses their email asks their facility's CareLoop admin to change it. Staff sessions last 12 h and the page locks after 15 idle minutes.
- Staff join two ways: an invite link from a colleague, or self sign-up with any email address (personal addresses are allowed), a care facility from `GET /facilities` (a hospital, pharmacy, clinic or care home; the person picks the type first, then the facility) and that facility's join code. The facility's CareLoop admin hands the code to their own staff and can change it at any time. Without the right code for the chosen facility, no account is created (403 with `field: "join_code"`). After 5 wrong codes, sign-up is blocked for 10 minutes (429). Join codes are never sent to the browser. Sign-up then confirms the email with a 6-digit code and signs the person in. If the address already has an account, the response is the same and the email tells the owner to sign in instead.
- Production: rate-limit join-code attempts per IP address and per facility, log each sign-up for the facility admin, and let the admin remove an account.
- Each staff user sees only patients at their own care facility. The mock keeps one set of sample patients and moves them to the signed-in user's facility.

```json
StaffSession: { "id": "ss_...", "user": { "id": "u-ada", "name": "Dr. Ada Okafor", "email": "string", "role": "string", "facility": "string", "initials": "AO", "is_admin": true },
  "remember_device": false, "idle_lock_minutes": 15, "expires_at": "ISO" }
```

| `CareLoopAPI` method | HTTP | Request body | Response |
|---|---|---|---|
| `getStaffSession()` | `GET /auth/staff/session` | | `{ session: StaffSession or null }` |
| `staffSignIn(body)` | `POST /auth/staff/sign-in` | `{ email, password }` | `{ mfa_token, masked_email, resend_in }` and emails a code; 401 generic message, 429 locked |
| `resendStaffMfaEmail(body)` | `POST /auth/staff/mfa/email` | `{ mfa_token }` | `{ resend_in }` |
| `verifyStaffMfa(body)` | `POST /auth/staff/mfa` | `{ mfa_token, code, remember_device }` | `{ session }`; 401 wrong code, 410 timed out, 429 too many |
| `listFacilities()` | `GET /facilities` | | `{ types: [{ id, label }], facilities: [{ id, type, name, city, country }], roles: string[] }`. `type` is one of `hospital`, `pharmacy`, `clinic`, `care_home`. The mock adds `demo_join_code` to each facility for the MVP notice on sign-up; the real backend must never return it. |
| `staffSignUp(body)` | `POST /auth/staff/sign-up` | `{ name, email, password, facility_id, join_code, role, confirmed }` | `{ signup_token, masked_email, resend_in }` and emails a 6-digit code; 403 wrong join code, 429 too many |
| `resendSignUpCode(body)` | `POST /auth/staff/sign-up/resend` | `{ signup_token }` | `{ resend_in }`; 429 too soon |
| `verifySignUpEmail(body)` | `POST /auth/staff/sign-up/verify` | `{ signup_token, code }` | `{ session }`; 401 wrong code, 410 expired |
| `requestPasswordReset(body)` | `POST /auth/staff/password-reset` | `{ email }` | `{ ok }` always |
| `checkResetToken(token)` | `GET /auth/staff/password-reset/{token}` | | `{ email_masked }`; 410 expired |
| `resetPassword(token, body)` | `POST /auth/staff/password-reset/{token}` | `{ password }` | `{ ok }`; signs out all sessions |
| `getStaffInvite(token)` | `GET /auth/staff/invites/{token}` | | `{ invite: { name, email, role, facility, invited_by } }` |
| `acceptStaffInvite(token, body)` | `POST /auth/staff/invites/{token}/accept` | `{ password }` | `{ session }` (the invite link already proves the email) |
| `unlockStaffSession(body)` | `POST /auth/staff/unlock` | `{ password }` | `{ session }` |
| `changePassword(body)` | `POST /auth/staff/password` | `{ current, next }` | `{ ok }`; signs out other sessions |
| `listStaffSessions()` | `GET /auth/staff/sessions` | | `{ sessions: [{ id, device, signed_in_at, last_seen_at, current }] }` |
| `staffSignOut(body)` | `POST /auth/staff/sign-out` | `{ everywhere }` | `{ ok }` |

The mock adds `demo_code` to challenges, `demo_link` to reset responses and `demo_message` (the text or email the person would receive) to anything that sends one, so testers can continue without SMS or email. The real backend must never return them.

## Endpoints

| `CareLoopAPI` method | HTTP | Request body | Response |
|---|---|---|---|
| `getSupportInfo()` | `GET /support` *(added)* | | `{ tomi_number, emergency_number, emergency_text }` |
| `listStaff()` | `GET /staff` *(added)* | | `{ staff: [{ id, name, role }] }`, the care team at your facility |
| `assignPatient(id, body)` | `PATCH /patients/{id}/assignment` *(added)* | `{ staff_id or null }` | `{ patient }`; logged on the timeline |
| `getAdminFacility()` | `GET /admin/facility` *(added; admin only)* | | `{ facility: { id, type, name, city, country, join_code }, staff: [{ id, name, email, role, is_admin, joined_at, last_seen_at }] }` (newest first); 403 for non-admins |
| `newJoinCode()` | `POST /admin/join-code` *(added; admin only)* | | `{ join_code }`; the old code stops working |
| `removeStaff(id)` | `DELETE /admin/staff/{id}` *(added; admin only)* | | `{ ok }`; signs them out everywhere and unassigns their patients; 409 for yourself |
| `listPatients()` | `GET /patients` | | `{ patients: Patient[] }` |
| `getPatient(id)` | `GET /patients/{id}` | | `{ patient }` |
| `createPatient(body)` | `POST /patients` | `{ name, phone_e164, email, language, literacy_level, caregiver_mode }` (email required: the patient signs in with it) | `{ patient }`; 400 without a valid email, 409 if the number or email is already linked to someone |
| `updateProfile(id, body)` | `PATCH /patients/{id}/profile` | `{ language, literacy_level, caregiver_mode }` | `{ patient }` |
| `recordConsent(id, body)` | `POST /patients/{id}/consent` | `{ channels[], scope, version, contact_window, pin? }` | `{ patient }` |
| `createPlan(body)` | `POST /patients/{id}/plan` | `{ patient_id, source_note }`; runs Care Plan and Plan Verifier | `{ plan }` |
| `getPlan(id)` | `GET /patients/{id}/plan` | | `{ plan, tasks: Task[] }` |
| `updatePlan(planId, body)` | `PATCH /plans/{planId}` *(added)* | edited Plan fields | `{ plan }` with the rule checks run again. Times are read as people write them ("5pm", "17.00") and saved as HH:MM; dates ("9/11/2026", day first) as YYYY-MM-DD. A value the clinician fills into an empty field or a new item is not flagged as "not in the note" (`clinician_entered` keeps track); changing a value drafted from the note is still checked. 400 names the field to fix in plain words |
| `approvePlan(planId, body)` | `POST /plans/{planId}/approve` | `{ override_issues }` | `{ plan }` |
| `getMessages(id)` | `GET /patients/{id}/messages` | | `{ messages[], welcome? }`. For the patient or their caregiver, `welcome: { text, suggestions[] }` is Tomi's greeting: their first name, what she can do and "What would you like to ask?" (one line each, separated by newlines), plus questions to tap (today's plan, the next visit if one is booked, the first medicine on the approved plan). Prepared lines in the patient's language from `voice/prompts/lines.json`, never generated. Not sent to staff |
| `sendMessage(id, body)` | `POST /patients/{id}/messages` | `{ original_text, language, task_id?, quick_reply? }` | `{ reply, barrier, escalation, reschedule }`. `reply.original_text` is in the patient's language when the Language Agent's checks pass, with `english_text`, `language`, `number_check_passed` and `uncertainty_flags`; otherwise English with `number_check_passed: false` |
| `listEvents({ patient_id, limit })` | `GET /patients/{id}/events`, or `GET /events` *(added)* for the feed across all patients | | `{ events: CareEvent[] }`, newest first |
| `listAppointments(filters)` | `GET /appointments?patient_id=` | | `{ appointments[] }` |
| `listSlots()` | `GET /clinic-slots` *(added)* | | `{ slots[] }` (future slots) |
| `listRescheduleRequests(filters)` | `GET /reschedule-requests?status=pending` *(added)* | | `{ requests[] }` |
| `createRescheduleRequest(apptId, body)` | `POST /appointments/{id}/reschedule-requests` | `{ reason }` | `{ request, appointment }` |
| `decideReschedule(reqId, body)` | `POST /reschedule-requests/{id}/decision` | `{ decision: "approve" or "reject", slot_id? }` | `{ request }`; 409 if the slot was taken |
| `recordAttendance(apptId, body)` | `POST /appointments/{id}/attendance` | `{ status: "attended" or "no_show" }` | `{ appointment }` |
| `listBarriers(filters)` | `GET /barriers?status=open` *(added)* | | `{ barriers[] }` |
| `listNotifications(filters)` | `GET /notifications?patient_id=` *(added)* | | `{ notifications[] }` |
| `listCalls({ patient_id })` | `GET /patients/{id}/calls`, or `GET /calls` *(added)* | | `{ calls[] }`, newest first |
| `getCall(id)` | `GET /calls/{id}` *(added)* | | `{ call }`; the UI polls it every second during a live call |
| `requestOutboundCall(body)` | `POST /calls/outbound` | `{ patient_id, reason }` | `{ call }`; 403 if no voice consent |
| `createVoiceSession(body)` | `POST /voice/sessions` *(added)* | `{ patient_id }` | `{ session: { id, mode: "livekit", url, token, language } }` |
| `sendVoiceInput(id, body)` | `POST /voice/sessions/{id}/input` *(added; mock only)* | `{ transcript?, confidence?, digit?, pin? }` | `{ turns[], state, keypad[], ended, pin_required?, escalation?, barrier? }` |
| `endVoiceSession(id)` | `POST /voice/sessions/{id}/end` *(added)* | | `{ ok }` |
| `listEscalations(filters)` | `GET /escalations?status=open` | `open` means any status except resolved | `{ escalations[] }` |
| `acknowledgeEscalation(id, body)` | `POST /escalations/{id}/acknowledge` | `{ by }` | `{ escalation }`; no change if it is already acknowledged or resolved |
| `resolveEscalation(id, body)` | `POST /escalations/{id}/resolve` | `{ note, by }` | `{ escalation }` |

## Browser voice (Tomi)

In the real system, `createVoiceSession` returns a short-lived LiveKit token. The browser joins the room, and the Tomi worker (`voice/tomi_agent.py`) handles audio, Spitch speech-to-text and text-to-speech, and turn-taking. The patient is already signed in, so browser voice has no PIN check. Phone calls have none either (decided by Nunsi, 5 Nov 2026): a number on file is enough. Turns reach the backend as normalized voice events (doc section 22.2).

Until the backend exists, `frontend/api/voice/sessions.js` issues that token: a Vercel function on the preview, served by Vite during `npm run dev`. It needs `LIVEKIT_URL`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` (root `.env` locally, Vercel project settings on the preview) and answers `503` without them. The token asks LiveKit to dispatch the agent `tomi` with job metadata `{ "patient_id", "language" }`. Body: `{ patient_id, language }`. Response: `{ session: { id, mode: "livekit", url, token, language } }`. The backend's own `POST /voice/sessions` issues the same token after checking the patient's session; this stand-in does not.

With mocks on, `createVoiceSession` tries that route first and falls back to the scripted mock session if it is not set up (`?voice=mock` forces the script). The voice sheet then joins the room through `shared/live-voice.js` (`livekit-client`): microphone in, Tomi's audio out, captions from the `lk.transcription` text stream, Tomi's state from the agent's `lk.agent.state` attribute, and the emergency button when the agent sets `careloop.escalation` to `open`.

The scripted mock session uses `sendVoiceInput`, a dialog driven by keypad presses and demo phrases.

## Voice worker *(added; used by `voice/tomi_agent.py`, not by the browser)*

The Tomi worker calls these with `Authorization: Bearer <VOICE_SERVICE_TOKEN>`, a service token that can only
use these routes (built in `backend/app/routes/voice.py`). Set `VOICE_USE_MOCKS=0` to use them; with `1` the worker
runs on its own mock (`voice/backend_client.py`).
Outgoing calls: `POST /calls/outbound` dispatches the LiveKit agent `tomi` with job metadata
`{ "call_id", "patient_id", "phone_e164" }`. Browser voice tokens carry the participant attribute `careloop.patient_id`.

| Route | Request body | Response |
|---|---|---|
| `POST /voice/calls` | `{ direction, phone_e164?, patient_id? }` | `{ call: { id, language, patient_id, known } }`. No PIN: an incoming number on file (the patient's or a caregiver's) is `known: true` with the patient's language; an outbound call is to the number on the record. An unknown number is `known: false`, and Tomi only tells it about CareLoop |
| `GET /voice/calls/{id}/context` | | `{ context: { patient: { id, first_name, language, timezone }, caller: { kind: "patient" } \| { kind: "caregiver", first_name, relation }, consent: { voice }, facility, plan, today[], tasks[], opening } }`; 403 for an unknown caller. `plan` is the approved plan only. `opening` is an approved line in the patient's language, or null |
| `POST /voice/calls/{id}/medicine` | `{ name }` | What a medicine **on the caller's plan** is generally used for: `{ found, name, generally_used_for, source, note }` from MedlinePlus, no doses. A medicine not on the plan is `{ found: false, note }`; 403 for an unknown caller |
| `POST /voice/calls/{id}/turns/check` | `{ text, language, confidence? }` | `{ action: "continue" }`, `{ action: "clarify" }` (unclear speech: ask again) or `{ action: "escalate", escalation }`. Runs the safety rules; an escalation is opened before it answers. For an unknown caller a red flag is `{ action: "escalate", escalation: null }` (the emergency line, no record). The worker sends `confidence: 0.4` for a transcript it judges unclear (Spitch gives no score) |
| `POST /voice/calls/{id}/turns` | `{ speaker: "tomi" \| "patient", transcript, language }` | `{}`; text only, no audio |
| `POST /voice/calls/{id}/task-updates` | `{ task_id, status: "done" \| "not_done" \| "unable", original_text }` | `{ ok }`; recorded as `patient_reported` after the patient confirmed it |
| `POST /voice/calls/{id}/barriers` | `{ type: "cost" \| "transport" \| "distance" \| "stock" \| "no_helper" \| "other", original_text, task_id? }` | `{ ok }` |
| `POST /voice/calls/{id}/questions` | `{ original_text }` | `{ ok }`; shows on the dashboard for the care team |
| `POST /voice/calls/{id}/end` | `{ outcome: "completed" \| "escalated" \| "unverified" \| "not_reached" \| "unknown_caller", states[] }` | `{}` |

## Demo-only endpoints

The UI shows these only while mocks are on:

- `POST /demo/patients/{id}/reminders/next`
- `POST /demo/calls/inbound` with `{ patient_id }`
- `GET /demo/voice-phrases`
- `GET /demo/sample-notes`
- `POST /demo/reset`

## Care-team assistant (Tomi)

Every assistant in CareLoop is called Tomi (decided by Nunsi, 5 Nov 2026). When the panel opens, `getAssistantWelcome`
greets the clinician by first name (titles such as "Dr." dropped), says what Tomi can do, asks what they would like to
ask, and offers questions to tap, built from the facility's own patients (or the selected one). A tapped question is sent
at once.

A panel in the dashboard where a clinician types or speaks (browser speech-to-text, `en-NG`) a question or an instruction.

**Questions** (and pasted reports to explain) come back as `mode: "answer"` with the answer in `reply`, `actions: []`,
and nothing changed. The agent reads every patient in the clinician's facility (status, tasks, problems, escalations,
next visit, medicines, last contact) and, for a named or selected patient, the whole record. It looks medicines up
(uses, warnings, interactions) in MedlinePlus and US FDA drug labels only, never the open web, and names the source.
`history` (the last few `{ role: "user" | "assistant", content }` turns) lets a follow-up such as "and her visits?" make
sense. Without a model it answers with counts from the record.

**Instructions** come back as `mode: "draft"`. The backend **Clinician Assistant Agent** turns it into proposed changes; nothing is saved until the
clinician confirms. The agent only uses what the clinician said: it never adds a medicine, dose, time or place they did
not give, and flags anything missing as an `issue`. Changes the patient has not consented to (texts, calls) come back
`blocked` and are skipped on apply. Every applied change is logged as a `clinician_verified` event under the clinician's name.

| `CareLoopAPI` method | HTTP | Request body | Response |
|---|---|---|---|
| `getAssistantWelcome({ patient_id? })` | `GET /assistant/welcome?patient_id=` | | `{ welcome: { text, suggestions[] } }`. 404 for a patient outside the facility |
| `draftAssistantActions(body)` | `POST /assistant/drafts` | `{ text, patient_id?, history? }` | `{ draft: { instruction, mode: "answer" \| "draft", patient, reply, needs_patient, choices?, actions[], templates[] } }` |
| `applyAssistantActions(body)` | `POST /assistant/apply` | `{ patient_id, actions[], by }` | `{ results: [{ id, kind, ok, summary }], patient }` |

Without `patient_id` the agent looks for a patient's name in the text; if none, `needs_patient: true` with `choices`.

```json
AssistantAction (one of):
{ "id": "act-…", "kind": "medicine", "title": "Paracetamol 500 mg tablet", "detail": "2 tablets", "times": ["08:00","20:00"], "days": 5, "starts_on": "YYYY-MM-DD", "issues": [] }
{ "id": "act-…", "kind": "test", "title": "Kidney function test", "detail": "Hospital laboratory", "due_at": "ISO", "issues": [] }
{ "id": "act-…", "kind": "visit", "what": "Diabetes review", "where": "Diabetes Clinic", "starts_at": "ISO", "issues": [] }
{ "id": "act-…", "kind": "send_text", "template": "medicine | visit | call_clinic", "blocked": false, "issues": [] }
{ "id": "act-…", "kind": "call_patient", "blocked": false, "issues": [] }
{ "id": "act-…", "kind": "note", "text": "string", "issues": [] }
```

Applying: `medicine` creates one pending task per time per day (past times skipped); `test` one task; `visit` one
appointment; both reschedule SMS/email reminders. `send_text` queues a generic template; `call_patient` starts a Tomi
call; `note` adds a `care_team_note` event to the timeline.
