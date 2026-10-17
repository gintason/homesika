"""
Reloadly airtime top-ups to phones abroad (international airtime).

What comes from Reloadly's official SDK code (`reloadly-airtime` 1.1.2, `reloadly-auth` / `reloadly-core`
1.1.1), not from memory:
* Auth: POST https://auth.reloadly.com/oauth/token {client_id, client_secret, grant_type: client_credentials,
  audience: <API base>} -> access_token.
* API base: https://topups.reloadly.com (live), https://topups-sandbox.reloadly.com (sandbox), with
  `Accept: application/com.reloadly.topups-v1+json`.
* Endpoints: GET /countries, GET /operators/countries/{ISO}, GET /operators/auto-detect/phone/{phone}/
  countries/{ISO}, POST /topups {operatorId, amount, useLocalAmount, customIdentifier, recipientPhone:
  {countryCode, number}}, GET /topups/reports/transaction (filter customIdentifier).
* Errors: a JSON body with "errorCode" and "message". Operator fields: id, name, denominationType (FIXED /
  RANGE), senderCurrencyCode, destinationCurrencyCode, minAmount, maxAmount, fixedAmounts, fxRate.

TODO(verify) in the Reloadly sandbox before going live: the token's lifetime (`expires_in`), the success
response of POST /topups (the transaction id field and whether a "status" is returned), the history
endpoint's exact path and response wrapper ("content"), and which errorCodes mean "never created".
Amounts are in the account's (sender) currency: Homesika only allows operators whose
senderCurrencyCode is NGN, so a naira-funded Reloadly account is required.
"""

import logging

from django.conf import settings
from django.core.cache import cache

from apps.core.money import to_minor

from .base import DELIVERED, PROCESSING, REJECTED, UNKNOWN, ProviderError, Result, classify, http

logger = logging.getLogger(__name__)
AUTH_URL = "https://auth.reloadly.com/oauth/token"
LIVE, SANDBOX = "https://topups.reloadly.com", "https://topups-sandbox.reloadly.com"
ACCEPT = "application/com.reloadly.topups-v1+json"
TOKEN_KEY = "reloadly:token"  # noqa: S105 - cache key name
# Errors where Reloadly can't have created the top-up (bad input, auth, balance). TODO(verify) the list.
NEVER_CREATED = {
    "INSUFFICIENT_BALANCE",
    "INVALID_PHONE_NUMBER",
    "OPERATOR_NOT_FOUND",
    "INVALID_AMOUNT_FOR_OPERATOR",
    "INVALID_TOKEN",
    "TOKEN_EXPIRED",
    "COUNTRY_NOT_SUPPORTED",
}


def base_url() -> str:
    return LIVE if settings.RELOADLY_LIVE else SANDBOX


class Reloadly:
    name = "reloadly"

    # ---- auth ----
    def _token(self, refresh: bool = False) -> str:
        if not (settings.RELOADLY_CLIENT_ID and settings.RELOADLY_CLIENT_SECRET):
            raise ProviderError(
                "reloadly: RELOADLY_CLIENT_ID / RELOADLY_CLIENT_SECRET not set", status_code=400
            )
        token = None if refresh else cache.get(TOKEN_KEY)
        if token:
            return token
        body = http(
            "POST",
            AUTH_URL,
            provider=self.name,
            json={
                "client_id": settings.RELOADLY_CLIENT_ID,
                "client_secret": settings.RELOADLY_CLIENT_SECRET,
                "grant_type": "client_credentials",
                "audience": base_url(),
            },
        )
        token = body.get("access_token")
        if not token:
            raise ProviderError("reloadly: no access_token in the auth response")
        ttl = int(body.get("expires_in") or 3600)  # TODO(verify) the real lifetime
        cache.set(TOKEN_KEY, token, max(60, ttl - 300))
        return token

    def call(self, method: str, path: str, **kwargs) -> dict | list:
        for attempt in (0, 1):
            headers = {"Accept": ACCEPT, "Authorization": f"Bearer {self._token(refresh=attempt == 1)}"}
            try:
                body = http(method, f"{base_url()}{path}", provider=self.name, headers=headers, **kwargs)
            except ProviderError as exc:
                if exc.status_code == 401 and attempt == 0:
                    continue  # token expired: log in again once
                raise
            if isinstance(body, dict) and body.get("errorCode"):
                raise ProviderError(
                    f"reloadly: {body.get('message') or body['errorCode']}", status_code=400, payload=body
                )
            return body
        raise ProviderError("reloadly: unauthorised")

    # ---- catalogue (used by apps.bills.intl) ----
    def countries(self) -> list[dict]:
        return list(self.call("GET", "/countries"))

    def detect_operator(self, phone: str, country: str) -> dict:
        return dict(self.call("GET", f"/operators/auto-detect/phone/{phone}/countries/{country}"))

    # ---- VtuProvider interface ----
    def supports(self, biller, plan) -> bool:
        return biller.category == "intl_airtime" and bool(settings.RELOADLY_CLIENT_ID)

    def verify_customer(self, biller, plan, customer_id: str) -> dict:
        return {"name": "", "details": {}}

    def purchase(self, order, request_id: str) -> Result:
        intl = order.intl or {}
        payload = {
            "operatorId": int(intl["operator_id"]),
            "amount": order.amount / 100,  # naira, in the account (sender) currency
            "useLocalAmount": False,
            "customIdentifier": request_id,
            "recipientPhone": {"countryCode": intl["country"], "number": order.customer_id},
        }
        try:
            body = self.call("POST", "/topups", json=payload)
        except ProviderError as exc:
            code = str((exc.payload or {}).get("errorCode") or "") if isinstance(exc.payload, dict) else ""
            if code == "INSUFFICIENT_BALANCE":
                logger.critical("Reloadly balance is empty: fund it now (international top-ups failing)")
            if code in NEVER_CREATED:
                return Result(outcome=REJECTED, message=str(exc)[:200])
            # Any other error: the top-up MAY exist, so requery by our customIdentifier, never retry blindly.
            return Result(outcome=UNKNOWN if code == "" else classify(exc), message=str(exc)[:200])
        return self._result(body)

    def requery(self, order, request_id: str) -> Result:
        try:
            body = self.call("GET", "/topups/reports/transaction", params={"customIdentifier": request_id})
        except ProviderError as exc:
            return Result(outcome=classify(exc), message=str(exc)[:200])
        rows = body.get("content", []) if isinstance(body, dict) else list(body or [])
        mine = [r for r in rows if str(r.get("customIdentifier")) == request_id]
        if not mine:
            # Not found: if the purchase never reached Reloadly it was never made. TODO(verify) how soon a new
            # top-up appears in the history; until then the order stays "unknown" and goes to review.
            return Result(outcome=PROCESSING, message="not in Reloadly's history yet")
        return self._result(mine[0])

    @staticmethod
    def _result(t: dict) -> Result:
        status = str(t.get("status") or "SUCCESSFUL").upper()  # TODO(verify) status values
        if status in ("FAILED", "REFUNDED"):
            return Result(
                outcome="failed",
                reference=str(t.get("transactionId") or t.get("id") or ""),
                message=f"reloadly: {status.lower()}",
            )
        if status not in ("SUCCESSFUL", "SUCCESS", "COMPLETED"):
            return Result(outcome=PROCESSING, reference=str(t.get("transactionId") or t.get("id") or ""))
        cost = t.get("requestedAmount")
        delivered = t.get("deliveredAmount")
        return Result(
            outcome=DELIVERED,
            reference=str(t.get("transactionId") or t.get("id") or ""),
            units=f"{delivered} {t.get('deliveredAmountCurrencyCode') or ''}".strip()
            if delivered is not None
            else "",
            cost=to_minor(str(cost), "NGN")
            if cost is not None and t.get("requestedAmountCurrencyCode") == "NGN"
            else None,
            raw={
                k: t.get(k)
                for k in (
                    "transactionId",
                    "id",
                    "operatorTransactionId",
                    "operatorName",
                    "countryCode",
                    "deliveredAmount",
                    "deliveredAmountCurrencyCode",
                    "discount",
                )
            },
        )
