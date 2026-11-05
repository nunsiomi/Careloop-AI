"""Termii adapter: text messages, sign-in codes by phone call and sign-in codes by email (mockable).

- SMS (POST /api/sms/send): any short text, so it carries sign-in codes and the generic reminder templates.
  Uses the DND route by default (TERMII_SMS_CHANNEL): Termii's generic route is for promotions, misses numbers
  on Nigeria's DND list and MTN numbers between 20:00 and 08:00. Ask Termii support to switch DND on.
- Voice Call (POST /api/sms/otp/call) and Email Token (POST /api/email/otp/send): Termii only allows one-time
  codes on these, never free text, so reminders, invites and reset links still go by SMTP (adapters/email.py).
  The email's wording is the template set up under the email OTP config on the Termii dashboard.

We always send our own code, so hashing, expiry and wrong-try limits stay in services/identity.py; Termii's
Verify Token API is not used. Every send is paid from the Termii wallet, not the Engage subscription.

TERMII_API_KEY and TERMII_BASE_URL come from the Termii dashboard. VOICE_CODE_PROVIDER=console prints voice
codes instead of calling, for local runs.
"""

import logging
import os

import httpx

from app.adapters import SendResult

log = logging.getLogger("careloop.termii")


def termii_configured() -> bool:
    return bool(os.getenv("TERMII_API_KEY") and os.getenv("TERMII_BASE_URL"))


async def _post(path: str, body: dict) -> SendResult:
    """POST to Termii and turn the answer into a SendResult. Never raises, never logs the body (it holds the key)."""
    url = os.environ["TERMII_BASE_URL"].rstrip("/") + path
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.post(url, json={"api_key": os.environ["TERMII_API_KEY"], **body})
    except httpx.HTTPError as error:  # timeout or dropped connection
        return SendResult(ok=False, error=f"Termii unreachable: {type(error).__name__}", retryable=True)

    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code >= 500:
        return SendResult(ok=False, error=f"Termii error {response.status_code}", retryable=True)
    if response.status_code >= 400 or str(data.get("code", "ok")).lower() != "ok":
        # 4xx: bad key, empty wallet, sender ID not approved, number refused. Retrying will not help.
        return SendResult(ok=False, error=f"Termii refused the message ({response.status_code}): {data.get('message') or response.text[:200]}")
    return SendResult(ok=True, provider_id=str(data.get("message_id_str") or data.get("message_id") or data.get("pinId") or ""))


# ----- SMS

def sms_ready() -> bool:
    return termii_configured() and bool(os.getenv("SMS_SENDER_ID"))


async def send_sms(to_e164: str, text: str) -> SendResult:
    return await _post("/api/sms/send", {"to": to_e164.lstrip("+"), "from": os.environ["SMS_SENDER_ID"], "sms": text,
                                         "type": "plain", "channel": os.getenv("TERMII_SMS_CHANNEL") or "dnd"})


# ----- sign-in codes by phone call

def voice_code_provider() -> str:
    """'termii' when Termii is configured, otherwise ''. VOICE_CODE_PROVIDER overrides (e.g. 'console')."""
    chosen = (os.getenv("VOICE_CODE_PROVIDER") or "").strip().lower()
    if chosen:
        return chosen
    return "termii" if termii_configured() else ""


def voice_codes_available() -> bool:
    return voice_code_provider() in ("termii", "console")


async def call_code(to_e164: str, code: str) -> SendResult:
    """Ring one number and read out a 4-8 digit code."""
    provider = voice_code_provider()
    if provider == "console":
        log.info("Voice code (not called, VOICE_CODE_PROVIDER=console) to %s: %s", to_e164, code)
        return SendResult(ok=True, provider_id="console")
    if provider != "termii":
        return SendResult(ok=False, error="Codes by phone call are not set up")
    return await _post("/api/sms/otp/call", {"phone_number": to_e164.lstrip("+"), "code": int(code)})


# ----- sign-in codes by email

def email_codes_ready() -> bool:
    return termii_configured() and bool(os.getenv("TERMII_EMAIL_CONFIG_ID"))


async def email_code(to: str, code: str) -> SendResult:
    return await _post("/api/email/otp/send", {"email_address": to, "code": code,
                                               "email_configuration_id": os.environ["TERMII_EMAIL_CONFIG_ID"]})
