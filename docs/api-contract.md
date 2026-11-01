# API Contract

Proposed routes: section 11 of the project documentation.

The routes the frontend calls today, with request and response shapes, are in [`api_shapes.md`](api_shapes.md).
It covers patients, plans, tasks, check-ins, appointments, escalations, calls, SMS and email reminders, sign-in and
accounts (patients, caregivers and staff), hospitals and join codes, and the care-team assistant. The frontend's
in-browser mock (`frontend/shared/mock-server.js`, `frontend/shared/mock-auth.js`) follows it exactly, so the backend
can replace the mock one route at a time (`?mock=0`).
