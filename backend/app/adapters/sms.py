"""SMS provider adapter (mockable).

Not live: CareLoop has no SMS provider yet, so reminders and sign-in codes go by email (decided by Nunsi,
3 Nov 2026). Once Africa's Talking or Termii is set up, fill in SMS_PROVIDER, SMS_API_KEY and SMS_SENDER_ID,
implement send_sms, and SMS joins the reminder channels automatically (services/notifications.py).
"""

import os

from app.adapters import SendResult


SMS_READY = False  # set to True once send_sms really sends


def sms_available() -> bool:
    return SMS_READY and bool(os.getenv("SMS_PROVIDER") and os.getenv("SMS_API_KEY"))


async def send_sms(to_e164: str, text: str) -> SendResult:
    return SendResult(ok=False, error="SMS is not set up yet")
