"""SMS provider adapter (mockable).

Termii sends CareLoop's text messages (adapters/termii.py, 4 Nov 2026). Set SMS_PROVIDER=termii, TERMII_API_KEY,
TERMII_BASE_URL and SMS_SENDER_ID (an approved sender ID), and SMS joins the reminder channels
(services/notifications.py) and the sign-in code options (services/identity.py) automatically.
"""

import os

from app.adapters import SendResult
from app.adapters import termii


def sms_available() -> bool:
    return (os.getenv("SMS_PROVIDER") or "").strip().lower() == "termii" and termii.sms_ready()


async def send_sms(to_e164: str, text: str) -> SendResult:
    if not sms_available():
        return SendResult(ok=False, error="SMS is not set up")
    return await termii.send_sms(to_e164, text)
