# Architecture

See CareLoop AI Technical & Product Documentation v2.1, section 10.

## Frontend (as built)

```
frontend/
  index.html, landing.jsx     landing page with doors to both apps
  patient/                    patient and family-helper app (mobile first)
  clinician/                  care-team dashboard (desktop first), including Assistant.jsx
  shared/                     api.js, mocks, design tokens, shared components
  public/favicon.svg
```

- React 19 + Vite 8, multi-page build (`landing`, `patient`, `clinician`). Hash routing in both apps.
- Every network call goes through `shared/api.js`. `USE_MOCKS` is on by default. The mocks keep data in the browser's
  local storage, stand in for the backend agents, and follow `docs/api_shapes.md`. `?mock=0` sends calls to FastAPI
  under `/api`.
- Builds to `frontend/dist/`, which FastAPI serves in production. The team preview is deployed on Vercel with
  Root Directory `frontend` (`frontend/vercel.json`).

## Changes since documentation v2.1

These change the product described in the v2.1 document. The document owner should fold them into the next version.

1. **Care-team sign-in.** Email, password and a 6-digit code by email at each sign-in. No authenticator apps and no
   backup codes. The screen locks after 15 idle minutes.
2. **Care-team sign-up.** Staff can join with any email address (no hospital domain needed) if they have their
   hospital's join code, which the hospital's CareLoop admin gives out. Invite links still work.
3. **Several hospitals.** Each staff account belongs to one hospital and sees only that hospital's patients.
4. **SMS and email reminders.** Generic templates only, 30 minutes before each task and at 18:00 the evening before a
   visit, never between 21:00 and 07:00. Each channel needs the patient's consent and can be turned off by the patient.
5. **Clinician Assistant Agent (new).** The dashboard assistant turns a clinician's typed or spoken instruction into
   proposed changes: medicine or test reminders, visits, a generic text, a Tomi call, or a note. The clinician confirms
   before anything is saved, and each change is logged as clinician-verified. The agent never adds clinical detail the
   clinician did not give.
6. **Patient sign-in.** Phone number with a 6-digit code (SMS or voice call), then a 4-digit PIN on a remembered phone.
   The same PIN is used on Tomi phone calls. Family helpers join with an invite code from the patient.
