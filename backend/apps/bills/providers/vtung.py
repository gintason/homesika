"""
VTU.ng (API v2), ported from Goldia's integration (docs: https://vtu.ng/api/).

* Auth is a 7-day JWT from POST /jwt-auth/v1/token. Only the newest token is valid, so all workers share one
  cached token and re-login is serialised behind a cache lock.
* Amounts are whole naira. Every purchase carries our request_id (max 50 chars), also used to requery.
* Webhooks: header X-Signature = hex HMAC-SHA256(body, account PIN).
"""

import hashlib
import hmac
import json
import math
import re
import time

from django.conf import settings
from django.core.cache import cache

from apps.core.money import to_minor

from .base import DELIVERED, FAILED, PROCESSING, REJECTED, ProviderError, Result, classify, http

TOKEN_KEY = "vtung:token"  # noqa: S105 - cache key name
LOCK_KEY = "vtung:token:lock"
TOKEN_TTL = 6 * 24 * 3600
STATUS = {
    "completed-api": DELIVERED,
    "refunded": FAILED,
    "failed": FAILED,
    "cancelled": FAILED,
    "processing-api": PROCESSING,
    "queued-api": PROCESSING,
    "initiated-api": PROCESSING,
    "pending": PROCESSING,
    "on-hold": PROCESSING,
}
AUTH_ERRORS = {"jwt_auth_invalid_token", "jwt_auth_failed", "rest_forbidden"}

NETWORKS = {"mtn": "MTN", "glo": "Glo", "airtel": "Airtel", "9mobile": "9mobile"}
TV = {"dstv": "DStv", "gotv": "GOtv", "startimes": "Startimes", "showmax": "Showmax"}
DISCOS = {
    "ikeja-electric": "Ikeja Electric (IKEDC)",
    "eko-electric": "Eko Electric (EKEDC)",
    "abuja-electric": "Abuja Electric (AEDC)",
    "ibadan-electric": "Ibadan Electric (IBEDC)",
    "enugu-electric": "Enugu Electric (EEDC)",
    "portharcourt-electric": "Port Harcourt Electric (PHED)",
    "kano-electric": "Kano Electric (KEDCO)",
    "kaduna-electric": "Kaduna Electric (KAEDCO)",
    "jos-electric": "Jos Electric (JED)",
    "benin-electric": "Benin Electric (BEDC)",
    "aba-electric": "Aba Power (ABEDC)",
    "yola-electric": "Yola Electric (YEDC)",
}


def verify_signature(raw_body: bytes, signature: str | None) -> bool:
    pin = settings.VTUNG_USER_PIN
    if not signature or not pin:
        return False
    sig = signature.strip().lower()
    candidates = [raw_body]
    try:
        candidates.append(json.dumps(json.loads(raw_body), separators=(",", ":")).encode())
    except ValueError:
        pass
    return any(
        hmac.compare_digest(hmac.new(pin.encode(), c, hashlib.sha256).hexdigest(), sig) for c in candidates
    )


class VtuNg:
    name = "vtung"

    def __init__(self):
        self.base = settings.VTUNG_BASE_URL.rstrip("/")

    # ---- auth ---------------------------------------------------------------------------------
    def _login(self) -> str:
        body = http(
            "POST",
            f"{self.base}/jwt-auth/v1/token",
            provider=self.name,
            json={"username": settings.VTUNG_USERNAME, "password": settings.VTUNG_PASSWORD},
        )
        token = body.get("token")
        if not token:
            raise ProviderError("vtung: login returned no token", status_code=401, payload={})
        cache.set(TOKEN_KEY, token, TOKEN_TTL)
        return token

    def _token(self, stale: str | None = None) -> str:
        token = cache.get(TOKEN_KEY)
        if token and token != stale:
            return token
        if cache.add(LOCK_KEY, "1", timeout=30):
            try:
                return self._login()
            finally:
                cache.delete(LOCK_KEY)
        for _ in range(20):
            time.sleep(0.25)
            token = cache.get(TOKEN_KEY)
            if token and token != stale:
                return token
        return self._login()

    def _authed(self, method: str, path: str, **kwargs) -> dict:
        token = self._token()
        try:
            return http(
                method,
                f"{self.base}{path}",
                provider=self.name,
                headers={"Authorization": f"Bearer {token}"},
                **kwargs,
            )
        except ProviderError as exc:
            code = (exc.payload or {}).get("code") if isinstance(exc.payload, dict) else ""
            if (
                exc.status_code == 403 and code in AUTH_ERRORS
            ):  # checked before any order exists: one safe retry
                fresh = self._token(stale=token)
                return http(
                    method,
                    f"{self.base}{path}",
                    provider=self.name,
                    headers={"Authorization": f"Bearer {fresh}"},
                    **kwargs,
                )
            raise

    # ---- interface ----------------------------------------------------------------------------
    def supports(self, biller, plan) -> bool:
        if "vtung" not in biller.provider_codes:
            return False
        return plan is None or "vtung" in plan.provider_codes

    def verify_customer(self, biller, plan, customer_id: str) -> dict:
        payload = {"customer_id": customer_id, "service_id": biller.provider_codes["vtung"]}
        if biller.category == "electricity" and plan is not None:
            payload["variation_id"] = plan.provider_codes["vtung"]
        data = self._authed("POST", "/api/v2/verify-customer", json=payload).get("data") or {}
        keep = (
            "customer_address",
            "meter_number",
            "customer_arrears",
            "min_purchase_amount",
            "max_purchase_amount",
            "current_bouquet",
            "renewal_amount",
            "due_date",
            "status",
        )
        return {"name": data.get("customer_name") or "", "details": {k: data[k] for k in keep if k in data}}

    @staticmethod
    def _naira(kobo: int) -> int:
        if kobo % 100:
            raise ProviderError("vtung: whole naira only", status_code=400)
        return kobo // 100

    def _payload(self, order, request_id: str) -> tuple[str, dict]:
        sid = order.biller.provider_codes["vtung"]
        if order.category == "airtime":
            return "/api/v2/airtime", {
                "request_id": request_id,
                "phone": order.customer_id,
                "service_id": sid,
                "amount": self._naira(order.amount),
            }
        if order.category == "data":
            return "/api/v2/data", {
                "request_id": request_id,
                "phone": order.customer_id,
                "service_id": sid,
                "variation_id": order.plan.provider_codes["vtung"],
            }
        if order.category == "electricity":
            return "/api/v2/electricity", {
                "request_id": request_id,
                "customer_id": order.customer_id,
                "service_id": sid,
                "variation_id": order.plan.provider_codes["vtung"],
                "amount": self._naira(order.amount),
            }
        payload = {
            "request_id": request_id,
            "customer_id": order.customer_id,
            "service_id": sid,
            "variation_id": order.plan.provider_codes["vtung"],
        }
        if sid in ("dstv", "gotv"):
            payload["subscription_type"] = "change"
        return "/api/v2/tv", payload

    def _result(self, body: dict) -> Result:
        if body.get("code") != "success":
            return Result(outcome=REJECTED, message=str(body.get("message") or "order rejected")[:200])
        data = body.get("data") or {}
        outcome = STATUS.get(str(data.get("status") or "").lower(), PROCESSING)
        cost = data.get("amount_charged")
        return Result(
            outcome=outcome,
            reference=str(data.get("order_id") or ""),
            token=str(data.get("token") or ""),
            units=str(data.get("units") or ""),
            cost=to_minor(str(cost), "NGN") if cost not in (None, "") else None,
            raw={k: v for k, v in data.items() if k not in ("token",)},
        )

    def purchase(self, order, request_id: str) -> Result:
        path, payload = self._payload(order, request_id)
        try:
            return self._result(self._authed("POST", path, json=payload))
        except ProviderError as exc:
            code = (exc.payload or {}).get("code") if isinstance(exc.payload, dict) else ""
            if code == "insufficient_funds":
                import logging

                logging.getLogger(__name__).critical(
                    "VTU.ng float is empty: fund it now (bills failing over/refunding)"
                )
            return Result(outcome=classify(exc), message=str(exc)[:200])

    def requery(self, order, request_id: str) -> Result:
        try:
            return self._result(self._authed("POST", "/api/v2/requery", json={"request_id": request_id}))
        except ProviderError as exc:
            code = (exc.payload or {}).get("code") if isinstance(exc.payload, dict) else ""
            if exc.status_code == 404 and code == "order_not_found":
                return Result(outcome="not_found", message="order not found")
            return Result(outcome="unknown", message=str(exc)[:200])

    # ---- catalogue ----------------------------------------------------------------------------
    def variations(self, kind: str) -> list[dict]:
        return http("GET", f"{self.base}/api/v2/variations/{kind}", provider=self.name).get("data") or []


def _priced(naira, markup_percent: float) -> int:
    return math.ceil(float(naira) * (1 + markup_percent / 100)) * 100


def _plan_details(name: str) -> dict:
    out = {}
    if m := re.search(r"(\d+(?:\.\d+)?)\s*(GB|MB|TB)", name, re.I):
        out["data_mb"] = int(float(m.group(1)) * {"MB": 1, "GB": 1024, "TB": 1024 * 1024}[m.group(2).upper()])
    if m := re.search(r"(\d+)\s*Day", name, re.I):
        out["validity_days"] = int(m.group(1))
    return out
