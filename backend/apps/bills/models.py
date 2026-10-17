"""
Bills (Module E): airtime, data, cable TV and electricity, bought through licensed VTU providers.
Pay-per-transaction: the person pays the exact total at the gateway checkout; only a verified payment
is fulfilled; anything we can't deliver is refunded through the gateway. No stored balance (ADR-0002).
"""

import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.fields import EncryptedTextField
from apps.core.models import TimeStampedModel
from apps.core.money import CurrencyField, MoneyField


class Category(models.TextChoices):
    AIRTIME = "airtime", _("Airtime")
    DATA = "data", _("Data")
    CABLE_TV = "cable_tv", _("Cable TV")
    ELECTRICITY = "electricity", _("Electricity")


def new_order_reference() -> str:
    return "BIL" + secrets.token_hex(10).upper()


class Biller(TimeStampedModel):
    """A network, TV service or electricity company, with its code at each provider."""

    category = models.CharField(max_length=12, choices=Category.choices, db_index=True)
    code = models.SlugField(max_length=60, help_text=_("Our code, e.g. mtn, dstv, ikeja-electric."))
    name = models.CharField(max_length=120)
    customer_label = models.CharField(max_length=60, default="Phone number")
    requires_verification = models.BooleanField(
        default=False, help_text=_("Look up the meter/smartcard owner first.")
    )
    min_amount = MoneyField(null=True, blank=True)
    max_amount = MoneyField(null=True, blank=True)
    provider_codes = models.JSONField(
        default=dict, blank=True, help_text=_('e.g. {"vtung": "mtn", "flutterwave": {...}}')
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("category", "sort_order", "name")
        constraints = [models.UniqueConstraint(fields=["category", "code"], name="biller_unique_code")]

    def __str__(self):
        return self.name


class Plan(TimeStampedModel):
    """A data bundle, TV bouquet, or electricity meter type (prepaid/postpaid, open amount)."""

    biller = models.ForeignKey(Biller, on_delete=models.CASCADE, related_name="plans")
    code = models.CharField(max_length=80)
    name = models.CharField(max_length=160)
    price = MoneyField(
        null=True, blank=True, help_text=_("What the person pays; empty = they choose the amount.")
    )
    provider_codes = models.JSONField(default=dict, blank=True)
    provider_costs = models.JSONField(
        default=dict, blank=True, help_text=_("Provider price in kobo, per provider.")
    )
    validity_days = models.PositiveSmallIntegerField(null=True, blank=True)
    data_mb = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "price", "name")
        constraints = [models.UniqueConstraint(fields=["biller", "code"], name="plan_unique_code")]

    def __str__(self):
        return f"{self.biller.name}: {self.name}"


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        AWAITING_PAYMENT = "awaiting_payment", _("Waiting for payment")
        PROCESSING = "processing", _("Paid, delivering")
        DELIVERED = "delivered", _("Delivered")
        REFUND_PENDING = "refund_pending", _("Couldn't deliver, refunding")
        REFUNDED = "refunded", _("Refunded")
        EXPIRED = "expired", _("Payment not completed")

    reference = models.CharField(max_length=40, unique=True, default=new_order_reference)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="bill_orders"
    )
    phone_number = models.CharField(
        max_length=16, db_index=True, help_text=_("The buyer (receipts go here).")
    )
    unit = models.ForeignKey(
        "properties.Unit", on_delete=models.SET_NULL, null=True, blank=True, related_name="bill_orders"
    )
    category = models.CharField(max_length=12, choices=Category.choices)
    biller = models.ForeignKey(Biller, on_delete=models.PROTECT, related_name="orders")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, null=True, blank=True, related_name="orders")
    customer_id = models.CharField(max_length=40, help_text=_("Phone, meter or smartcard number."))
    customer_name = models.CharField(max_length=150, blank=True)
    amount = MoneyField(help_text=_("Face value delivered."))
    fee = MoneyField(default=0)
    total = MoneyField(help_text=_("What the person pays: amount + fee."))
    currency = CurrencyField(default="NGN")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.AWAITING_PAYMENT, db_index=True
    )
    channel = models.CharField(max_length=10, default="app")

    # Payment (to Homesika's own account; no landlord split)
    gateway = models.CharField(max_length=12, blank=True)
    gateway_reference = models.CharField(max_length=60, blank=True, db_index=True)
    checkout_url = models.URLField(max_length=500, blank=True)
    payment_attempts = models.JSONField(default=list, blank=True)
    paid_amount = MoneyField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()

    # Fulfilment
    provider = models.CharField(max_length=20, blank=True, help_text=_("The provider currently/last trying."))
    provider_reference = models.CharField(max_length=60, blank=True, db_index=True)
    attempts = models.JSONField(default=list, blank=True, help_text=_("Provider attempts (failover)."))
    status_checks = models.PositiveSmallIntegerField(default=0)
    provider_cost = MoneyField(null=True, blank=True)
    token = EncryptedTextField(blank=True, help_text=_("Electricity token (encrypted)."))
    units = models.CharField(max_length=40, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    # Refund and review
    refund_reference = models.CharField(max_length=80, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    needs_review = models.BooleanField(default=False, db_index=True)
    review_reason = models.CharField(max_length=255, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    receipt_number = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="bill_amount_positive"),
            models.CheckConstraint(
                condition=Q(total__gte=models.F("amount")), name="bill_total_covers_amount"
            ),
        ]

    def __str__(self):
        return self.reference


class ReceiptCounter(models.Model):
    """Gap-free bill receipt numbers (BIL-000001)."""

    key = models.CharField(max_length=10, primary_key=True, default="bills")
    last = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.key}:{self.last}"


class ProviderEvent(TimeStampedModel):
    """A VTU provider webhook, stored once before processing."""

    provider = models.CharField(max_length=20)
    event_id = models.CharField(max_length=120)
    reference = models.CharField(max_length=60, db_index=True)
    payload = models.JSONField(default=dict)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "event_id"], name="bill_provider_event_unique")
        ]

    def __str__(self):
        return f"{self.provider}:{self.event_id}"
