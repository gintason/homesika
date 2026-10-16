from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.accounts.validators import phone_validator
from apps.core.models import TimeStampedModel
from apps.core.money import CurrencyField


class Organization(TimeStampedModel):
    """The tenancy boundary: a landlord's business, an agency, an estate association, or Homesika itself."""

    class Kind(models.TextChoices):
        LANDLORD = "landlord", _("Landlord / property owner")
        AGENCY = "agency", _("Agency / property manager")
        ESTATE = "estate", _("Estate association")
        PLATFORM = "platform", _("Homesika platform")

    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.LANDLORD)
    country = models.CharField(max_length=2, default="NG")
    currency = CurrencyField(default="NGN")
    timezone = models.CharField(max_length=40, default="Africa/Lagos")
    phone_number = models.CharField(max_length=16, blank=True, validators=[phone_validator])
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    def __str__(self):
        return self.name


class Role(models.TextChoices):
    OWNER = "owner", _("Owner")
    MANAGER = "manager", _("Manager")
    AGENT = "agent", _("Agent")
    ACCOUNTANT = "accountant", _("Accountant")
    ESTATE_ADMIN = "estate_admin", _("Estate admin")
    SECURITY = "security", _("Security desk")
    VIEWER = "viewer", _("Viewer (read only)")


class Membership(TimeStampedModel):
    """Staff access to an organization. Tenants, residents and artisans are NOT members: they are linked
    by data (lease, estate membership, job), so they can never see an organization's other records."""

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        INVITED = "invited", _("Invited (no account yet)")
        REMOVED = "removed", _("Removed")

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="memberships"
    )
    invited_phone = models.CharField(max_length=16, blank=True, validators=[phone_validator])
    role = models.CharField(max_length=12, choices=Role.choices)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"],
                condition=Q(user__isnull=False),
                name="membership_unique_user",
            ),
            models.UniqueConstraint(
                fields=["organization", "invited_phone"],
                condition=Q(status="invited"),
                name="membership_unique_invite",
            ),
            models.CheckConstraint(
                condition=Q(user__isnull=False) | ~Q(invited_phone=""), name="membership_has_user_or_phone"
            ),
        ]

    def __str__(self):
        return f"{self.user or self.invited_phone} @ {self.organization} ({self.role})"
