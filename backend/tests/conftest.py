"""Test settings: a fresh SQLite file per test, no scheduler, no real email, LiveKit or Groq calls."""

import os
import re

import pytest

# Set before app.main loads .env, which never overrides variables that already exist.
os.environ.update({
    "CARELOOP_SCHEDULER": "0", "CARELOOP_DEMO": "1", "CARELOOP_DISABLE_RATE_LIMITS": "1", "EMAIL_PROVIDER": "console",
    "VOICE_SERVICE_TOKEN": "test-worker-token", "GROQ_API_KEY": "mock_key_for_testing", "APP_URL": "http://localhost:5173",
    "LIVEKIT_URL": "", "LIVEKIT_API_KEY": "", "LIVEKIT_API_SECRET": "", "LIVEKIT_SIP_TRUNK_ID": "", "SMS_PROVIDER": "",
})


class Mailbox:
    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, to, subject, text):
        from app.adapters import SendResult
        self.sent.append({"to": to, "subject": subject, "text": text})
        return SendResult(ok=True, provider_id=f"<m{len(self.sent)}@test>")

    def last_code(self, to: str | None = None) -> str:
        for mail in reversed(self.sent):
            if to is None or mail["to"] == to:
                return re.search(r"\b(\d{6})\b", mail["text"]).group(1)
        raise AssertionError(f"no email to {to}")


@pytest.fixture
def mailbox(monkeypatch):
    box = Mailbox()
    from app.adapters import email
    from app.services import identity, notifications
    for module in (email, identity, notifications):
        monkeypatch.setattr(module, "send_email", box.send)
    return box


@pytest.fixture
def client(tmp_path, monkeypatch, mailbox):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client
