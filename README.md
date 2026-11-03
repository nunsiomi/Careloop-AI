# CareLoop AI

Follow-up care after a patient leaves a hospital, pharmacy, care home or other care facility. Patients and their
families get help from **Tomi**, an assistant that talks with them by chat, voice and phone call. The first languages
are Hausa, Yoruba, Igbo and plain English. Care teams get a dashboard that shows who needs them now. A rules-gated multi-agent system drafts the care plans, and a clinician approves every one before it
reaches a patient. Synthetic data only.

Team: Dorcas, Nunsi, Olamide, Mary.

## Where things stand

- **Frontend: built.** It runs on sample data in the browser: the landing page, the patient app, the care-team
  dashboard, the Clinician Assistant, and sign-in for patients and staff.
- **Tomi voice worker: written, not yet run with real keys.** `voice/` holds a LiveKit worker built from
  [Tech-sis123/agricall](https://github.com/Tech-sis123/agricall) (used with permission). It runs on its own
  sample patient until it is pointed at the backend (`VOICE_USE_MOCKS=0`). See [voice/README.md](voice/README.md).
- **Backend: built, not yet deployed.** FastAPI in `backend/` serves every route in `docs/api_shapes.md`: sign-in
  with email codes, patients, plans (Care Plan Agent and Plan Verifier), chat, visits, email reminders,
  escalations, the Clinician Assistant and the Tomi worker's routes. It starts with the same sample facility as
  the mock. Open the app with `?mock=0` to use it.
- **Agents and safety:** Care Plan, Plan Verifier, Check-in, Barrier and Escalation Summary agents are wired in.
  Every message passes the red-flag rules first (`backend/app/safety/`). The rules are a draft until the clinical
  mentor signs [docs/clinical-safety-review.md](docs/clinical-safety-review.md).
- **AI models:** Groq (`GROQ_API_KEY`), not the Claude API.

What's left, with owners and checkboxes: **[docs/launch-checklist.md](docs/launch-checklist.md)**. When you finish an
item, tick it there in the same commit as the work.

## Documentation

| Document | What it covers |
|---|---|
| [docs/source/CareLoop_AI_Project_Documentation_v2_1_Team_Integration.docx](docs/source/CareLoop_AI_Project_Documentation_v2_1_Team_Integration.docx) | Full product and technical reference. It includes the v2.2 updates as tracked changes for the team to review. |
| [docs/launch-checklist.md](docs/launch-checklist.md) | Everything left before launch, with owners, API keys and accounts |
| [docs/architecture.md](docs/architecture.md) | How the frontend is built, and what has changed since documentation v2.1 |
| [docs/api_shapes.md](docs/api_shapes.md) | API contract the backend must follow (the frontend mocks follow it too) |
| [voice/README.md](voice/README.md) | Tomi's voice worker: how a call goes, the keys it needs, how to run it |
| [docs/plan-review-criteria.md](docs/plan-review-criteria.md) | What the plan checks flag, and what a clinician checks before approving a plan |
| [docs/demo-script.md](docs/demo-script.md) | Click-through for teammates and judges, with every sign-in |
| [docs/clinical-safety-review.md](docs/clinical-safety-review.md) | Red-flag rules and safety policies for the clinical mentor to review and sign |
| [CLAUDE.md](CLAUDE.md) | Rules for contributors and AI coding assistants |

## What changed in v2.2

- **Care-team sign-in.** Email, password and a 6-digit code by email. No authenticator apps and no backup codes.
- **Care-team sign-up.** Any email address, plus the care facility (hospital, pharmacy, care home and so on) and that
  facility's join code. Five wrong codes block sign-up for 10 minutes. Staff can still join by invite link.
- **Several care facilities.** Each staff member sees only their own facility's patients.
- **Clinician Assistant.** A dashboard agent that takes a typed or spoken instruction about a patient and drafts the
  changes: medicine or test reminders, visits, a text, a Tomi call, or a note. Nothing is saved until the clinician
  confirms. It never adds a medicine, dose, time or place the clinician didn't say, and it blocks texts or calls the
  patient hasn't agreed to.
- **Reminders.** Generic email templates (SMS later, once there is a provider) that never name a medicine, condition or test. They go out 30 minutes
  before each task and at 18:00 the evening before a visit, never between 21:00 and 07:00. Patients can turn each
  channel off.
- **Patient sign-in.** Phone number from any country and a 6-digit code (by email or voice call; SMS later), then a 4-digit PIN on
  a remembered phone.
  Family helpers join with an invite code from the patient.
- **Frontend stack.** React + Vite, with a team preview on Vercel.
- **AI models.** Groq instead of the Claude API.

## Repository structure

```
Careloop-AI/
├── README.md
├── CLAUDE.md                     rules for contributors and AI coding assistants
├── .env.example                  every key the backend needs (copy to .env)
├── requirements.txt              Python packages for the backend and voice worker
│
├── frontend/                     React + Vite (Nunsi)
│   ├── index.html, landing.jsx, landing.css   landing page with doors to both apps
│   ├── patient/                  patient and family-helper app, mobile first
│   │   ├── App.jsx, main.jsx, index.html
│   │   ├── Auth.jsx              phone + code, PIN, invite codes
│   │   ├── Onboarding.jsx        first visit: PIN, language, consent
│   │   ├── DayLoop.jsx, screens.jsx, parts.jsx   today, plan, visits
│   │   ├── Chat.jsx, VoiceSheet.jsx              Tomi by chat and voice
│   │   ├── Account.jsx           reminders, family helpers, sign-out
│   │   └── device.js, patient.css
│   ├── clinician/                care-team dashboard, desktop first
│   │   ├── App.jsx, main.jsx, index.html, shell.jsx
│   │   ├── Auth.jsx              email + password + code, sign-up with facility code, invites, reset
│   │   ├── Assistant.jsx         Clinician Assistant (typed or spoken instructions)
│   │   ├── components.jsx, clinician.css
│   │   └── pages/                Overview, Patients, PatientProfile, PlanReview, Appointments,
│   │                             Reminders, Calls, Escalations, Account
│   ├── shared/
│   │   ├── api.js                every network call goes through here (USE_MOCKS, ?mock=0)
│   │   ├── mock-server.js        in-browser stand-in for the backend
│   │   ├── mock-auth.js          in-browser sign-in, accounts and facility codes
│   │   ├── presenter.js          presenter mode (?presenter=1)
│   │   ├── tokens.css, base.css, fonts.js       design tokens and base styles
│   │   └── ui.jsx, auth-ui.jsx, LoopArt.jsx, languages.js, format.js
│   ├── public/favicon.svg
│   ├── vercel.json               Vercel settings for the team preview
│   ├── vite.config.js, package.json
│   └── _legacy/                  old plain HTML/JS version, reference only
│
├── backend/                      FastAPI (placeholders for now)
│   ├── app/
│   │   ├── main.py               routes (Olamide)
│   │   ├── db.py, models.py      database (Olamide)
│   │   ├── orchestrator.py       runs the agents in order
│   │   ├── scheduler.py          reminders and check-ins
│   │   ├── agents/               care_plan, plan_verifier, plan_rules (Mary), checkin, escalation,
│   │   │                         barrier (Dorcas), language (Nunsi); prompts/ holds their system prompts
│   │   ├── safety/               rules.py, red_flags.json, number_check.py (Dorcas)
│   │   ├── services/             identity, consent, appointments, notifications, activity_log
│   │   └── adapters/             sms, email, telephony, spitch
│   └── tests/
│
├── voice/                        Tomi's voice worker (Nunsi); see voice/README.md
│   ├── tomi_agent.py             LiveKit worker: language menu, PIN, safety check, check-in (Spitch + Groq)
│   ├── call_controller.py        call states, keypad input, PIN tries
│   ├── backend_client.py         calls to the backend, plus a mock with the sample patient
│   ├── prompts/lines.json        Tomi's fixed lines in four languages
│   ├── test_voice.py             tests that need no keys
│   └── Dockerfile, requirements.txt
│
├── data/                         synthetic data only
│   ├── synthetic_patients.json   the five sample patients, matching the frontend mock
│   ├── resources.json            approved contacts for the Barrier Agent
│   └── sample_discharges/        five discharge notes with seeded errors, and expected.json for the tests
│
├── notebooks/                    agent experiments only; production imports backend/app/agents/*.py
│
└── docs/
    ├── source/                   project documentation (.docx)
    ├── launch-checklist.md
    ├── architecture.md
    ├── api_shapes.md             API contract (api-contract.md points here)
    ├── plan-review-criteria.md
    ├── demo-script.md
    └── clinical-safety-review.md
```

The Clinician Assistant's backend routes (`/assistant/drafts`, `/assistant/apply`) don't have a file yet; adding one
is on the checklist.

## Run the frontend

```
cd frontend
npm install
npm run dev        # http://localhost:5173 (patient app at /patient/, dashboard at /clinician/)
npm run build      # writes frontend/dist for FastAPI to serve
```

Needs Node 20.19 or newer. It runs on in-browser sample data by default. Add `?mock=0` to a URL to call FastAPI on
port 8000 instead (Vite forwards `/api` to it).

### Sign-in details

Every person, hospital and number here is invented. Texts and emails are not really sent; they appear at the top of
the screen like a phone notification.

**Patients** (`/patient/`)
- Returning patient: phone `0800 000 0101` (Zainab Musa). The PIN on the next visit is `1234`.
- New patient invited by their care team: invite code `CL-7K4Q` (Chidi Okeke).
- Family helper: invite code `CG-3M9D` (Femi Adeyemi). Any mobile number works; pick the country first.

**Care team** (`/clinician/`)
- Existing account: `ada.okafor@kestrelgeneral.ng`, password `Blue-ward-morning-24`.
- Staff invite link: `/clinician/#/join/join-7f3k`.
- New account: **Create an account**, with any email address. Choose where you work (hospital, pharmacy, clinic or
  care home), then the facility, then enter its code. Once you pick a facility, the sign-up page shows its code with an
  MVP notice.

  | Type | Care facility | Code |
  |---|---|---|
  | Hospital | Kestrel General Hospital, Abuja, Nigeria | `KGH-4821` |
  | Hospital | Egret Teaching Hospital, Ibadan, Nigeria | `ETH-3067` |
  | Hospital | Hornbill Specialist Hospital, Kano, Nigeria | `HSH-5914` |
  | Hospital | Weaverbird Medical Centre, Enugu, Nigeria | `WMC-2738` |
  | Hospital | Heron Bay General Hospital, Lagos, Nigeria | `HBG-6409` |
  | Pharmacy | Sunbird Pharmacy, Abuja, Nigeria | `SBP-1956` |
  | Clinic or health centre | Ibis Family Clinic, Accra, Ghana | `IFC-4173` |
  | Care home | Kingfisher Care Home, Nairobi, Kenya | `KCH-8352` |

  Facility codes are for staff only. The sample patients move to the signed-in person's facility.

**Clinician Assistant:** open it from the **Assistant** button (bottom right) or **Ask the assistant** on a patient
page. You can type or speak; voice needs Chrome or Edge. For example: "Book Grace a diabetes review next Tuesday at 9:30 in
the Diabetes Clinic."

**Presenter mode:** add `?presenter=1` to any URL to show these details on screen, along with tools to reset the walkthrough
and play an incoming Tomi call. `?presenter=0` hides them again.

## Backend setup

Copy `.env.example` to `.env` and fill it in. Never commit `.env`. The keys, and where to get them, are in section 1
of [docs/launch-checklist.md](docs/launch-checklist.md). Python packages are in `requirements.txt`.

Run the backend from `backend/`:

```
uvicorn app.main:app --port 8000      # one process only; then open the frontend with ?mock=0
python -m pytest tests                # no keys needed: email, LiveKit and the model are mocked
```

An empty database gets the sample facility on first start (Dr. Ada Okafor, `ada.okafor@kestrelgeneral.ng`,
`Blue-ward-morning-24`; patients sign in with an emailed code, PIN `1234`). Without SMTP settings, emails and their
codes are printed in the backend log. The Vite dev server proxies `/api` to port 8000; after `npm run build` the
backend also serves `frontend/dist`. On a host, run `uvicorn app.main:app --host 0.0.0.0 --port $PORT` from
`backend/` with `DATABASE_URL` pointing at Postgres, and set `CARELOOP_DEMO=0` before real patients use it.

## Team preview (Vercel)

Import the GitHub repo into Vercel and set **Root Directory** to `frontend`. `frontend/vercel.json` does the rest
(`npm ci`, `npm run build`, serves `dist`). The preview runs on in-browser data only, so it needs no backend or
secrets. It is marked `noindex`.

## Branches

`feat/care-plan-verifier` (Mary), `feat/checkin-escalation` (Dorcas),
`feat/backend-notifications` (Olamide), `feat/tomi-voice-frontend` (Nunsi).
Protect `main` and keep PRs small and reviewed. No secrets, raw recordings or real patient data in Git.

## Agent handoff

Each agent exposes `async def run(payload: dict) -> dict` and returns proposals only. Each one ships with unit tests in
`backend/tests/` and a notebook in `notebooks/`. All agents use one shared Groq client, so the model can be changed in
one place (`GROQ_MODEL`).
