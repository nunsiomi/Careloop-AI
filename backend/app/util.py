"""Small helpers shared by the services and routes: ids, times, masking, phone numbers and API errors."""

import re
import secrets
from datetime import datetime, timedelta, timezone


class ApiError(Exception):
    """An error the frontend shows as-is: `detail` is plain language for the person using the app."""

    def __init__(self, detail: str, status: int = 400, **extra):
        super().__init__(detail)
        self.detail, self.status, self.extra = detail, status, extra


def not_found(what: str) -> ApiError:
    return ApiError(f"{what} was not found.", 404)


def make_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(5)}"


def token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(18)}"


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime | None = None) -> str:
    """ISO 8601 in UTC with milliseconds and Z, the same format as JavaScript's toISOString()."""
    moment = (moment or now()).astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def now_iso() -> str:
    return iso()


def in_seconds(seconds: float) -> str:
    return iso(now() + timedelta(seconds=seconds))


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def six_digits() -> str:
    return f"{secrets.randbelow(900000) + 100000}"


def first_name(name: str) -> str:
    return name.split(" ")[0]


# Same table and rules as frontend/shared/format.js, so the app and the backend agree on every number.
PHONE_COUNTRIES = [("234", 10), ("233", 9), ("254", 9), ("27", 9), ("256", 9), ("250", 9), ("237", 9), ("44", 10), ("1", 10)]
_BY_DIAL = sorted(PHONE_COUNTRIES, key=lambda item: -len(item[0]))


def mask_phone(e164: str | None) -> str:
    if not e164:
        return ""
    dial = next((code for code, _ in _BY_DIAL if e164[1:].startswith(code)), e164[1:4])
    return f"+{dial} ••• ••• {e164[-4:]}"


def mask_email(email: str | None) -> str:
    if not email or "@" not in email:
        return ""
    local, domain = email.split("@", 1)
    return f"{local[0]}{'•' * min(len(local) - 1, 6)}@{domain}"


def normalize_phone(phone: str | None) -> str | None:
    """'+234 0803 123 4567', '0803 123 4567' or '+44 7400 123456' -> E.164, or None. Same rules as shared/format.js."""
    text = str(phone or "").strip()
    digits = re.sub(r"\D", "", text)
    if not text.startswith("+"):
        if digits.startswith("234") and len(digits) == 13:
            return f"+{digits}"
        if digits.startswith("0") and len(digits) == 11:
            return f"+234{digits[1:]}"
        if len(digits) == 10 and digits[0] in "789":
            return f"+234{digits}"
        return None
    country = next(((code, size) for code, size in _BY_DIAL if digits.startswith(code)), None)
    if not country:
        return f"+{digits}" if 8 <= len(digits) <= 15 else None
    national = re.sub(r"^0", "", digits[len(country[0]):])
    return f"+{country[0]}{national}" if len(national) == country[1] else None


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
