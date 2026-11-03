"""Hashing for passwords, PINs and one-time codes, session tokens, and simple rate limits (stdlib only).

- Passwords and PINs: scrypt with a random salt per secret.
- One-time codes: HMAC-SHA256 with CODE_PEPPER, so a database copy does not reveal live codes.
- Session cookies hold a random token; the database keeps only its SHA-256, so a database copy cannot sign anyone in.
"""

import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque

from app.util import ApiError

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def hash_secret(secret: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(secret.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_secret(secret: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt, digest = stored.split("$")
    candidate = hashlib.scrypt(str(secret).encode(), salt=bytes.fromhex(salt), **_SCRYPT)
    return hmac.compare_digest(candidate.hex(), digest)


def _pepper() -> bytes:
    return (os.getenv("CODE_PEPPER") or os.getenv("SESSION_SECRET") or "careloop-local-only").encode()


def hash_code(code: str) -> str:
    return hmac.new(_pepper(), str(code).encode(), hashlib.sha256).hexdigest()


def check_code(code: str, stored: str | None) -> bool:
    return bool(stored) and hmac.compare_digest(hash_code(code), stored)


def new_session_token() -> tuple[str, str]:
    """(token for the cookie, key to store)."""
    raw = secrets.token_urlsafe(32)
    return raw, session_key(raw)


def session_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# In-memory sliding-window limits (one backend process). Keyed by route and client address or account.
_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(key: str, limit: int, per_seconds: int, message: str = "Too many attempts. Wait a minute, then try again.") -> None:
    if os.getenv("CARELOOP_DISABLE_RATE_LIMITS") == "1":
        return
    window, stamp = _hits[key], time.monotonic()
    while window and stamp - window[0] > per_seconds:
        window.popleft()
    if len(window) >= limit:
        raise ApiError(message, 429)
    window.append(stamp)


def reset_rate_limits() -> None:
    _hits.clear()


COMMON_PASSWORDS = {"password", "password1", "password123", "123456789012", "careloop123", "qwertyuiop", "iloveyou",
                    "nigeria123", "lagos12345", "welcome123"}


def password_problem(password: str | None, email: str = "") -> str | None:
    """NIST SP 800-63B style: length, not common, not the email. Same messages as the app."""
    if not password or len(password) < 12:
        return "Use at least 12 characters."
    if len(password) > 128:
        return "Use 128 characters or fewer."
    if password.lower() in COMMON_PASSWORDS:
        return "That password is too common. Try a short phrase only you would know."
    local = (email.split("@")[0] if email else "").lower()
    if len(local) > 3 and local in password.lower():
        return "Do not use your email address in your password."
    return None
