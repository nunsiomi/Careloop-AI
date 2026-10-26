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

## Branches
`feat/care-plan-verifier` (Mary), `feat/checkin-escalation` (Dorcas),
`feat/backend-notifications` (Olamide), `feat/tomi-voice-frontend` (Nunsi).
Protect `main`; small reviewed PRs. No secrets, raw recordings or real patient data in Git.

## Agent handoff
Each agent exposes `async def run(payload: dict) -> dict`, returns proposals only, ships with
unit tests in `backend/tests/` and a notebook in `notebooks/`.
