from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

# E.164 international format, e.g. +2348012345678
phone_validator = RegexValidator(
    regex=r"^\+[1-9]\d{7,14}$",
    message=_("Enter a phone number in international format, e.g. +2348012345678."),
    code="invalid_phone",
)

login_pin_validator = RegexValidator(
    regex=r"^\d{6}$", message=_("Your login PIN must be exactly 6 digits."), code="invalid_login_pin_format"
)

transaction_pin_validator = RegexValidator(
    regex=r"^\d{4}$", message=_("Your transaction PIN must be exactly 4 digits."), code="invalid_pin_format"
)


def is_weak_pin(pin: str) -> bool:
    """All one digit (000000) or a straight run up or down (123456, 6543)."""
    digits = [int(c) for c in pin]
    steps = {b - a for a, b in zip(digits, digits[1:], strict=False)}
    return len(set(digits)) == 1 or steps in ({1}, {-1})


def normalise_phone(raw: str, default_country_code: str = "234") -> str:
    """08012345678 / 2348012345678 / +234 801 234 5678 -> +2348012345678 (Nigeria default)."""
    digits = "".join(ch for ch in raw if ch.isdigit() or ch == "+")
    if digits.startswith("+"):
        return digits
    if digits.startswith(default_country_code):
        return f"+{digits}"
    if digits.startswith("0") and len(digits) == 11:
        return f"+{default_country_code}{digits[1:]}"
    return digits
