# CareLoop AI launch checklist

Everything left between the current frontend and a working app. When something is done, change `[ ]` to `[x]`,
add the date and who did it, and commit the change with the work.

Owners follow the README branches: **Nunsi** (frontend, language, voice), **Olamide** (backend core),
**Mary** (care plan agents), **Dorcas** (check-in, escalation, safety).

Last updated: 3 Nov 2026

## Progress

| Section | Done |
|---|---|
| 1. Accounts and keys | 0 / 11 |
| 2. Backend core | 11 / 13 |
| 3. Agents | 7 / 9 |
| 4. Safety | 3 / 5 |
| 5. Tomi voice | 1 / 6 |
| 6. Frontend | 5 / 13 |
| 7. Deploy | 1 / 7 |
| 8. Clinical and team sign-off | 1 / 6 |

Update this table when you tick items off.

## 1. Accounts and keys

Set up email sending first: since 3 Nov 2026 email carries reminders and patient sign-in codes, and SMS waits
until there is a provider (Termii needs a CAC registration). Apply for the voice number early; it can take weeks.

- [ ] **Groq API key** (console.groq.com) → `GROQ_API_KEY`. Pick the model for the agents and set `GROQ_MODEL`.
  Check the free-tier rate limits before the judges' demo; upgrade if several people will test at once. — Nunsi
  Key works with `openai/gpt-oss-120b` (Tomi, Care Plan Agent and Plan Verifier, 3 Nov 2026); rate limits not checked yet.
- [ ] **Spitch API key** for Hausa, Yoruba and Igbo speech → `SPITCH_API_KEY`. Test it on medical words early. — Nunsi
- [ ] **LiveKit Cloud** project → `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`. — Nunsi
- [ ] **Phone number for Tomi calls**: Africa's Talking (`AT_USERNAME`, `AT_API_KEY`) or Twilio (`TWILIO_*`).
  Twilio trial accounts can only call numbers you have verified. — Olamide
- [ ] **LiveKit SIP trunk** linked to that phone number → `LIVEKIT_SIP_TRUNK_ID`. — Nunsi
- [ ] **Email sending** (needed now): a Gmail app password (`smtp.gmail.com`) or Brevo (`smtp-relay.brevo.com`) →
  `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`; Resend once there is a domain. Then send one real reminder
  and one sign-in code to a team inbox. — Olamide
- [ ] **SMS provider** (later; Africa's Talking or Termii) → `SMS_PROVIDER`, `SMS_API_KEY`. — Olamide
- [ ] **SMS sender ID registered** (later; `SMS_SENDER_ID`), on the transactional route so codes reach DND numbers. — Olamide
- [ ] **Hosted Postgres** (Neon or Supabase) → `DATABASE_URL` for the deployed backend. — Olamide
- [ ] **Backend hosting** (Render, Railway or Fly.io) for FastAPI, the reminder scheduler and the voice worker. — Olamide
- [ ] **Generated secrets** `SESSION_SECRET`, `CODE_PEPPER`, `WEBHOOK_SECRET`, stored in the host's settings, never in Git. — Olamide

Optional: a domain (`.com` is quickest; `.ng` needs NiRA paperwork) for a proper email sender and URL.

## 2. Backend core (FastAPI)

The contract is `docs/api_shapes.md`. Each route should return exactly what the frontend mock returns today.

- [x] Database models: hospitals, staff, patients, caregivers, invites, plans, tasks, events, appointments,
  escalations, calls, notifications. — Olamide (done by Nunsi, 3 Nov 2026: `backend/app/db.py`, one JSON record table on
  SQLite or Postgres; plan contract in `models.py`. Runs as one backend process)
- [x] Seed data: `data/synthetic_patients.json`, `data/resources.json`, sample discharge notes in `data/sample_discharges/`. — Mary
  (done by Nunsi, 3 Nov 2026: five patients matching the frontend mock, five barrier contacts, five notes with
  seeded dose and date errors plus `expected.json`)
- [x] Plan flow in the orchestrator: on `POST /patients`, run the Care Plan Agent then the Plan Verifier, store the
  verifier's `issues` as `verifier_issues`, and never send a plan while `deliverable` is false or before a
  clinician approves (`docs/api_shapes.md`, "Plan"). — Olamide
  (done by Nunsi, 3 Nov 2026: `services/plans.py`; approval creates the tasks and visits, and emails the patient an invite)
- [x] Patient sign-in: code by email (to the address on the account, never shown) or voice call, PIN on a remembered
  phone, invite codes that collect the person's email, caregivers. SMS codes later. — Olamide (done by Nunsi, 3 Nov 2026; codes by phone call
  answer 503 until there is telephony)
- [x] Staff sign-in: password, 6-digit email code, password reset, idle lock. — Olamide (done by Nunsi, 3 Nov 2026)
- [x] Staff sign-up with hospital join code (lockout after 5 wrong codes), invite links. Never return `demo_join_code`. — Olamide
  (done by Nunsi, 3 Nov 2026)
- [x] Sessions in httpOnly cookies, rate limits on every code and PIN route. — Olamide (done by Nunsi, 3 Nov 2026; tokens stored hashed,
  passwords and PINs with scrypt, codes with HMAC; rate limits are in memory)
- [x] Patient routes: today, tasks, plan, chat, appointments, account and consent settings. — Olamide (done by Nunsi, 3 Nov 2026)
- [x] Dashboard routes: overview, patients, profile, plan review, appointments, reminders, escalations. — Olamide
  (done by Nunsi, 3 Nov 2026; every field the app reads checked against the mock)
- [x] Reminder scheduler: 30 minutes before each task, 18:00 before a visit, nothing 21:00–07:00,
  consent checked at send time, retries. — Olamide
  Rules written 3 Nov 2026 (`services/notifications.py`: `plan_reminders`, `dispatch`, `send_sign_in_code`, with
  tests); APScheduler job every 30 s in `scheduler.py` (done by Nunsi, 3 Nov 2026): sends due reminders, marks tasks overdue
  2 hours after they were due (never treated as a missed dose), clears expired codes.
- [ ] Provider adapters for SMS, email and calls, with signed delivery-report webhooks. — Olamide
  Email adapter written 3 Nov 2026 (`adapters/email.py`, SMTP or console); SMS stays off (`adapters/sms.py`) until
  there is a provider. Calls and webhooks still to do.
- [x] Each staff account sees only its own hospital's patients (checked on every route). — Olamide (done by Nunsi, 3 Nov 2026;
  tested with a second facility)
- [ ] Tests: the acceptance tests in section 17 of the project documentation. — All
  Done 3 Nov 2026: care plan integrity (`test_plan_verifier.py`, `test_care_plan.py`) and verification (a shared
  phone or wrong PIN reveals nothing, `test_api.py`). Still to write: voice languages, red flags per language,
  event provenance.

## 3. Agents (Groq)

All agents call Groq through one shared client, so the model can be changed in one place.

- [x] Shared Groq client: model from `GROQ_MODEL`, timeouts, retries, JSON output checked against a schema. — Olamide
  (done by Nunsi, 3 Nov 2026: `agents/llm.py`, used by the plan, Check-in and Escalation Summary agents)
- [x] Care Plan Agent: discharge note → draft plan for clinician review. — Mary (done by Nunsi, 3 Nov 2026:
  `agents/care_plan.py`; removes anything the note does not support; run on the five sample notes with Groq)
- [x] Plan Verifier Agent: flags anything in the draft not found in the note. — Mary (done by Nunsi, 3 Nov 2026:
  rule checks in `agents/plan_rules.py` always run, then a model pass; review rules in `docs/plan-review-criteria.md`;
  notebook `notebooks/care_plan_verifier.ipynb`)
- [x] Mary reviews the plan agents, the seeded notes and `docs/plan-review-criteria.md`, and agrees the plan
  schema (`backend/app/models.py`) with Olamide. — Mary (done by Nunsi, 3 Nov 2026: agents re-run on six notes with
  Groq, shorthand false alarms fixed, plan format and its six decisions recorded in `docs/plan-format.md`)
- [x] Check-in Agent: Tomi's daily check-ins in chat. — Dorcas
  (done by Nunsi, 3 Nov 2026: wired into chat in `services/chat.py`; marking a task done waits for the patient's "yes", and its replies
  pass the number check and an advice guard or a fixed line is sent. Run with Groq, including a Hausa message)
- [x] Barrier Agent: cost, transport and distance problems → hospital resources. — Dorcas (done by Nunsi, 3 Nov 2026: `agents/barrier.py`,
  approved contacts only; escalates after 2 options that did not work)
- [x] Escalation Agent: red flags → open escalation on the dashboard. — Dorcas (done by Nunsi, 3 Nov 2026: `agents/escalation.py` and
  `services/escalations.py`; fact-only brief, care-team email without patient details, backup after 15 minutes)
- [ ] Language Agent: Hausa, Yoruba, Igbo and plain English, reading level checks. — Nunsi
- [ ] Clinician Assistant: `POST /assistant/drafts` and `POST /assistant/apply`, same rules as the mock
  (only what the clinician said, missing details flagged, no texts or calls without consent). — Nunsi

## 4. Safety

- [ ] `red_flags.json` filled in with the clinical mentor. — Dorcas
  Draft written 3 Nov 2026 (8 rules in four languages, negation and unclear-speech handling, amber policies); waiting
  for the mentor and native speakers: `docs/clinical-safety-review.md`.
- [x] Safety rules run before any agent reply reaches a patient; red flags skip the model entirely. — Dorcas
  (done by Nunsi, 3 Nov 2026: `safety/rules.py` on every chat message and voice turn; tests per language in `tests/test_safety.py`)
- [x] Numbers in outgoing text (doses, times) checked against the approved plan. — Dorcas (done by Nunsi, 3 Nov 2026: `safety/number_check.py`)
- [ ] Low-confidence speech is read back to the patient or sent to a person. — Nunsi
- [x] SMS and email templates never name a medicine, condition or test. — Olamide (done by Nunsi, 3 Nov 2026: checked in
  `tests/test_notifications.py` for every template)

## 5. Tomi voice

- [ ] `voice/tomi_agent.py`: LiveKit worker using Spitch for speech and Groq for replies. — Nunsi
  Code written 2 Nov 2026 from Tech-sis123/agricall (with permission); tick once it has run with real LiveKit,
  Spitch and Groq keys (`python tomi_agent.py console`).
- [ ] `voice/call_controller.py`: call states, keypad fallback, PIN check, consent prompt. — Nunsi
  Code and tests written 2 Nov 2026; tick after the first real phone call.
- [x] Backend routes for the voice worker (`docs/api_shapes.md`, "Voice worker"), then `VOICE_USE_MOCKS=0`. — Olamide
  (done by Nunsi, 3 Nov 2026; tested over HTTP. Set `VOICE_USE_MOCKS=0` and the same `VOICE_SERVICE_TOKEN` in both when you run
  them together)
- [ ] Incoming calls: patient rings the Tomi number. — Nunsi
- [ ] Outgoing calls: scheduled check-ins and the dashboard's "Call patient". — Nunsi
- [ ] Prompts in all four languages checked by native speakers (`voice/prompts/lines.json`; Hausa, Yoruba and
  Igbo are first drafts). — Nunsi

## 6. Frontend

- [x] Patient app, dashboard and landing page on sample data. — Nunsi, Oct 2026
- [x] Staff sign-in by email code, sign-up with hospital join code, five hospitals. — Nunsi, 1 Nov 2026
- [x] Clinician Assistant panel with typing and voice. — Nunsi, 1 Nov 2026
- [x] Any care facility, not only hospitals: facility type on sign-up (hospital, pharmacy, clinic, care home),
  sample facilities in Ghana and Kenya, phone numbers from any country. — Nunsi, 2 Nov 2026
- [x] Email first: SMS switched off in the app (`SMS_AVAILABLE` in `shared/languages.js`), sign-in codes and
  invites by email, onboarding asks for an email address, dashboard "Send a message" uses email. — Nunsi, 3 Nov 2026
- [ ] Bedside welcome text on onboarding. Decide first: language of the text, and what happens if the patient
  hasn't signed in after 24 hours. With SMS off, this becomes a welcome email or a printed invite code. — Nunsi
- [ ] Assign patients to clinicians. — Nunsi
- [ ] Hospital admin page: change the join code, remove staff, see new sign-ups (needs Nunsi's OK for a new page). — Nunsi
- [ ] Privacy notice and terms pages (NDPA 2023). — Nunsi
- [ ] Every screen tested with `?mock=0` against the real backend. — Nunsi
- [ ] `/api/*` rewrite in `frontend/vercel.json` pointing at the backend. — Nunsi
- [ ] Real backend made the default on the live site (mocks off). — Nunsi
- [ ] Beta chips removed for each language that passes native-speaker checks. — Nunsi

## 7. Deploy

- [x] Vercel project with Root Directory `frontend`. — Nunsi, 1 Nov 2026
- [ ] Vercel preview confirmed loading for the whole team. — Nunsi
- [ ] Backend deployed with all keys from section 1 in the host's settings. — Olamide
- [ ] Voice worker deployed and running all the time. — Nunsi
- [ ] Database backups switched on. — Olamide
- [ ] Error alerts (logs or an uptime check) on the backend and voice worker. — Olamide
- [ ] Full end-to-end run: discharge note → approved plan → reminder text → Tomi call → escalation on the dashboard. — All

## 8. Clinical and team sign-off

- [ ] Clinical mentor approves red flags, reminder wording and escalation steps (`docs/clinical-safety-review.md`). — Dorcas
- [ ] Provider tests from section 20 of the project documentation: speech quality, Nigerian call routing, SMS sender approval. — All
- [ ] The five open decisions added to section 20 of the project documentation. — All
- [ ] Team reviews the tracked changes in the project documentation. — All
- [x] Project documentation updated: Groq replaces the Claude API in section 10.1. — Nunsi, 2 Nov 2026
- [ ] Demo script (`docs/demo-script.md`) rehearsed against the real backend. — All
