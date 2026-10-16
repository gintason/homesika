"""
Money conventions used across Homesika.

Every monetary amount is stored as an integer in the currency's *minor unit*
(kobo, cents, pesewas). No floats ever touch stored amounts, so there is no
rounding drift. Convert only at the API edge.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

# ISO 4217 code -> minor-unit exponent. Extend as new corridors launch.
SUPPORTED_CURRENCIES: dict[str, int] = {
    "NGN": 2,
    "USD": 2,
    "GBP": 2,
    "EUR": 2,
    "GHS": 2,
    "KES": 2,
    "ZAR": 2,
    "XOF": 0,
    "CAD": 2,
}

CURRENCY_CHOICES = [(code, code) for code in SUPPORTED_CURRENCIES]


def validate_currency(code: str) -> None:
    if code not in SUPPORTED_CURRENCIES:
        raise ValidationError(_("Unsupported currency: %(code)s"), params={"code": code})


def to_minor(amount: Decimal | str | int, currency: str) -> int:
    """Major units (e.g. Decimal('1500.50') NGN) -> minor units (150050). Rejects sub-minor precision."""
    exp = SUPPORTED_CURRENCIES[currency]
    value = Decimal(str(amount)) * (10**exp)
    if value != value.to_integral_value():
        raise ValidationError(_("Too many decimal places for %(code)s."), params={"code": currency})
    return int(value)


def to_major(minor: int, currency: str) -> Decimal:
    exp = SUPPORTED_CURRENCIES[currency]
    return (Decimal(minor) / (10**exp)).quantize(Decimal(1).scaleb(-exp))


class CurrencyField(models.CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 3)
        kwargs.setdefault("choices", CURRENCY_CHOICES)
        super().__init__(*args, **kwargs)


class MoneyField(models.BigIntegerField):
    """Amount in minor units. Named so model code reads as money, not a count."""

    description = "Monetary amount in minor units"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("help_text", "Minor units (kobo/cents)")
        super().__init__(*args, **kwargs)


def format_money(minor: int, currency: str, *, plain: bool = False) -> str:
    """Human-readable, e.g. 150000 NGN-minor -> '₦1,500.00'. plain=True gives 'NGN 1,500.00' for SMS
    (the naira sign isn't in the GSM alphabet; it would double the SMS cost) and PDF core fonts."""
    symbols = {"NGN": "₦", "USD": "$", "GBP": "£", "EUR": "€", "GHS": "GH₵", "KES": "KSh ", "ZAR": "R"}
    major = to_major(minor, currency)
    sign = "-" if major < 0 else ""
    prefix = f"{currency} " if plain else symbols.get(currency, currency + " ")
    return f"{sign}{prefix}{abs(major):,.{SUPPORTED_CURRENCIES[currency]}f}"
