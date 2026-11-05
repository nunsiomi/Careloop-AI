"""Email provider adapter (SMTP: a Gmail app password or Brevo; or the Gmail API over HTTPS; mockable).

Email is CareLoop's live channel for reminders and patient sign-in codes until there is an SMS provider
(decided by Nunsi, 3 Nov 2026). EMAIL_PROVIDER=console prints messages instead of sending them, for local runs.
Railway's Hobby plan blocks outbound SMTP ports, so a deploy there sends through the Gmail API over HTTPS
(EMAIL_PROVIDER=gmail, with GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET and GMAIL_REFRESH_TOKEN; see backend/gmail_token.py).
"""

import asyncio
import logging
import os
import base64
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr

import httpx

from app.adapters import SendResult

log = logging.getLogger("careloop.email")

# Invented domains of the sample facility (app/seed.py). Mail to them is printed, never sent: it would bounce
# back into the sending inbox, or reach a stranger if the domain is ever registered. Real users are unaffected.
SAMPLE_DOMAINS = {"kestrelmail.ng", "kestrelgeneral.ng"}


def email_provider() -> str:
    """'gmail' with a Gmail API refresh token, else 'smtp' when SMTP is configured, otherwise 'console'.
    EMAIL_PROVIDER overrides."""
    chosen = (os.getenv("EMAIL_PROVIDER") or "").strip().lower()
    if chosen:
        return chosen
    if os.getenv("GMAIL_REFRESH_TOKEN"):
        return "gmail"
    return "smtp" if os.getenv("SMTP_HOST") else "console"


def sender() -> tuple[str, str]:
    """(name, address) from EMAIL_FROM. Tolerates a missing <...>: "CareLoop you@gmail.com" works too."""
    raw = (os.getenv("EMAIL_FROM") or "").strip()
    name, address = parseaddr(raw)
    if " " in address or "@" not in address:  # "CareLoop you@gmail.com" parses as one odd address
        words = raw.replace("<", " ").replace(">", " ").split()
        address = next((word for word in words if "@" in word), "")
        name = " ".join(word for word in words if word != address)
    return (name or "CareLoop", address or os.getenv("SMTP_USER") or "no-reply@careloop.app")


def _message(to: str, subject: str, text: str) -> EmailMessage:
    message = EmailMessage()
    name, address = sender()
    message["From"] = f"{name} <{address}>"
    message["To"] = to
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(domain="careloop.app")
    message.set_content(text)
    return message


def _send_smtp(message: EmailMessage) -> None:
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT") or 587)
    user, password = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
    context = ssl.create_default_context()
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=15)
    with server:
        if port != 465:
            server.starttls(context=context)
        if user:
            server.login(user, password or "")
        server.send_message(message)


_gmail_token = {"value": "", "expires": 0.0}


async def _gmail_access_token(http: httpx.AsyncClient) -> str:
    """Swap the long-lived refresh token for an access token (kept until a minute before it expires)."""
    if _gmail_token["expires"] > time.time():
        return _gmail_token["value"]
    response = await http.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.getenv("GMAIL_CLIENT_ID") or "", "client_secret": os.getenv("GMAIL_CLIENT_SECRET") or "",
        "refresh_token": os.getenv("GMAIL_REFRESH_TOKEN") or "", "grant_type": "refresh_token"})
    if response.status_code >= 400:
        raise PermissionError(f"Google refused the refresh token ({response.status_code}): {response.text[:300]}")
    body = response.json()
    _gmail_token.update(value=body["access_token"], expires=time.time() + int(body.get("expires_in", 3600)) - 60)
    return _gmail_token["value"]


async def _send_gmail(message: EmailMessage) -> SendResult:
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            access = await _gmail_access_token(http)
            response = await http.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                                       json={"raw": raw}, headers={"Authorization": f"Bearer {access}"})
    except PermissionError as error:
        return SendResult(ok=False, error=str(error))
    except httpx.HTTPError as error:  # timeout or dropped connection
        return SendResult(ok=False, error=f"Email not sent: {error!r}", retryable=True)
    if response.status_code >= 400:
        if response.status_code == 401:
            _gmail_token["expires"] = 0.0
        return SendResult(ok=False, error=f"Gmail answered {response.status_code}: {response.text[:300]}",
                          retryable=response.status_code == 429 or response.status_code >= 500)
    return SendResult(ok=True, provider_id=response.json().get("id"))


async def send_email(to: str, subject: str, text: str) -> SendResult:
    """Send one plain-text email. Never raises: failures come back as SendResult(ok=False)."""
    message = _message(to, subject, text)
    provider = email_provider()
    if to.rsplit("@", 1)[-1].strip().lower() in SAMPLE_DOMAINS:
        log.info("Email (not sent, sample address) to %s: %s\n%s", to, subject, text)
        return SendResult(ok=True, provider_id=message["Message-ID"])
    if provider == "console":
        log.info("Email (not sent, EMAIL_PROVIDER=console) to %s: %s\n%s", to, subject, text)
        return SendResult(ok=True, provider_id=message["Message-ID"])
    if provider == "gmail":
        result = await _send_gmail(message)
    elif provider == "smtp":
        result = await _smtp_result(message)
    else:
        result = SendResult(ok=False, error=f"Unknown EMAIL_PROVIDER {provider!r}")
    if not result.ok:
        log.error("Email to %s (%s) failed via %s: %s", to, subject, provider, result.error)
    return result


async def _smtp_result(message: EmailMessage) -> SendResult:
    try:
        await asyncio.to_thread(_send_smtp, message)
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as error:
        return SendResult(ok=False, error=f"Address refused: {error}")
    except smtplib.SMTPAuthenticationError:
        return SendResult(ok=False, error="The email account rejected the SMTP user or password")
    except (smtplib.SMTPException, OSError) as error:  # dropped connection, timeout, server busy; Railway Hobby blocks SMTP
        return SendResult(ok=False, error=f"Email not sent: {error!r}", retryable=True)
    return SendResult(ok=True, provider_id=message["Message-ID"])
