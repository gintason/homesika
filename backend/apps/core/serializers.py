from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .money import to_major, to_minor


class MoneyField(serializers.Field):
    """API edge for money: in/out as a decimal string in major units ("1500000.00"), stored as integer minor
    units. The currency comes from `currency_source` on the object, else the serializer context's
    "currency" (the organization's currency)."""

    default_error_messages = {
        "invalid": _("Enter a valid amount."),
        "negative": _("Amount can't be negative."),
        "zero": _("Amount must be more than zero."),
    }

    def __init__(self, *, allow_zero=True, currency_source="currency", **kwargs):
        self.allow_zero = allow_zero
        self.currency_source = currency_source
        super().__init__(**kwargs)

    def _currency(self, obj=None) -> str:
        if obj is not None and getattr(obj, self.currency_source, None):
            return getattr(obj, self.currency_source)
        return self.context.get("currency", "NGN")

    def get_attribute(self, instance):
        self._row = instance  # remember the row so its own currency is used (works for lists too)
        return super().get_attribute(instance)

    def to_representation(self, value):
        return None if value is None else str(to_major(value, self._currency(getattr(self, "_row", None))))

    def to_internal_value(self, data):
        try:
            amount = Decimal(str(data).replace(",", "").strip())
        except (InvalidOperation, ValueError):
            self.fail("invalid")
        if amount < 0:
            self.fail("negative")
        if amount == 0 and not self.allow_zero:
            self.fail("zero")
        try:
            return to_minor(amount, self._currency())
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
