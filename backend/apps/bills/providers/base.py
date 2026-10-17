"""
VTU provider interface. Outcomes decide what happens to the person's money:

  delivered   the provider delivered: done.
  processing  accepted, not final: requery later (same provider).
  failed      the provider created the order and says it failed or refunded it: safe to try the next provider.
  rejected    the order was never created (bad request, float empty, auth): safe to try the next provider.
  unknown     timeout / 5xx / conflict: the order MAY exist. Requery the same provider;
              never fail over or refund.
"""

import logging
from dataclasses import dataclass, field
from typing import Protocol

import requests

logger = logging.getLogger(__name__)
TIMEOUT = (5, 40)

DELIVERED, PROCESSING, FAILED, REJECTED, UNKNOWN = "delivered", "processing", "failed", "rejected", "unknown"


class ProviderError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, payload=None, timeout: bool = False):
        super().__init__(message)
        self.status_code, self.payload, self.timeout = status_code, payload, timeout


@dataclass
class Result:
    outcome: str
    reference: str = ""
    token: str = ""
    units: str = ""
    cost: int | None = None  # what the provider charged us, kobo
    message: str = ""
    raw: dict = field(default_factory=dict)


class VtuProvider(Protocol):
    name: str

    def supports(self, biller, plan) -> bool: ...

    def verify_customer(self, biller, plan, customer_id: str) -> dict: ...

    def purchase(self, order, request_id: str) -> Result: ...

    def requery(self, order, request_id: str) -> Result: ...


def http(method: str, url: str, *, provider: str, json=None, params=None, headers=None) -> dict:
    """One call, no automatic retry (a retried POST could buy twice). Never logs payloads or secrets."""
    try:
        resp = requests.request(
            method,
            url,
            json=json,
            params=params,
            headers={"Accept": "application/json", **(headers or {})},
            timeout=TIMEOUT,
        )
    except requests.Timeout as exc:
        logger.warning("%s %s timed out", provider, url.split("?")[0])
        raise ProviderError(f"{provider} timed out", timeout=True) from exc
    except requests.RequestException as exc:
        raise ProviderError(f"{provider} unreachable: {type(exc).__name__}", timeout=True) from exc
    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text[:300]}
    if resp.status_code >= 400:
        message = (body.get("message") or body.get("code")) if isinstance(body, dict) else ""
        logger.warning("%s %s -> %s", provider, url.split("?")[0], resp.status_code)
        raise ProviderError(
            f"{provider}: {message or resp.status_code}", status_code=resp.status_code, payload=body
        )
    return body


def classify(exc: ProviderError) -> str:
    """Could the order exist? timeouts, 5xx, 409 and 429 -> unknown; other 4xx -> rejected (never created)."""
    if exc.timeout or exc.status_code is None or exc.status_code >= 500 or exc.status_code in (409, 429):
        return UNKNOWN
    return REJECTED
