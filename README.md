# CareLoop AI

Tomi: multilingual (Hausa, Yoruba, Igbo, English fallback) patient follow-through assistant.
Rules-gated multi-agent system; clinicians approve every care plan. Synthetic data only.

Team: Dorcas, Nunsi, Olamide, Mary. Full reference: `docs/source/`.

## Layout
- `backend/` FastAPI app, six agents, safety, services, adapters, tests (Olamide)
- `voice/` Tomi LiveKit worker and call controller (Nunsi)
- `frontend/` patient, clinician, shared UI (Nunsi)
- `data/` synthetic patients, sample discharge notes, fake resources
- `notebooks/` agent experiments only; production imports `backend/app/agents/*.py`
- `docs/` architecture, API contract, safety review, demo script

## Frontend (React + Vite)
```
cd frontend
npm install
npm run dev        # http://localhost:5173 (patient app at /patient/, dashboard at /clinician/)
npm run build      # writes frontend/dist for FastAPI to serve
```
Walkthrough accounts (in-browser data only; every person, hospital and number is invented):
- Patient: phone `0800 000 0101` (Zainab), PIN `1234`. The sign-in code arrives as a text at the top of the screen. Invite codes `CL-7K4Q` (new patient) and `CG-3M9D` (family helper).
- Care team: `ada.okafor@kestrelgeneral.ng` / `Blue-ward-morning-24`. The sign-in code arrives as an email at the top of the screen.
  Staff invite: `/clinician/#/join/join-7f3k`.
- New care-team accounts: `/clinician/#/sign-up` with any email address, a hospital, and that hospital's code:
  Kestrel General `KGH-4821`, Egret Teaching `ETH-3067`, Hornbill Specialist `HSH-5914`, Weaverbird Medical Centre `WMC-2738`,
  Heron Bay General `HBG-6409`. Give judges the code for one hospital. The sample patients move to the signed-in person's hospital.
- Assistant (dashboard, bottom right or "Ask the assistant" on a patient page): type or speak an instruction such as
  "Book Grace a diabetes review next Tuesday at 9:30 in the Diabetes Clinic". It drafts changes; nothing is saved until you confirm.
- Presenter mode: add `?presenter=1` to any URL to show these details on each screen, plus tools to reset the walkthrough
  and play an incoming call. `?presenter=0` hides them again. Nobody else sees them.

Click-through for teammates and judges: `docs/demo-script.md`.

Runs on in-browser mock data by default. Add `?mock=0` to a URL to call FastAPI on port 8000
(Vite proxies `/api`). API contract for the backend: `docs/api_shapes.md`.

## Team preview (Vercel)
Import the GitHub repo into Vercel and keep the defaults: `vercel.json` builds `frontend/` and serves `frontend/dist`.
The preview runs on in-browser data only, so it needs no backend or secrets. It is marked `noindex`.

## Branches
`feat/care-plan-verifier` (Mary), `feat/checkin-escalation` (Dorcas),
`feat/backend-notifications` (Olamide), `feat/tomi-voice-frontend` (Nunsi).
Protect `main`; small reviewed PRs. No secrets, raw recordings or real patient data in Git.

## Agent handoff
Each agent exposes `async def run(payload: dict) -> dict`, returns proposals only, ships with
unit tests in `backend/tests/` and a notebook in `notebooks/`.
