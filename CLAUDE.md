# CareLoop AI

## Frontend rules

- The frontend is React + Vite in `frontend/` (decided by Nunsi, 30 Oct 2026; replaces the plain HTML/JS rule). Run `npm run dev` there; `npm run build` writes `frontend/dist/`, which FastAPI serves as static files. The team preview is deployed to Vercel from `vercel.json` at the repo root (mock data only). Both apps use hash routing, so no server rewrites are needed.
- `frontend/_legacy/` is the old plain HTML/JS version, kept for reference only. Do not edit it or import from it.
- Structure: `index.html` + `landing.jsx` (landing), `patient/` (patient app), `clinician/` (dashboard), `shared/` (API, mocks, tokens, shared components). Ask Nunsi before adding a new page, a top-level folder, or an npm dependency.
- Define all colours, spacing, radii and fonts as CSS variables in `shared/tokens.css`. Do not use hex or rgb colour values in any other file (the only exception is `public/favicon.svg`).
- Route every network call through `shared/api.js`; components must never call `fetch` directly.
- `shared/api.js` must provide a `USE_MOCKS` flag (on by default, `?mock=0` turns it off). Mock responses live in `shared/mock-server.js` and must follow `docs/api_shapes.md`, which follows section 11 of the project documentation v2.
- Build the patient app mobile-first, beginning at 360px. Build the dashboard desktop-first, beginning at 1280px. Check 360, 768 and 1280.
- Meet accessibility requirements: semantic HTML, a label for every input, a visible focus ring, 4.5:1 text contrast, tap targets at least 44px, keyboard use for chat, dialogs and the voice sheet, and a focus trap in every dialog.
- The UI must never write medical content. Clinical text, including everything Tomi says, may come only from the API (or its mock).
- Use red only for red flags and open escalations.
- MVP languages are Hausa, Yoruba, Igbo and plain English. Pidgin is removed. Show a Beta chip wherever a language that has not passed native-speaker validation is named (`shared/languages.js`).
- Patient-language text (Tomi's lines, patient quotes) uses Noto Sans, because the display face (Bricolage Grotesque) lacks Hausa hooked letters.
- Purple is the brand colour (aubergine surfaces, royal purple actions). Marigold belongs only to Tomi.
- Sign-in: patients use phone number + 6-digit code (SMS or voice call), then a 4-digit PIN on a remembered phone; caregivers join by invite code. Staff use email + password + a 6-digit code by email (no authenticator apps, no backup codes). Staff join by invite link, or sign up with any email address plus their hospital and that hospital's join code; no hospital is hard-coded in the UI. Never show whether an account exists on sign-in or reset screens. Auth calls go through `shared/api.js` like everything else; the mock lives in `shared/mock-auth.js`.
- Every patient screen ends with: "This is an AI assistant. If you feel very unwell, go to the nearest hospital now."
- All sample data must be fake, but must read naturally: no "demo", "fictional", "fake", "example" or "prototype" on screen. The invented hospitals are Kestrel General (Abuja, the default), Egret Teaching (Ibadan), Hornbill Specialist (Kano), Weaverbird Medical Centre (Enugu) and Heron Bay General (Lagos); their staff join codes live in `shared/mock-auth.js`. The real backend must never return them; the mock returns `demo_join_code` so the sign-up screen can show the chosen hospital's code with an MVP notice saying that in real use the hospital gives it out. This notice is the one agreed exception to the no-MVP-wording rule, and it disappears with `?mock=0`. The sample patients follow the signed-in staff member's hospital (`setMockFacility`).
- Bump `AUTH_KEY` in `shared/mock-auth.js` or `STORAGE_KEY` in `shared/mock-server.js` whenever seeded accounts or data change shape, so browsers drop stale saved copies.
- The dashboard assistant (`clinician/Assistant.jsx`) drafts changes from a clinician's typed or spoken instruction; nothing is saved until the clinician confirms. It may only use what the clinician said: never invent a medicine, dose, time or place, flag anything missing as an issue, and block texts or calls the patient has not consented to. Voice input uses the browser's speech recognition (`en-NG`), with no extra dependency.
- Walkthrough help (credentials, reset, simulated calls) goes behind presenter mode (`shared/presenter.js`, `?presenter=1`), never on the default screen.
- SMS and email reminders are generic templates from the API. They never name a medicine, condition or test, and patients can turn each channel off themselves.
