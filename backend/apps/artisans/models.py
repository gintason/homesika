import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.accounts.validators import phone_validator
from apps.core.fields import EncryptedTextField
from apps.core.models import TimeStampedModel


class Trade(models.TextChoices):
    """What an artisan does; also a repair ticket's category, so tickets can be matched to artisans."""

    PLUMBING = "plumbing", _("Plumbing")
    ELECTRICAL = "electrical", _("Electrical")
    CARPENTRY = "carpentry", _("Carpentry and doors")
    PAINTING = "painting", _("Painting")
    AC = "ac", _("Air conditioning")
    GENERATOR = "generator", _("Generator repair")
    ROOFING = "roofing", _("Roofing")
    TILING = "tiling", _("Tiling and masonry")
    WELDING = "welding", _("Welding and gates")
    APPLIANCE = "appliance", _("Appliance repair")
    PEST = "pest", _("Pest control")
    CLEANING = "cleaning", _("Cleaning")
    LOCKSMITH = "locksmith", _("Locks and keys")
    OTHER = "other", _("Other")


class ArtisanProfile(TimeStampedModel):
    """A person who does repairs. Not an organization member: what they see comes only from the jobs
    they're offered (address and tenant contact only once they accept)."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Checks in progress")
        VERIFIED = "verified", _("Verified")
        SUSPENDED = "suspended", _("Suspended")
        REMOVED = "removed", _("Removed")

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="artisan")
    display_name = models.CharField(max_length=120, help_text=_("Name or business name shown to landlords."))
    trades = models.JSONField(default=list)
    service_areas = models.JSONField(default=list, help_text=_("Areas they work in, e.g. Lekki, Ajah."))
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    address = EncryptedTextField(blank=True, help_text=_("Home or workshop address (encrypted)."))
    bio = models.CharField(max_length=300, blank=True)
    years_experience = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    status_reason = models.CharField(max_length=200, blank=True)
    is_available = models.BooleanField(default=True, help_text=_("Taking new jobs."))
    rating_sum = models.PositiveIntegerField(default=0)
    rating_count = models.PositiveIntegerField(default=0)
    jobs_completed = models.PositiveIntegerField(default=0)
    data_consent_at = models.DateTimeField(
        null=True, blank=True, help_text=_("When they agreed to ID and reference checks (NDPA).")
    )

    class Meta:
        ordering = ("display_name",)

    def __str__(self):
        return self.display_name

    @property
    def is_verified(self) -> bool:
        return self.status == self.Status.VERIFIED

    @property
    def rating_avg(self) -> float | None:
        return round(self.rating_sum / self.rating_count, 1) if self.rating_count else None


def private_storage():
    from apps.core.media import private_storage as storage

    return storage()


def id_document_path(instance, filename: str) -> str:
    return f"artisans/{instance.artisan_id}/id/{secrets.token_hex(16)}.jpg"


class VerificationCheck(TimeStampedModel):
    """One of the checks behind the Verified badge. One row per kind; attempts are counted on it."""

    class Kind(models.TextChoices):
        ID = "id", _("ID check")
        PHONE = "phone", _("Phone number")
        ADDRESS = "address", _("Address")

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", _("Not started")
        PENDING = "pending", _("Waiting for review")
        PASSED = "passed", _("Passed")
        FAILED = "failed", _("Failed")

    artisan = models.ForeignKey(ArtisanProfile, on_delete=models.CASCADE, related_name="checks")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NOT_STARTED)
    provider = models.CharField(max_length=20, blank=True, help_text=_("mock, manual, or the ID provider."))
    id_type = models.CharField(max_length=20, blank=True)
    id_number = EncryptedTextField(blank=True)
    id_number_last4 = models.CharField(max_length=4, blank=True)
    document = models.ImageField(
        upload_to=id_document_path, storage=private_storage, blank=True, help_text=_("Photo of the ID.")
    )
    evidence = EncryptedTextField(blank=True, help_text=_("What the provider returned (encrypted JSON)."))
    note = models.CharField(max_length=200, blank=True, help_text=_("Shown to the artisan when it fails."))
    attempts = models.PositiveSmallIntegerField(default=0)
    checked_at = models.DateTimeField(null=True, blank=True)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ("kind",)
        constraints = [models.UniqueConstraint(fields=["artisan", "kind"], name="one_check_per_kind")]

    def __str__(self):
        return f"{self.artisan} · {self.kind}: {self.status}"


class Voucher(TimeStampedModel):
    """A guarantor or a reference. They confirm by SMS link; the badge needs 2 guarantors and 1
    reference confirmed."""

    class Kind(models.TextChoices):
        GUARANTOR = "guarantor", _("Guarantor")
        REFERENCE = "reference", _("Reference")

    class Status(models.TextChoices):
        PENDING = "pending", _("Waiting for them to confirm")
        CONFIRMED = "confirmed", _("Confirmed")
        DECLINED = "declined", _("Declined")
        EXPIRED = "expired", _("Link expired")

    artisan = models.ForeignKey(ArtisanProfile, on_delete=models.CASCADE, related_name="vouchers")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    full_name = models.CharField(max_length=120)
    phone_number = models.CharField(max_length=16, validators=[phone_validator])
    relationship = models.CharField(max_length=80, help_text=_("e.g. uncle, former boss, past client."))
    occupation = models.CharField(max_length=80, blank=True)
    address = EncryptedTextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    link_sent_at = models.DateTimeField(null=True, blank=True)
    sends = models.PositiveSmallIntegerField(default=0)
    responded_at = models.DateTimeField(null=True, blank=True)
    comment = models.CharField(max_length=300, blank=True, help_text=_("What they said when confirming."))

    class Meta:
        ordering = ("kind", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=["artisan", "phone_number"],
                condition=~Q(status__in=["declined", "expired"]),
                name="voucher_phone_once_per_artisan",
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.full_name} for {self.artisan}"
