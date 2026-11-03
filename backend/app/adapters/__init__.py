"""Provider adapters. Each send returns a SendResult, so the notification service can retry or record a failure."""

from dataclasses import dataclass


@dataclass
class SendResult:
    ok: bool
    provider_id: str | None = None   # the provider's message id, matched later against delivery reports
    error: str | None = None
    retryable: bool = False          # True for timeouts and dropped connections; False for a refused address
