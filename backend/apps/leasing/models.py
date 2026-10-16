from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.validators import phone_validator
from apps.core.fields import EncryptedTextField
from apps.core.models import TimeStampedModel
from apps.core.money import CurrencyField, MoneyField


class TenantProfile(TimeStampedModel):
    """A tenant as the landlord's organization knows them. Linked to a User once the tenant joins the app
    (same phone number), but it exists before that so landlords can start right away."""

    organization = models.ForeignKey("orgs.Organization", on_delete=models.CASCADE, related_name="tenants")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tenant_profiles",
    )
    full_name = models.CharField(max_length=160)
    phone_number = models.CharField(max_length=16, validators=[phone_validator], db_index=True)
    email = models.EmailField(blank=True)
    occupation = models.CharField(max_length=100, blank=True)
    next_of_kin = EncryptedTextField(blank=True, help_text=_("Name and phone (encrypted)."))
    id_document = EncryptedTextField(blank=True, help_text=_("ID type and number (encrypted)."))
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("full_name",)
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "phone_number"], name="tenant_phone_unique_in_org"
            )
        ]

    def __str__(self):
        return self.full_name


class Frequency(models.TextChoices):
    MONTHLY = "monthly", _("Monthly")
    QUARTERLY = "quarterly", _("Every 3 months")
    BIANNUAL = "biannual", _("Every 6 months")
    ANNUAL = "annual", _("Yearly")


FREQUENCY_MONTHS = {Frequency.MONTHLY: 1, Frequency.QUARTERLY: 3, Frequency.BIANNUAL: 6, Frequency.ANNUAL: 12}


class Lease(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        ACTIVE = "active", _("Active")
        ENDED = "ended", _("Ended")
        TERMINATED = "terminated", _("Terminated early")

    organization = models.ForeignKey("orgs.Organization", on_delete=models.CASCADE, related_name="leases")
    unit = models.ForeignKey("properties.Unit", on_delete=models.PROTECT, related_name="leases")
    tenant = models.ForeignKey(TenantProfile, on_delete=models.PROTECT, related_name="leases")
    start_date = models.DateField()
    end_date = models.DateField()
    rent_amount = MoneyField(help_text=_("Rent per period (see rent_frequency), minor units."))
    rent_frequency = models.CharField(max_length=10, choices=Frequency.choices, default=Frequency.ANNUAL)
    service_charge_amount = MoneyField(default=0, help_text=_("Per period, same frequency as rent."))
    deposit_amount = MoneyField(default=0, help_text=_("Caution deposit, charged once at the start."))
    currency = CurrencyField(default="NGN")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    ended_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-start_date",)
        constraints = [
            models.UniqueConstraint(
                fields=["unit"], condition=Q(status="active"), name="one_active_lease_per_unit"
            ),
            models.CheckConstraint(condition=Q(end_date__gt=F("start_date")), name="lease_ends_after_start"),
            models.CheckConstraint(condition=Q(rent_amount__gt=0), name="lease_rent_positive"),
        ]

    def __str__(self):
        return f"{self.tenant} · {self.unit}"


class Charge(TimeStampedModel):
    """Money a tenant (or estate member, Phase 5) owes for a period. Payments settle it via Allocation."""

    class Kind(models.TextChoices):
        RENT = "rent", _("Rent")
        SERVICE_CHARGE = "service_charge", _("Service charge")
        DEPOSIT = "deposit", _("Caution deposit")
        DUES = "dues", _("Estate dues")
        OTHER = "other", _("Other")

    class Status(models.TextChoices):
        OPEN = "open", _("Unpaid")
        PART_PAID = "part_paid", _("Part paid")
        PAID = "paid", _("Paid")
        WAIVED = "waived", _("Waived")
        VOID = "void", _("Cancelled")

    OUTSTANDING = (Status.OPEN, Status.PART_PAID)

    organization = models.ForeignKey("orgs.Organization", on_delete=models.CASCADE, related_name="charges")
    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, null=True, blank=True, related_name="charges")
    unit = models.ForeignKey("properties.Unit", on_delete=models.PROTECT, related_name="charges")
    tenant = models.ForeignKey(
        TenantProfile, on_delete=models.PROTECT, null=True, blank=True, related_name="charges"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    description = models.CharField(max_length=160, blank=True)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    due_date = models.DateField(db_index=True)
    amount = MoneyField()
    amount_paid = MoneyField(default=0)
    currency = CurrencyField(default="NGN")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    waived_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("due_date", "kind")
        indexes = [models.Index(fields=["organization", "status", "due_date"])]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="charge_amount_positive"),
            models.CheckConstraint(
                condition=Q(amount_paid__gte=0) & Q(amount_paid__lte=F("amount")),
                name="charge_paid_within_amount",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.due_date} {self.amount}"

    @property
    def balance(self) -> int:
        return self.amount - self.amount_paid if self.status in self.OUTSTANDING else 0

    @property
    def is_overdue(self) -> bool:
        return self.status in self.OUTSTANDING and self.due_date < timezone.localdate()

    def refresh_status(self) -> None:
        """Recompute open / part_paid / paid from amount_paid (never touches waived or void)."""
        if self.status in (self.Status.WAIVED, self.Status.VOID):
            return
        if self.amount_paid >= self.amount:
            self.status = self.Status.PAID
        elif self.amount_paid > 0:
            self.status = self.Status.PART_PAID
        else:
            self.status = self.Status.OPEN
