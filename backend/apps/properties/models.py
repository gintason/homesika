from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.core.money import MoneyField


class Property(TimeStampedModel):
    class Kind(models.TextChoices):
        BLOCK = "block", _("Block of flats")
        HOUSE = "house", _("House / duplex")
        COMPOUND = "compound", _("Compound (face-me-I-face-you)")
        COMMERCIAL = "commercial", _("Commercial / shops")
        MIXED = "mixed", _("Mixed use")
        OTHER = "other", _("Other")

    organization = models.ForeignKey("orgs.Organization", on_delete=models.CASCADE, related_name="properties")
    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.BLOCK)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    country = models.CharField(max_length=2, default="NG")
    notes = models.TextField(blank=True)
    is_archived = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "properties"
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="property_name_unique_in_org")
        ]

    def __str__(self):
        return self.name


class Unit(TimeStampedModel):
    class Kind(models.TextChoices):
        FLAT = "flat", _("Flat / apartment")
        ROOM = "room", _("Room / self-contain")
        HOUSE = "house", _("Whole house")
        SHOP = "shop", _("Shop")
        OFFICE = "office", _("Office")
        OTHER = "other", _("Other")

    class Status(models.TextChoices):
        VACANT = "vacant", _("Vacant")
        OCCUPIED = "occupied", _("Occupied")
        UNAVAILABLE = "unavailable", _("Unavailable (repairs etc.)")

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="units")
    label = models.CharField(max_length=60, help_text=_("e.g. Flat 2B, Shop 4"))
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.FLAT)
    bedrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    default_rent_amount = MoneyField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.VACANT, db_index=True)
    meter_number = models.CharField(
        max_length=30, blank=True, help_text=_("Prepaid meter, for bills (Phase 3).")
    )
    disco = models.CharField(max_length=40, blank=True, help_text=_("Electricity distribution company."))

    class Meta:
        ordering = ("property__name", "label")
        constraints = [
            models.UniqueConstraint(fields=["property", "label"], name="unit_label_unique_in_property")
        ]

    def __str__(self):
        return f"{self.property.name} · {self.label}"
