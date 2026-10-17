"""
Paystack adapter.

Known from Goldia's integration: POST /transaction/initialize, GET /transaction/verify/{reference},
webhook header x-paystack-signature = HMAC-SHA512(raw body, secret key), amounts in kobo.

TODO(verify) against Paystack's current docs before going live:
* subaccount creation (POST /subaccount) field names and the settlement-bank fields;
* split on initialize: `subaccount`, `transaction_charge` (flat fee to the main account, kobo) and `bearer`;
* that settlement to the subaccount is direct to the landlord's bank (written confirmation, ADR-0002).
"""

import hashlib
import hmac
from datetime import datetime

from django.conf import settings

from .base import Checkout, CheckoutRequest, GatewayError, VerifiedTransaction, WebhookEvent, http


class PaystackGateway:
    name = "paystack"

    def __init__(self):
        self.base = settings.PAYSTACK_BASE_URL.rstrip("/")
        self.secret = settings.PAYSTACK_SECRET_KEY

    def _headers(self):
        return {"Authorization": f"Bearer {self.secret}", "Content-Type": "application/json"}

    def create_subaccount(self, *, business_name: str, bank_code: str, account_number: str) -> str:
        body = http(
            "POST",
            f"{self.base}/subaccount",
            headers=self._headers(),
            provider=self.name,
            json={
                "business_name": business_name,  # TODO(verify)
                "settlement_bank": bank_code,  # TODO(verify)
                "account_number": account_number,  # TODO(verify)
                "percentage_charge": 0,  # TODO(verify): fee is set per transaction instead
            },
        )
        code = (body.get("data") or {}).get("subaccount_code")  # TODO(verify)
        if not code:
            raise GatewayError("paystack: no subaccount code returned", retryable=False)
        return code

    def initialize(self, req: CheckoutRequest) -> Checkout:
        payload = {
            "email": req.email,
            "amount": req.amount,
            "currency": req.currency,
            "reference": req.reference,
            "callback_url": req.callback_url,
            "metadata": {**req.metadata, "description": req.description},
        }
        if req.subaccount_code:  # rent and dues: settle to the landlord's subaccount
            payload.update(
                {
                    "subaccount": req.subaccount_code,  # TODO(verify)
                    "transaction_charge": req.platform_fee,  # TODO(verify): flat kobo to Homesika's account
                    "bearer": "subaccount",  # TODO(verify): landlord bears Paystack's fee
                }
            )
        body = http(
            "POST",
            f"{self.base}/transaction/initialize",
            headers=self._headers(),
            json=payload,
            provider=self.name,
        )
        data = body.get("data") or {}
        if not data.get("authorization_url"):
            raise GatewayError("paystack: no checkout url returned", retryable=False)
        return Checkout(
            url=data["authorization_url"], gateway_reference=data.get("reference") or req.reference
        )

    def verify(self, reference: str) -> VerifiedTransaction:
        body = http(
            "GET", f"{self.base}/transaction/verify/{reference}", headers=self._headers(), provider=self.name
        )
        data = body.get("data") or {}
        status = {"success": "success", "failed": "failed", "abandoned": "failed", "reversed": "failed"}.get(
            data.get("status"), "pending"
        )
        paid_at = data.get("paid_at") or data.get("paidAt")
        return VerifiedTransaction(
            status=status,
            reference=data.get("reference") or reference,
            amount=int(data.get("amount") or 0),
            currency=data.get("currency") or "",
            channel=data.get("channel") or "",
            gateway_fee=int(data.get("fees") or 0),
            paid_at=datetime.fromisoformat(paid_at.replace("Z", "+00:00")) if paid_at else None,
            raw={
                k: data.get(k)
                for k in (
                    "id",
                    "status",
                    "reference",
                    "amount",
                    "currency",
                    "channel",
                    "fees",
                    "paid_at",
                    "gateway_response",
                )
            },
        )

    def refund(self, reference: str, amount: int) -> str:
        """Refund a transaction (bills that couldn't be delivered). TODO(verify) POST /refund fields."""
        body = http(
            "POST",
            f"{self.base}/refund",
            headers=self._headers(),
            json={"transaction": reference, "amount": amount},
            provider=self.name,
        )
        data = body.get("data") or {}
        return str(data.get("id") or data.get("reference") or reference)

    def verify_signature(self, raw_body: bytes, headers) -> bool:
        given = headers.get("x-paystack-signature", "")
        expected = hmac.new(self.secret.encode(), raw_body, hashlib.sha512).hexdigest()
        return bool(self.secret) and hmac.compare_digest(given, expected)

    def parse_webhook(self, payload: dict) -> WebhookEvent | None:
        data = payload.get("data") or {}
        reference = data.get("reference")
        if not reference:
            return None
        return WebhookEvent(
            event_id=f"{payload.get('event')}:{data.get('id') or reference}",
            event_type=payload.get("event", ""),
            reference=reference,
        )
