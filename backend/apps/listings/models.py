import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.core.money import CurrencyField, MoneyField


def new_listing_ref() -> str:
    return "LST-" + secrets.token_hex(3).upper()


def photo_path(instance, filename: str) -> str:
    ext = (filename.rsplit(".", 1)[-1] or "jpg").lower()[:5]
    return f"listings/{instance.listing.organization_id}/{instance.listing_id}/{secrets.token_hex(8)}.{ext}"


class Listing(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")
        LET = "let", _("Let (no longer available)")
        ARCHIVED = "archived", _("Archived")

    class Period(models.TextChoices):
        YEAR = "year", _("per year")
        MONTH = "month", _("per month")

    organization = models.ForeignKey("orgs.Organization", on_delete=models.CASCADE, related_name="listings")
    unit = models.ForeignKey(
        "properties.Unit", on_delete=models.SET_NULL, null=True, blank=True, related_name="listings"
    )
    ref = models.CharField(max_length=20, unique=True, default=new_listing_ref)
    title = models.CharField(max_length=140)
    description = models.TextField(blank=True)
    whatsapp_caption = models.TextField(blank=True, help_text=_("Short text for sharing on WhatsApp."))
    features = models.JSONField(default=list, blank=True)
    area = models.CharField(max_length=80, db_index=True, help_text=_("Neighbourhood, e.g. Lekki, Yaba."))
    city = models.CharField(max_length=80, default="Lagos")
    address = models.CharField(
        max_length=255, blank=True, help_text=_("Shown only after a viewing is booked.")
    )
    bedrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    bathrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    rent_amount = MoneyField()
    rent_period = models.CharField(max_length=5, choices=Period.choices, default=Period.YEAR)
    currency = CurrencyField(default="NGN")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    ai_generated = models.BooleanField(default=False)
    contact_phone = models.CharField(max_length=16, blank=True, help_text=_("Who prospects can call."))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ("-published_at", "-created_at")
        constraints = [models.CheckConstraint(condition=Q(rent_amount__gt=0), name="listing_rent_positive")]

    def __str__(self):
        return f"{self.ref} {self.title}"


class ListingPhoto(TimeStampedModel):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to=photo_path)
    position = models.PositiveSmallIntegerField(default=0)
    caption = models.CharField(max_length=140, blank=True)

    class Meta:
        ordering = ("position", "created_at")

    def __str__(self):
        return self.image.name


class ViewingSlot(TimeStampedModel):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="slots")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    capacity = models.PositiveSmallIntegerField(default=1)
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ("starts_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")), name="slot_ends_after_start"
            )
        ]

    def __str__(self):
        return f"{self.listing.ref} {self.starts_at:%Y-%m-%d %H:%M}"


class Lead(TimeStampedModel):
    class Stage(models.TextChoices):
        NEW = "new", _("New")
        CONTACTED = "contacted", _("Contacted")
        VIEWING_BOOKED = "viewing_booked", _("Viewing booked")
        VIEWED = "viewed", _("Viewed")
        APPLIED = "applied", _("Applied")
        WON = "won", _("Became a tenant")
        LOST = "lost", _("Lost")

    class Source(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        WEB = "web", _("Listing page")
        APP = "app", _("App")
        MANUAL = "manual", _("Added by staff")

    organization = models.ForeignKey("orgs.Organization", on_delete=models.CASCADE, related_name="leads")
    listing = models.ForeignKey(
        Listing, on_delete=models.SET_NULL, null=True, blank=True, related_name="leads"
    )
    contact = models.ForeignKey(
        "messaging.Contact", on_delete=models.SET_NULL, null=True, blank=True, related_name="leads"
    )
    name = models.CharField(max_length=120, blank=True)
    phone_number = models.CharField(max_length=16, db_index=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.WHATSAPP)
    stage = models.CharField(max_length=16, choices=Stage.choices, default=Stage.NEW, db_index=True)
    message = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=["listing", "phone_number"], name="one_lead_per_phone_per_listing")
        ]

    def __str__(self):
        return f"{self.name or self.phone_number} ({self.stage})"


class Viewing(TimeStampedModel):
    class Status(models.TextChoices):
        BOOKED = "booked", _("Booked")
        DONE = "done", _("Done")
        NO_SHOW = "no_show", _("Didn't come")
        CANCELLED = "cancelled", _("Cancelled")

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="viewings")
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="viewings")
    slot = models.ForeignKey(ViewingSlot, on_delete=models.PROTECT, related_name="viewings")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.BOOKED, db_index=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("slot__starts_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["lead", "slot"],
                condition=~Q(status="cancelled"),
                name="one_booking_per_lead_per_slot",
            )
        ]

    def __str__(self):
        return f"{self.lead} @ {self.slot}"
