import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.accounts.validators import phone_validator
from apps.core.models import TimeStampedModel
from apps.core.money import CurrencyField, MoneyField
from apps.leasing.models import Frequency

JOIN_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I/L to misread


def _join_code() -> str:
    return "".join(secrets.choice(JOIN_ALPHABET) for _ in range(6))


class Estate(TimeStampedModel):
    """A gated estate run by an organization (usually of kind "estate"). Its houses are the units of its
    property, so dues are ordinary charges and residents pay them like rent."""

    organization = models.ForeignKey("orgs.Organization", on_delete=models.CASCADE, related_name="estates")
    property = models.OneToOneField("properties.Property", on_delete=models.PROTECT, related_name="estate")
    name = models.CharField(max_length=150)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    join_code = models.CharField(
        max_length=8, unique=True, default=_join_code, help_text=_("Residents enter this in the app to join.")
    )
    is_active = models.BooleanField(default=True)
    panic_enabled = models.BooleanField(default=True)
    alert_residents = models.BooleanField(
        default=True, help_text=_("Non-silent panic alerts also go to verified residents, not only security.")
    )
    gate_instructions = models.CharField(
        max_length=300, blank=True, help_text=_("Shown to visitors with their code.")
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class EstateMember(TimeStampedModel):
    """A resident (or estate executive) of an estate. Staff (estate admin, security desk) are organization
    members instead. An approved member is a "verified resident": they receive alerts and pay dues."""

    class Role(models.TextChoices):
        RESIDENT = "resident", _("Resident")
        EXCO = "exco", _("Executive committee")

    class Status(models.TextChoices):
        PENDING = "pending", _("Waiting for approval")
        APPROVED = "approved", _("Verified resident")
        SUSPENDED = "suspended", _("Suspended")
        REMOVED = "removed", _("Removed")

    estate = models.ForeignKey(Estate, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="estate_memberships",
    )
    full_name = models.CharField(max_length=160)
    phone_number = models.CharField(max_length=16, validators=[phone_validator])
    unit = models.ForeignKey(
        "properties.Unit", on_delete=models.SET_NULL, null=True, blank=True, related_name="estate_members"
    )
    house_label = models.CharField(max_length=60, blank=True, help_text=_("What they typed when joining."))
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.RESIDENT)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    payer = models.ForeignKey(
        "leasing.TenantProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="estate_memberships",
        help_text=_("Who dues are charged to (created on approval)."),
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    status_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("estate", "full_name")
        constraints = [
            models.UniqueConstraint(
                fields=["estate", "phone_number"],
                condition=~Q(status="removed"),
                name="estate_member_phone_once",
            )
        ]

    def __str__(self):
        return f"{self.full_name} ({self.estate})"

    @property
    def is_verified(self) -> bool:
        return self.status == self.Status.APPROVED


class DuesPlan(TimeStampedModel):
    """Recurring estate dues, charged to every verified resident from the period they joined."""

    estate = models.ForeignKey(Estate, on_delete=models.CASCADE, related_name="dues_plans")
    name = models.CharField(max_length=100, help_text=_("e.g. Security levy, Service charge"))
    amount = MoneyField()
    currency = CurrencyField(default="NGN")
    frequency = models.CharField(max_length=10, choices=Frequency.choices, default=Frequency.MONTHLY)
    start_date = models.DateField(help_text=_("First due date; later ones follow the frequency."))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("estate", "name")
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="dues_amount_positive")]

    def __str__(self):
        return f"{self.name} ({self.estate})"


class DuesCharge(models.Model):
    """Which charge was raised for which member and period (makes generation safe to rerun)."""

    id = models.BigAutoField(primary_key=True)
    plan = models.ForeignKey(DuesPlan, on_delete=models.CASCADE, related_name="charges")
    member = models.ForeignKey(EstateMember, on_delete=models.CASCADE, related_name="dues_charges")
    charge = models.OneToOneField("leasing.Charge", on_delete=models.CASCADE, related_name="dues_link")
    period_start = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["plan", "member", "period_start"], name="dues_once_per_period")
        ]

    def __str__(self):
        return f"{self.plan} {self.period_start}"


class DuesReminderLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    charge = models.ForeignKey("leasing.Charge", on_delete=models.CASCADE, related_name="+")
    stage = models.CharField(max_length=10)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["charge", "stage"], name="dues_reminder_once")]

    def __str__(self):
        return f"{self.charge_id} {self.stage}"


class Announcement(TimeStampedModel):
    class Audience(models.TextChoices):
        ALL = "all", _("Everyone")
        EXCO = "exco", _("Executive committee")

    estate = models.ForeignKey(Estate, on_delete=models.CASCADE, related_name="announcements")
    title = models.CharField(max_length=120)
    body = models.TextField(max_length=2000)
    audience = models.CharField(max_length=6, choices=Audience.choices, default=Audience.ALL)
    urgent = models.BooleanField(default=False, help_text=_("Also by SMS to everyone (costs SMS credit)."))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    push_sent = models.PositiveIntegerField(default=0)
    sms_sent = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-created_at",)


def _pass_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


class GatePass(TimeStampedModel):
    class Kind(models.TextChoices):
        VISITOR = "visitor", _("Visitor")
        ARTISAN = "artisan", _("Artisan")
        DELIVERY = "delivery", _("Delivery")

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        USED = "used", _("Used up")
        EXPIRED = "expired", _("Expired")
        CANCELLED = "cancelled", _("Cancelled")

    estate = models.ForeignKey(Estate, on_delete=models.CASCADE, related_name="gate_passes")
    host = models.ForeignKey(EstateMember, on_delete=models.CASCADE, related_name="gate_passes")
    visitor_name = models.CharField(max_length=120)
    visitor_phone = models.CharField(max_length=16, blank=True, validators=[phone_validator])
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.VISITOR)
    job = models.ForeignKey(
        "maintenance.Job",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gate_passes",
        help_text=_("For an artisan pass: the repair job (shows the Verified badge at the gate)."),
    )
    code = models.CharField(max_length=6, default=_pass_code)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    max_uses = models.PositiveSmallIntegerField(default=1)
    uses = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("-valid_from",)
        constraints = [
            models.UniqueConstraint(
                fields=["estate", "code"], condition=Q(status="active"), name="gate_code_unique_while_active"
            ),
            models.CheckConstraint(condition=Q(valid_to__gt=models.F("valid_from")), name="gate_pass_window"),
        ]

    def __str__(self):
        return f"{self.visitor_name} → {self.host}"


class GateEvent(TimeStampedModel):
    class Kind(models.TextChoices):
        CHECK_IN = "check_in", _("Checked in")
        CHECK_OUT = "check_out", _("Checked out")
        DENIED = "denied", _("Turned away")

    gate_pass = models.ForeignKey(GatePass, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("-created_at",)
