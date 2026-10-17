"""
Flutterwave adapter (v3 API), the failover gateway.

Known from Goldia's integration: webhook header `verif-hash` must equal the dashboard secret hash.

TODO(verify) against Flutterwave's current docs before going live:
* POST /payments body (`tx_ref`, `redirect_url`, `customer`, `subaccounts` split), response `data.link`;
* GET /transactions/verify_by_reference?tx_ref=... response fields and `charged_amount` vs `amount`;
* POST /subaccounts fields; whether v4 should be used instead.
Amounts in this API are in MAJOR units (naira), unlike Paystack.
"""

import hmac
from datetime import datetime
from decimal import Decimal

from django.conf import settings

from apps.core.money import to_major, to_minor

from .base import Checkout, CheckoutRequest, GatewayError, VerifiedTransaction, WebhookEvent, http


class FlutterwaveGateway:
    name = "flutterwave"

    def __init__(self):
        self.base = settings.FLUTTERWAVE_BASE_URL.rstrip("/")
        self.secret = settings.FLUTTERWAVE_SECRET_KEY
        self.webhook_hash = settings.FLUTTERWAVE_WEBHOOK_HASH

    def _headers(self):
        return {"Authorization": f"Bearer {self.secret}", "Content-Type": "application/json"}

    def create_subaccount(self, *, business_name: str, bank_code: str, account_number: str) -> str:
        body = http(
            "POST",
            f"{self.base}/subaccounts",
            headers=self._headers(),
            provider=self.name,
            json={
                "account_bank": bank_code,  # TODO(verify)
                "account_number": account_number,  # TODO(verify)
                "business_name": business_name,  # TODO(verify)
                "split_type": "flat",  # TODO(verify)
                "split_value": 0,  # TODO(verify)
            },
        )
        code = (body.get("data") or {}).get("subaccount_id")  # TODO(verify)
        if not code:
            raise GatewayError("flutterwave: no subaccount id returned", retryable=False)
        return str(code)

    def initialize(self, req: CheckoutRequest) -> Checkout:
        payload = {
            "tx_ref": req.reference,
            "amount": str(to_major(req.amount, req.currency)),
            "currency": req.currency,
            "redirect_url": req.callback_url,
            "customer": {"email": req.email, "phonenumber": req.phone, "name": req.name},
            "customizations": {"title": "Homesika", "description": req.description[:100]},
            "meta": req.metadata,
        }
        if req.subaccount_code:
            # TODO(verify): split so the landlord's subaccount gets everything except Homesika's flat fee.
            payload["subaccounts"] = [
                {
                    "id": req.subaccount_code,
                    "transaction_charge_type": "flat_subaccount",
                    "transaction_charge": str(to_major(req.amount - req.platform_fee, req.currency)),
                }
            ]
        body = http(
            "POST", f"{self.base}/payments", headers=self._headers(), json=payload, provider=self.name
        )
        link = (body.get("data") or {}).get("link")
        if not link:
            raise GatewayError("flutterwave: no checkout link returned", retryable=False)
        return Checkout(url=link, gateway_reference=req.reference)

    def verify(self, reference: str) -> VerifiedTransaction:
        body = http(
            "GET",
            f"{self.base}/transactions/verify_by_reference",
            headers=self._headers(),
            params={"tx_ref": reference},
            provider=self.name,
        )
        data = body.get("data") or {}
        currency = data.get("currency") or "NGN"
        status = {"successful": "success", "failed": "failed", "cancelled": "failed"}.get(
            data.get("status"), "pending"
        )
        created = data.get("created_at")
        return VerifiedTransaction(
            status=status,
            reference=data.get("tx_ref") or reference,
            amount=to_minor(Decimal(str(data.get("amount") or 0)), currency),
            currency=currency,
            channel=data.get("payment_type") or "",
            gateway_fee=to_minor(Decimal(str(data.get("app_fee") or 0)), currency),
            paid_at=datetime.fromisoformat(created.replace("Z", "+00:00")) if created else None,
            raw={
                k: data.get(k)
                for k in (
                    "id",
                    "tx_ref",
                    "status",
                    "amount",
                    "currency",
                    "payment_type",
                    "app_fee",
                    "created_at",
                )
            },
        )

    def refund(self, reference: str, amount: int) -> str:
        """Refund by tx_ref: look up the transaction id, then refund it. TODO(verify) both endpoints."""
        body = http(
            "GET",
            f"{self.base}/transactions/verify_by_reference",
            headers=self._headers(),
            params={"tx_ref": reference},
            provider=self.name,
        )
        tx_id = (body.get("data") or {}).get("id")
        if not tx_id:
            raise GatewayError("flutterwave: transaction not found for refund", retryable=False)
        currency = (body.get("data") or {}).get("currency") or "NGN"
        resp = http(
            "POST",
            f"{self.base}/transactions/{tx_id}/refund",
            headers=self._headers(),
            json={"amount": str(to_major(amount, currency))},
            provider=self.name,
        )
        return str((resp.get("data") or {}).get("id") or tx_id)

    def verify_signature(self, raw_body: bytes, headers) -> bool:
        given = headers.get("verif-hash", "")
        return bool(self.webhook_hash) and hmac.compare_digest(given, self.webhook_hash)

    def parse_webhook(self, payload: dict) -> WebhookEvent | None:
        data = payload.get("data") or {}
        reference = data.get("tx_ref")
        if not reference:
            return None
        return WebhookEvent(
            event_id=f"{payload.get('event')}:{data.get('id') or reference}",
            event_type=payload.get("event", ""),
            reference=reference,
        )
