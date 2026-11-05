# Demo Script

The full Zainab Musa multi-day case is in section 16 of the project documentation. This page is the click-through
for the current frontend (React + Vite, running on in-browser data). Everything below happens in your own browser:
nothing is sent anywhere, and each person who opens the site gets their own copy of the sample patients.

Add `?presenter=1` to any URL to show sign-in details on each screen and tools to reset the walkthrough
(for example `/clinician/?presenter=1`). `?presenter=0` hides them again.

## Pages

| Page | Path | Who |
|---|---|---|
| Landing | `/` | Everyone |
| Patient app | `/patient/` | Patients and family helpers (phone first, from 360px) |
| Care-team dashboard | `/clinician/` | Doctors, nurses, pharmacists (desktop first, from 1280px) |

## Accounts

**Care team**

- Existing account: `ada.okafor@kestrelgeneral.ng`, password `Blue-ward-morning-24`. The 6-digit sign-in code
  arrives as an email notification at the top of the screen.
- New account: choose **Create an account** on the sign-in page. Any email address works. Choose where you work
  (hospital, pharmacy, clinic or care home), pick the facility and enter its code:

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

  You don't need to remember these: once you pick a facility, the sign-up page shows its code with an MVP notice
  and a **Use this code** button. Five wrong codes block sign-up for 10 minutes. The sample patients appear under the facility you chose.
- Staff invite link: `/clinician/#/join/join-7f3k` (Bisi Ola, follow-up nurse).

**Patients and family helpers**

Facility codes are for staff only. Patients and family helpers never use them; they join through their care team or the patient.

- Existing patient: phone `0800 000 0101` (Zainab Musa). The sign-in code arrives as an email at the top of the screen.
  On the next visit the phone remembers her, and the PIN is `1234`.
- New patient, invited by their care team: invite code `CL-7K4Q` (Chidi Okeke). Signs in, chooses a PIN, then agrees
  to how Tomi may contact him.
- Family helper, invited by the patient: invite code `CG-3M9D` (Femi Adeyemi, son of Tola Adeyemi). Any mobile number works
  for the helper; the phone field has a country picker. A patient can invite more helpers from **Account** in the patient app.

## Five-minute walkthrough

1. **Dashboard overview.** Sign in as Dr. Ada Okafor. "Needs you now" lists the open escalation (red), overdue
   medicines, plans to review, a reschedule request and an email that was not delivered.
2. **Approve a plan.** Patients, then Ibrahim Danjuma, then **Review plan**. Tomi drafted it from the discharge note; two
   fields need a decision. Nothing reaches the patient until it is approved.
3. **Use the assistant.** Open Grace Bassey and choose **Ask the assistant**. Type or say: "Book a diabetes review next
   Tuesday at 9:30 in the Diabetes Clinic. Note: her daughter answers the phone in the mornings." Check the drafted
   changes, then confirm. The visit and the note appear on her record.
4. **Reminders.** The Reminders page shows texts and emails that are scheduled, sent and not delivered. Texts never
   name a medicine or illness. Retry the failed one.
5. **Patient side.** Open `/patient/` and sign in as Zainab. Today shows her day as a loop. Tap Tomi to chat or talk,
   report a medicine as taken, or say the clinic is too far. With presenter mode on, the patient's **Presenter** menu
   sends a chat reminder now, and the dashboard's **Calls** page can play an incoming Tomi call from Zainab.
6. **Escalation.** In the patient chat, type something that mentions chest pain. The dashboard shows a new red
   escalation, and the patient is told to go to the nearest hospital now.
7. **Start again.** With presenter mode on, use **Presenter: start the walkthrough again** in the dashboard sidebar.

## Against the real backend

Rehearsed on 3 Nov 2026: every step above passed against the FastAPI backend with Groq switched on (the steps are
driven through the same API calls the screens make). What changes from the in-browser version:

1. Start the backend from `backend/` with `..oice\.venv\Scripts\python -m uvicorn app.main:app --port 8000`, and the
   frontend from `frontend/` with `npm run dev`. Open the pages with `?mock=0` (for example
   `http://localhost:5173/clinician/?mock=0&presenter=1`). Vite passes `/api` to port 8000.
2. Set `CARELOOP_DEMO=1` in `.env` for the presenter tools (reset, scripted calls, sample notes).
3. Sign-in codes go by real email when `SMTP_HOST` is set. Without it they are printed in the backend's terminal
   (`Email (not sent, EMAIL_PROVIDER=console)`), so keep that window visible.
4. **Start the walkthrough again** reloads the sample data and signs everyone out. Sign in again after it.
5. Timings with Groq: the assistant's draft takes about 5 seconds, and a chat reply about 8 to 9 seconds while the
   Language Agent translates it. Pause and say so rather than clicking again.
6. A chat reply can come back in English with the patient's language chosen. That is on purpose: the Language Agent's
   translation is shown only if every number and medicine name survives; otherwise the approved English is shown.
7. The browser voice sheet uses LiveKit when `LIVEKIT_URL` is set and the voice worker is running; without them it
   falls back to the scripted voice.

## What is not real yet

- No real texts, emails or calls are sent. Each one appears on screen the way a phone notification would.
- In the in-browser version, the assistant and Tomi run on simple rules, standing in for the backend agents
  (contract in `docs/api_shapes.md`). With `?mock=0` they are the real Groq agents.
- Voice typing in the dashboard assistant needs Chrome or Edge.
