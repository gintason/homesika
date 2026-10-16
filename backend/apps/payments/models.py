import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.fields import EncryptedTextField
from apps.core.models import TimeStampedModel
from apps.core.money import CurrencyField, MoneyField


class Gateway(models.TextChoices):
    PAYSTACK = "paystack", "Paystack"
    FLUTTERWAVE = "flutterwave", "Flutterwave"
    MOCK = "mock", _("Mock gateway (development only)")
    MANUAL = "manual", _("Recorded manually")


def new_reference() -> str:
    return "HSK" + secrets.token_hex(10).upper()


def new_receipt_token() -> str:
    """Unguessable id for the public receipt link sent by SMS (the payment id is never exposed)."""
    return secrets.token_urlsafe(18)


class SettlementAccount(TimeStampedModel):
    """Where an organization's collections settle: its OWN bank account, registered with the gateway as a
    subaccount. Homesika never holds rent (ADR-0002)."""

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        FAILED = "failed", _("Rejected by gateway")
        DISABLED = "disabled", _("Disabled")

    organization = models.ForeignKey(
        "orgs.Organization", on_delete=models.CASCADE, related_name="settlement_accounts"
    )
    gateway = models.CharField(max_length=12, choices=Gateway.choices)
    bank_code = models.CharField(max_length=10)
    bank_name = models.CharField(max_length=80, blank=True)
    account_number = EncryptedTextField()
    account_last4 = models.CharField(max_length=4)
    account_name = models.CharField(max_length=120, blank=True)
    subaccount_code = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    failure_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "gateway"],
                condition=Q(status="active"),
                name="one_active_settlement_per_gateway",
            )
        ]

    def __str__(self):
        return f"{self.organization} · {self.gateway} ****{self.account_last4}"


class PaymentLink(TimeStampedModel):
    """A request to pay specific charges. Shareable by SMS/WhatsApp; the gateway session is created only
    when the payer opens it, so the failover choice is made at payment time."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Awaiting payment")
        PAID = "paid", _("Paid")
        EXPIRED = "expired", _("Expired")
        CANCELLED = "cancelled", _("Cancelled")

    organization = models.ForeignKey(
        "orgs.Organization", on_delete=models.CASCADE, related_name="payment_links"
    )
    reference = models.CharField(max_length=40, unique=True, default=new_reference)
    tenant = models.ForeignKey(
        "leasing.TenantProfile", on_delete=models.PROTECT, related_name="payment_links"
    )
    charges = models.ManyToManyField("leasing.Charge", related_name="payment_links")
    amount = MoneyField()
    currency = CurrencyField(default="NGN")
    description = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    expires_at = models.DateTimeField()
    gateway = models.CharField(max_length=12, choices=Gateway.choices, blank=True)
    gateway_reference = models.CharField(max_length=60, blank=True, db_index=True)
    checkout_url = models.URLField(max_length=500, blank=True)
    attempts = models.JSONField(
        default=list, blank=True, help_text=_("Gateway initialisation attempts (failover).")
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    def __str__(self):
        return self.reference


class Payment(TimeStampedModel):
    """Money that reached the landlord: a verified gateway transaction, or cash/transfer recorded by staff."""

    class Status(models.TextChoices):
        SUCCEEDED = "succeeded", _("Succeeded")
        REVERSED = "reversed", _("Reversed / refunded")

    organization = models.ForeignKey("orgs.Organization", on_delete=models.CASCADE, related_name="payments")
    tenant = models.ForeignKey("leasing.TenantProfile", on_delete=models.PROTECT, related_name="payments")
    payment_link = models.ForeignKey(
        PaymentLink, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments"
    )
    gateway = models.CharField(max_length=12, choices=Gateway.choices)
    gateway_reference = models.CharField(max_length=60)
    channel = models.CharField(max_length=30, blank=True, help_text=_("card, bank_transfer, ussd, cash..."))
    amount = MoneyField()
    platform_fee_amount = MoneyField(default=0)
    gateway_fee_amount = MoneyField(default=0)
    unallocated_amount = MoneyField(default=0, help_text=_("Overpayment not matched to any charge."))
    currency = CurrencyField(default="NGN")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUCCEEDED)
    paid_at = models.DateTimeField()
    needs_review = models.BooleanField(default=False, db_index=True)
    review_reason = models.CharField(max_length=255, blank=True)
    note = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    verified_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-paid_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["gateway", "gateway_reference"], name="payment_unique_gateway_ref"
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_positive"),
        ]

    def __str__(self):
        return f"{self.gateway}:{self.gateway_reference}"


class Allocation(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="allocations")
    charge = models.ForeignKey("leasing.Charge", on_delete=models.PROTECT, related_name="allocations")
    amount = MoneyField()

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="allocation_amount_positive")]

    def __str__(self):
        return f"{self.payment_id} -> {self.charge_id}: {self.amount}"


class Receipt(TimeStampedModel):
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name="receipt")
    number = models.CharField(max_length=40)
    organization = models.ForeignKey("orgs.Organization", on_delete=models.CASCADE, related_name="receipts")
    public_token = models.CharField(max_length=32, unique=True, default=new_receipt_token, editable=False)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "number"], name="receipt_number_unique_in_org")
        ]

    def __str__(self):
        return self.number


class ReceiptCounter(models.Model):
    """Gap-free per-organization receipt numbering (row-locked when issuing)."""

    organization = models.OneToOneField("orgs.Organization", on_delete=models.CASCADE, primary_key=True)
    last = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.organization_id}: {self.last}"


class GatewayEvent(TimeStampedModel):
    """Every webhook, stored once (unique per gateway event id) before processing."""

    class Status(models.TextChoices):
        RECEIVED = "received", _("Received")
        PROCESSED = "processed", _("Processed")
        IGNORED = "ignored", _("Ignored")
        FAILED = "failed", _("Failed")

    gateway = models.CharField(max_length=12, choices=Gateway.choices)
    event_id = models.CharField(max_length=120)
    event_type = models.CharField(max_length=80, blank=True)
    reference = models.CharField(max_length=60, blank=True, db_index=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RECEIVED, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["gateway", "event_id"], name="gateway_event_unique")]

    def __str__(self):
        return f"{self.gateway}:{self.event_id}"


class ReminderLog(models.Model):
    """One row per (charge, stage) so a reminder is never sent twice, even if the daily job reruns."""

    charge = models.ForeignKey("leasing.Charge", on_delete=models.CASCADE, related_name="reminders")
    stage = models.CharField(max_length=12)
    sent_at = models.DateTimeField(auto_now_add=True)
    payment_link = models.ForeignKey(PaymentLink, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["charge", "stage"], name="reminder_once_per_stage")]

    def __str__(self):
        return f"{self.charge_id}:{self.stage}"
