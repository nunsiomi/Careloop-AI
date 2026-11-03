"""Fixed routing of agent/tool calls, context selection, idempotency, persistence (owner: Olamide).

Where each flow lives (agents return proposals only; these services decide and write):
- Plan flow, discharge note -> Care Plan Agent -> Plan Verifier -> approval -> tasks: services/plans.py
- Chat and voice turns, safety first, then task reports, barriers and reschedules: services/care.py
- Tomi worker calls (PIN, context, safety check, updates): services/voice.py
- Reminders and messages: services/outbox.py (rules in services/notifications.py), run by scheduler.py
- Clinician Assistant drafts and confirmed changes: services/assistant.py
Every request's changes are saved by the middleware in main.py (db.Store.flush).
"""
