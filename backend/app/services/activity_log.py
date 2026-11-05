"""Append-only care events: who reported what, through which channel, and how it was verified (doc v2, section 9).

Events are never edited; a correction is a new event with `supersedes_event_id`.
"""

from app.db import store
from app.util import make_id, now_iso


def log_event(patient_id: str, **fields) -> dict:
    stamp = now_iso()
    event = {"id": make_id("ev"), "patient_id": patient_id, "reported_at": stamp, "recorded_at": stamp, "supersedes_event_id": None, **fields}
    return store().add("events", event)
