"""
Flutterwave Bills (v3), the failover provider; adapted from Goldia's client. It pays from Homesika's
Flutterwave balance. Codes per biller/plan go in provider_codes["flutterwave"] = {"type": <biller_name>,
"item_code": ..., "biller_code": ...} (set in the admin after checking Flutterwave's bill categories).

TODO(verify) against Flutterwave's current docs before enabling: POST /bills body (country, customer,
amount, recurrence, type, reference), GET /bills/{reference} status values and where tokens appear, and
GET /bill-items/{item_code}/validate.
"""

from django.conf import settings

from apps.core.money import to_major

from .base import DELIVERED, FAILED, PROCESSING, ProviderError, Result, classify, http


class FlutterwaveBills:
    name = "flutterwave"

    def __init__(self):
        self.base = settings.FLUTTERWAVE_BASE_URL.rstrip("/")
        self.headers = {"Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}"}

    def _codes(self, order_or_biller, plan=None) -> dict:
        biller = getattr(order_or_biller, "biller", order_or_biller)
        plan = plan if plan is not None else getattr(order_or_biller, "plan", None)
        codes = dict(biller.provider_codes.get("flutterwave") or {})
        if plan is not None:
            codes.update(plan.provider_codes.get("flutterwave") or {})
        return codes

    def supports(self, biller, plan) -> bool:
        return bool(self._codes(biller, plan).get("type")) and bool(settings.FLUTTERWAVE_SECRET_KEY)

    def verify_customer(self, biller, plan, customer_id: str) -> dict:
        c = self._codes(biller, plan)
        body = http(
            "GET",
            f"{self.base}/bill-items/{c.get('item_code', '')}/validate",
            provider=self.name,
            headers=self.headers,
            params={"code": c.get("biller_code", ""), "customer": customer_id},
        )
        data = body.get("data") or {}
        return {"name": data.get("name") or "", "details": {}}

    def purchase(self, order, request_id: str) -> Result:
        c = self._codes(order)
        try:
            body = http(
                "POST",
                f"{self.base}/bills",
                provider=self.name,
                headers=self.headers,
                json={
                    "country": "NG",
                    "customer": order.customer_id,
                    "amount": float(to_major(order.amount, order.currency)),
                    "recurrence": "ONCE",
                    "type": c["type"],
                    "reference": request_id,
                },
            )
        except ProviderError as exc:
            return Result(outcome=classify(exc), message=str(exc)[:200])
        data = body.get("data") or {}
        return Result(outcome=PROCESSING, reference=str(data.get("flw_ref") or request_id), raw=data)

    def requery(self, order, request_id: str) -> Result:
        try:
            body = http("GET", f"{self.base}/bills/{request_id}", provider=self.name, headers=self.headers)
        except ProviderError as exc:
            if exc.status_code == 404:
                return Result(outcome="not_found")
            return Result(outcome="unknown", message=str(exc)[:200])
        data = body.get("data") or {}
        status = str(data.get("status") or "").lower()
        if status in ("successful", "success"):
            extra = data.get("extra") or ""
            return Result(
                outcome=DELIVERED, reference=str(data.get("flw_ref") or ""), token=str(extra)[:200], raw=data
            )
        if status == "failed":
            return Result(
                outcome=FAILED, message=str(data.get("response_message") or "failed")[:200], raw=data
            )
        return Result(outcome=PROCESSING, raw=data)
