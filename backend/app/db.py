"""SQLite connection and schema (synthetic data only).

Storage is one table of JSON records, grouped by collection (patients, plans, tasks, events and so on), so the
same code runs on SQLite locally and on hosted Postgres (DATABASE_URL) when deployed. The service keeps a working
copy in memory and `flush()` writes only the records that changed, after every request and scheduler run.
This assumes one backend process (one Uvicorn worker), which is what the MVP runs.
"""

import json
import os
from typing import Any, Callable

from sqlalchemy import Column, MetaData, String, Table, Text, create_engine, delete, insert, select

COLLECTIONS = [
    # care data (docs/api_shapes.md)
    "facilities", "patients", "plans", "tasks", "appointments", "clinic_slots", "reschedule_requests", "barriers",
    "events", "calls", "escalations", "messages", "notifications", "voice_sessions",
    # accounts and sign-in
    "staff", "staff_sessions", "staff_invites", "signups", "mfa_tokens", "resets",
    "patient_sessions", "challenges", "invites", "caregivers", "counters",
]

metadata = MetaData()
records = Table(
    "records", metadata,
    Column("collection", String(40), primary_key=True),
    Column("id", String(120), primary_key=True),
    Column("data", Text, nullable=False),
)


def database_url() -> str:
    url = os.getenv("DATABASE_URL") or "sqlite:///./careloop.db"
    for prefix in ("postgres://", "postgresql://"):  # hosts hand these out; use the psycopg 3 driver
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Store:
    def __init__(self, url: str | None = None):
        self.engine = create_engine(url or database_url(), future=True)
        metadata.create_all(self.engine)
        self.data: dict[str, list[dict]] = {name: [] for name in COLLECTIONS}
        self._saved: dict[tuple[str, str], str] = {}
        with self.engine.connect() as connection:
            for row in connection.execute(select(records)):
                if row.collection in self.data:
                    self.data[row.collection].append(json.loads(row.data))
                    self._saved[(row.collection, row.id)] = row.data

    def is_empty(self) -> bool:
        return not any(self.data.values())

    # ----- reading -----
    def all(self, collection: str) -> list[dict]:
        return self.data[collection]

    def get(self, collection: str, record_id: str | None) -> dict | None:
        return next((item for item in self.data[collection] if item.get("id") == record_id), None) if record_id else None

    def where(self, collection: str, test: Callable[[dict], bool] | None = None, **match: Any) -> list[dict]:
        return [item for item in self.data[collection] if all(item.get(key) == value for key, value in match.items()) and (test is None or test(item))]

    def first(self, collection: str, test: Callable[[dict], bool] | None = None, **match: Any) -> dict | None:
        return next(iter(self.where(collection, test, **match)), None)

    # ----- writing -----
    def add(self, collection: str, record: dict) -> dict:
        self.data[collection].append(record)
        return record

    def remove(self, collection: str, test: Callable[[dict], bool]) -> None:
        self.data[collection] = [item for item in self.data[collection] if not test(item)]

    def replace_all(self, data: dict[str, list[dict]]) -> None:
        self.data = {collection: list(data.get(collection, [])) for collection in COLLECTIONS}

    def counter(self, key: str) -> dict:
        """A small mutable record for rate limits and lockouts (for example join-code failures)."""
        record = self.get("counters", key)
        if record is None:
            record = self.add("counters", {"id": key, "count": 0, "locked_until": None})
        return record

    def flush(self) -> None:
        current: dict[tuple[str, str], str] = {}
        for name, items in self.data.items():
            for item in items:
                current[(name, str(item["id"]))] = json.dumps(item, ensure_ascii=False, sort_keys=True)
        changed = [key for key, text in current.items() if self._saved.get(key) != text]
        removed = [key for key in self._saved if key not in current]
        if not changed and not removed:
            return
        with self.engine.begin() as connection:
            for collection, record_id in changed + removed:
                connection.execute(delete(records).where(records.c.collection == collection, records.c.id == record_id))
            if changed:
                connection.execute(insert(records), [{"collection": c, "id": i, "data": current[(c, i)]} for c, i in changed])
        self._saved = current


_store: Store | None = None


def store() -> Store:
    if _store is None:
        raise RuntimeError("The store is not open yet; the app opens it at startup.")
    return _store


def set_store(value: Store | None) -> None:
    global _store
    _store = value
