"""
MOCK gateway: development and tests only. It moves no money. Every checkout URL points at
/pay/<ref>/mock-checkout on the web app and every result is labelled "mock". Settings refuse to
enable it in production (see config/settings/production.py).
"""

import hashlib
import hmac
import logging
from datetime import UTC, datetime

from django.conf import settings
from django.core.cache import cache

from .base import Checkout, CheckoutRequest, VerifiedTransaction, WebhookEvent

logger = logging.getLogger(__name__)
SECRET = b"mock-gateway-signing-key-not-a-secret"


class MockGateway:
    name = "mock"

    def create_subaccount(self, *, business_name: str, bank_code: str, account_number: str) -> str:
        return f"MOCK_SUB_{account_number[-4:]}"

    def initialize(self, req: CheckoutRequest) -> Checkout:
        cache.set(
            f"mockpay:{req.reference}",
            {"amount": req.amount, "currency": req.currency, "status": "pending"},
            timeout=7 * 86400,
        )
        logger.warning("MOCK checkout created for %s (no real money)", req.reference)
        return Checkout(
            url=f"{settings.WEB_APP_URL.rstrip('/')}/pay/{req.reference}/mock-checkout",
            gateway_reference=req.reference,
        )

    @staticmethod
    def complete(reference: str, *, success: bool = True, amount: int | None = None) -> None:
        """Simulate the payer finishing checkout (used by the mock checkout page and tests)."""
        tx = cache.get(f"mockpay:{reference}") or {"amount": amount or 0, "currency": "NGN"}
        tx.update(
            status="success" if success else "failed",
            amount=amount if amount is not None else tx["amount"],
            paid_at=datetime.now(UTC).isoformat(),
        )
        cache.set(f"mockpay:{reference}", tx, timeout=7 * 86400)

    def verify(self, reference: str) -> VerifiedTransaction:
        tx = cache.get(f"mockpay:{reference}") or {"status": "pending", "amount": 0, "currency": "NGN"}
        paid_at = datetime.fromisoformat(tx["paid_at"]) if tx.get("paid_at") else None
        return VerifiedTransaction(
            status=tx["status"],
            reference=reference,
            amount=tx["amount"],
            currency=tx["currency"],
            channel="mock",
            paid_at=paid_at,
            raw={"mock": True, **tx},
        )

    def refund(self, reference: str, amount: int) -> str:
        tx = cache.get(f"mockpay:{reference}") or {}
        if tx.get("status") != "success":
            from .base import GatewayError

            raise GatewayError("mock: nothing to refund", retryable=False)
        tx.update(refunded=amount)
        cache.set(f"mockpay:{reference}", tx, timeout=7 * 86400)
        logger.warning("MOCK refund of %s for %s (no real money)", amount, reference)
        return f"MOCKREFUND-{reference}"

    def verify_signature(self, raw_body: bytes, headers) -> bool:
        expected = hmac.new(SECRET, raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(headers.get("x-mock-signature", ""), expected)

    def parse_webhook(self, payload: dict) -> WebhookEvent | None:
        ref = (payload.get("data") or {}).get("reference")
        return (
            WebhookEvent(event_id=f"mock:{ref}", event_type=payload.get("event", ""), reference=ref)
            if ref
            else None
        )
