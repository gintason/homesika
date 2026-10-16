"""Payment gateway interface. Business code talks only to this; adapters translate to each provider."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

import requests

logger = logging.getLogger(__name__)
TIMEOUT = (5, 30)


class GatewayError(Exception):
    """The provider rejected the request or was unreachable."""

    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = True):
        super().__init__(message)
        self.status_code, self.retryable = status_code, retryable


@dataclass
class CheckoutRequest:
    reference: str
    amount: int  # minor units
    currency: str
    email: str
    phone: str
    name: str
    callback_url: str
    subaccount_code: str
    platform_fee: int  # minor units kept by Homesika (0 = everything settles to the landlord)
    description: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class Checkout:
    url: str
    gateway_reference: str


@dataclass
class VerifiedTransaction:
    status: str  # "success" | "failed" | "pending"
    reference: str
    amount: int  # minor units actually paid
    currency: str
    channel: str = ""
    gateway_fee: int = 0
    paid_at: datetime | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class WebhookEvent:
    event_id: str
    event_type: str
    reference: str


class PaymentGateway(Protocol):
    name: str

    def create_subaccount(self, *, business_name: str, bank_code: str, account_number: str) -> str: ...

    def initialize(self, req: CheckoutRequest) -> Checkout: ...

    def verify(self, reference: str) -> VerifiedTransaction: ...

    def verify_signature(self, raw_body: bytes, headers) -> bool: ...

    def parse_webhook(self, payload: dict) -> WebhookEvent | None: ...


def http(method: str, url: str, *, headers: dict, json=None, params=None, provider: str) -> dict:
    """One HTTP call with timeouts; never logs secrets or full payloads."""
    try:
        resp = requests.request(method, url, headers=headers, json=json, params=params, timeout=TIMEOUT)
    except requests.Timeout as exc:
        raise GatewayError(f"{provider} timed out") from exc
    except requests.RequestException as exc:
        raise GatewayError(f"{provider} unreachable: {type(exc).__name__}") from exc
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code >= 400:
        message = (body.get("message") if isinstance(body, dict) else "") or f"HTTP {resp.status_code}"
        logger.warning("%s %s -> %s: %s", provider, url.split("?")[0], resp.status_code, message)
        raise GatewayError(
            f"{provider}: {message}",
            status_code=resp.status_code,
            retryable=resp.status_code >= 500 or resp.status_code == 429,
        )
    return body
