"""Email provider adapter (SMTP: a Gmail app password or Brevo; mockable).

Email is CareLoop's live channel for reminders and patient sign-in codes until there is an SMS provider
(decided by Nunsi, 3 Nov 2026). EMAIL_PROVIDER=console prints messages instead of sending them, for local runs.
"""

import asyncio
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid

from app.adapters import SendResult

log = logging.getLogger("careloop.email")


def email_provider() -> str:
    """'smtp' when SMTP is configured, otherwise 'console'. EMAIL_PROVIDER overrides."""
    chosen = (os.getenv("EMAIL_PROVIDER") or "").strip().lower()
    if chosen:
        return chosen
    return "smtp" if os.getenv("SMTP_HOST") else "console"


def _message(to: str, subject: str, text: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = os.getenv("EMAIL_FROM") or "CareLoop <no-reply@careloop.app>"
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


async def send_email(to: str, subject: str, text: str) -> SendResult:
    """Send one plain-text email. Never raises: failures come back as SendResult(ok=False)."""
    message = _message(to, subject, text)
    provider = email_provider()
    if provider == "console":
        log.info("Email (not sent, EMAIL_PROVIDER=console) to %s: %s\n%s", to, subject, text)
        return SendResult(ok=True, provider_id=message["Message-ID"])
    if provider != "smtp":
        return SendResult(ok=False, error=f"Unknown EMAIL_PROVIDER {provider!r}")
    try:
        await asyncio.to_thread(_send_smtp, message)
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as error:
        return SendResult(ok=False, error=f"Address refused: {error}")
    except smtplib.SMTPAuthenticationError:
        return SendResult(ok=False, error="The email account rejected the SMTP user or password")
    except (smtplib.SMTPException, OSError) as error:  # dropped connection, timeout, server busy
        return SendResult(ok=False, error=f"Email not sent: {error}", retryable=True)
    return SendResult(ok=True, provider_id=message["Message-ID"])
