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
- New account: choose **Create an account** on the sign-in page. Any email address works. Pick a hospital and enter
  that hospital's code:

  | Hospital | Code |
  |---|---|
  | Kestrel General Hospital, Abuja | `KGH-4821` |
  | Egret Teaching Hospital, Ibadan | `ETH-3067` |
  | Hornbill Specialist Hospital, Kano | `HSH-5914` |
  | Weaverbird Medical Centre, Enugu | `WMC-2738` |
  | Heron Bay General Hospital, Lagos | `HBG-6409` |

  You don't need to remember these: once you pick a hospital, the sign-up page shows its code with an MVP notice
  and a **Use this code** button. Five wrong codes block sign-up for 10 minutes. The sample patients appear under the hospital you chose.
- Staff invite link: `/clinician/#/join/join-7f3k` (Bisi Ola, follow-up nurse).

**Patients and family helpers**

Hospital codes are for staff only. Patients and family helpers never use them; they join through the hospital or the patient.

- Existing patient: phone `0800 000 0101` (Zainab Musa). The sign-in code arrives as a text at the top of the screen.
  On the next visit the phone remembers her, and the PIN is `1234`.
- New patient, invited by the hospital: invite code `CL-7K4Q` (Chidi Okeke). Signs in, chooses a PIN, then agrees
  to how Tomi may contact him.
- Family helper, invited by the patient: invite code `CG-3M9D` (Femi Adeyemi, son of Tola Adeyemi). Any Nigerian mobile
  number works for the helper. A patient can invite more helpers from **Account** in the patient app.

## Five-minute walkthrough

1. **Dashboard overview.** Sign in as Dr. Ada Okafor. "Needs you now" lists the open escalation (red), overdue
   medicines, plans to review, a reschedule request and a text that was not delivered.
2. **Approve a plan.** Patients, then Ibrahim Danjuma, then **Review plan**. Tomi drafted it from the discharge note; two
   fields need a decision. Nothing reaches the patient until it is approved.
3. **Use the assistant.** Open Grace Bassey and choose **Ask the assistant**. Type or say: "Book a diabetes review next
   Tuesday at 9:30 in the Diabetes Clinic. Note: her daughter answers the phone in the mornings." Check the drafted
   changes, then confirm. The visit and the note appear on her record.
4. **Reminders.** The Reminders page shows texts and emails that are scheduled, sent and not delivered. Texts never
   name a medicine or illness. Retry the failed one.
5. **Patient side.** Open `/patient/` and sign in as Zainab. Today shows her day as a loop. Tap Tomi to chat or talk,
   report a medicine as taken, or say the clinic is too far. With presenter mode on, the patient menu can play an
   incoming Tomi call.
6. **Escalation.** In the patient chat, type something that mentions chest pain. The dashboard shows a new red
   escalation, and the patient is told to go to the nearest hospital now.
7. **Start again.** With presenter mode on, use **Presenter: start the walkthrough again** in the dashboard sidebar.

## What is not real yet

- No real texts, emails or calls are sent. Each one appears on screen the way a phone notification would.
- The assistant and Tomi run on simple rules in the browser, standing in for the backend agents
  (contract in `docs/api_shapes.md`).
- Voice typing in the dashboard assistant needs Chrome or Edge.
