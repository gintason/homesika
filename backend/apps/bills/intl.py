"""
International airtime (Reloadly): which countries, which operator a number belongs to, and the naira
amounts allowed. The operator is always detected on the server from the number; the app never chooses it.

Without Reloadly credentials (development and tests) a labelled SAMPLE catalogue is used; production
refuses it (BILLS_PROVIDERS can't be "mock" there, and without credentials no provider supports the order).
"""

import re
from dataclasses import asdict, dataclass

from django.conf import settings
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers, status

from apps.core.exceptions import HomesikaAPIException
from apps.core.money import to_minor

from .providers.base import ProviderError

SAMPLE = {
    "countries": [
        {"isoName": "GH", "name": "Ghana", "currencyCode": "GHS", "callingCodes": ["+233"]},
        {"isoName": "KE", "name": "Kenya", "currencyCode": "KES", "callingCodes": ["+254"]},
        {"isoName": "GB", "name": "United Kingdom", "currencyCode": "GBP", "callingCodes": ["+44"]},
    ],
    "operators": {
        "GH": {
            "id": 900001,
            "name": "MTN Ghana (sample)",
            "denominationType": "RANGE",
            "senderCurrencyCode": "NGN",
            "destinationCurrencyCode": "GHS",
            "minAmount": 500,
            "maxAmount": 50000,
            "fixedAmounts": [],
            "fxRate": {"rate": 0.0075, "currencyCode": "GHS"},
        },
        "KE": {
            "id": 900002,
            "name": "Safaricom Kenya (sample)",
            "denominationType": "RANGE",
            "senderCurrencyCode": "NGN",
            "destinationCurrencyCode": "KES",
            "minAmount": 500,
            "maxAmount": 50000,
            "fixedAmounts": [],
            "fxRate": {"rate": 0.08, "currencyCode": "KES"},
        },
        "GB": {
            "id": 900003,
            "name": "EE UK (sample)",
            "denominationType": "FIXED",
            "senderCurrencyCode": "NGN",
            "destinationCurrencyCode": "GBP",
            "minAmount": None,
            "maxAmount": None,
            "fixedAmounts": [5000, 10000, 20000],
            "fxRate": {"rate": 0.0005, "currencyCode": "GBP"},
        },
    },
}


class IntlUnavailable(HomesikaAPIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = _("International top-ups aren't available right now. Please try again later.")
    default_code = "intl_unavailable"


@dataclass
class Operator:
    operator_id: str
    name: str
    country: str
    denomination: str  # "range" or "fixed"
    min_amount: int | None  # kobo
    max_amount: int | None
    fixed_amounts: list[int]
    local_currency: str
    fx_rate: float | None  # local currency per naira, an estimate shown as "about"
    sample: bool

    def as_api(self) -> dict:
        d = asdict(self)
        for k in ("min_amount", "max_amount"):
            d[k] = None if d[k] is None else f"{d[k] / 100:.2f}"
        d["fixed_amounts"] = [f"{a / 100:.2f}" for a in self.fixed_amounts]
        return d


def _live() -> bool:
    return bool(settings.RELOADLY_CLIENT_ID) and "reloadly" in settings.BILLS_PROVIDERS


def _client():
    from .providers.reloadly import Reloadly

    return Reloadly()


def enabled() -> bool:
    return settings.INTL_TOPUP_ENABLED and (_live() or "mock" in settings.BILLS_PROVIDERS)


def allowed() -> set[str]:
    return {c.strip().upper() for c in settings.INTL_TOPUP_COUNTRIES.split(",") if c.strip()} - {"NG"}


def countries() -> list[dict]:
    if not enabled():
        raise IntlUnavailable()
    key = "intl:countries:live" if _live() else "intl:countries:sample"
    rows = cache.get(key)
    if rows is None:
        try:
            raw = _client().countries() if _live() else SAMPLE["countries"]
        except ProviderError as exc:
            raise IntlUnavailable() from exc
        rows = [
            {
                "code": c["isoName"],
                "name": c["name"],
                "currency": c.get("currencyCode", ""),
                "calling_code": (c.get("callingCodes") or [""])[0],
            }
            for c in raw
        ]
        cache.set(key, rows, 6 * 3600)
    return [r for r in rows if r["code"] in allowed()]


def normalise(phone: str, calling_code: str) -> str:
    digits = re.sub(r"[^\d+]", "", phone or "")
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if not digits.startswith("+"):
        digits = calling_code + digits.lstrip("0")
    return digits


def _kobo(v) -> int | None:
    return None if v in (None, "") else to_minor(str(v), "NGN")


def detect(country: str, phone: str) -> tuple[str, Operator]:
    """(E.164 phone, operator) for a number abroad. Raises a field error the person can fix."""
    country = (country or "").upper()
    match = next((c for c in countries() if c["code"] == country), None)
    if match is None:
        raise serializers.ValidationError({"country": [_("Choose a country from the list.")]})
    phone = normalise(phone, match["calling_code"])
    if not re.fullmatch(r"\+[1-9]\d{6,14}", phone) or phone.startswith("+234"):
        raise serializers.ValidationError(
            {"phone": [_("Enter the full number abroad, e.g. +233 24 123 4567.")]}
        )
    if match["calling_code"] and not phone.startswith(match["calling_code"]):
        raise serializers.ValidationError(
            {"phone": [_("This number doesn't start with %(code)s.") % {"code": match["calling_code"]}]}
        )
    key = f"intl:op:{country}:{phone}"
    op = cache.get(key)
    if op is None:
        if _live():
            try:
                raw = _client().detect_operator(phone, country)
            except ProviderError as exc:
                if exc.status_code and 400 <= exc.status_code < 500:
                    raise serializers.ValidationError(
                        {
                            "phone": [
                                _("We couldn't find the network for this number. Check it and try again.")
                            ]
                        }
                    ) from exc
                raise IntlUnavailable() from exc
        else:
            raw = SAMPLE["operators"].get(country)
            if raw is None:
                raise serializers.ValidationError(
                    {"phone": [_("We couldn't find the network for this number.")]}
                )
        if raw.get("senderCurrencyCode") != "NGN":
            raise IntlUnavailable()  # the Reloadly account must be funded in naira
        fx = raw.get("fxRate") or {}
        op = Operator(
            operator_id=str(raw["id"]),
            name=str(raw.get("name") or ""),
            country=country,
            denomination="fixed" if str(raw.get("denominationType")).upper() == "FIXED" else "range",
            min_amount=_kobo(raw.get("minAmount")),
            max_amount=_kobo(raw.get("maxAmount")),
            fixed_amounts=[_kobo(a) for a in (raw.get("fixedAmounts") or []) if a is not None],
            local_currency=str(raw.get("destinationCurrencyCode") or match["currency"]),
            fx_rate=float(fx["rate"]) if fx.get("rate") else None,
            sample=not _live(),
        )
        cache.set(key, op, 10 * 60)
    return phone, op


def check_amount(op: Operator, amount: int | None) -> int:
    if not amount or amount % 100:
        raise serializers.ValidationError({"amount": [_("Enter a whole naira amount.")]})
    if op.denomination == "fixed":
        if amount not in op.fixed_amounts:
            raise serializers.ValidationError({"amount": [_("Choose one of the amounts shown.")]})
    else:
        if op.min_amount and amount < op.min_amount or op.max_amount and amount > op.max_amount:
            raise serializers.ValidationError(
                {
                    "amount": [
                        _("For this network the amount must be between ₦%(min)s and ₦%(max)s.")
                        % {
                            "min": f"{(op.min_amount or 0) // 100:,}",
                            "max": f"{(op.max_amount or 0) // 100:,}",
                        }
                    ]
                }
            )
    return amount
