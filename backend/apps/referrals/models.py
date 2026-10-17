import secrets

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I/L


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(7))


class ReferralCode(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referral_code"
    )
    code = models.CharField(max_length=12, unique=True, default=new_code)

    def __str__(self):
        return self.code


class Referral(TimeStampedModel):
    """Who invited whom. It qualifies when the new person makes a first real purchase or payment."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Joined, no purchase yet")
        QUALIFIED = "qualified", _("Qualified, reward given")
        CAPPED = "capped", _("Qualified, monthly reward limit reached")
        REJECTED = "rejected", _("Rejected")

    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referrals_made"
    )
    referred = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referred_by"
    )
    code = models.CharField(max_length=12)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    qualified_at = models.DateTimeField(null=True, blank=True)
    qualified_by = models.CharField(max_length=20, blank=True, help_text=_("bill or rent_payment"))
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        indexes = [models.Index(fields=["referrer", "status", "qualified_at"])]

    def __str__(self):
        return f"{self.referrer_id} -> {self.referred_id} ({self.status})"


class FeeWaiver(TimeStampedModel):
    """One waived Homesika service fee on a bill purchase (electricity or cable TV). A discount on our own
    fee, not money: it has no cash value and can't be withdrawn or transferred (no stored value)."""

    class Reason(models.TextChoices):
        JOINED_WITH_CODE = "joined", _("Joined with a referral code")
        REFERRED_SOMEONE = "referrer", _("Invited someone who joined")
        GOODWILL = "goodwill", _("Given by Homesika support")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="fee_waivers")
    reason = models.CharField(max_length=10, choices=Reason.choices)
    referral = models.ForeignKey(
        Referral, on_delete=models.SET_NULL, null=True, blank=True, related_name="waivers"
    )
    expires_at = models.DateTimeField()
    order = models.OneToOneField(
        "bills.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fee_waiver",
        help_text=_("The order it was used on (released again if that order isn't paid or is refunded)."),
    )
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("expires_at",)
        indexes = [models.Index(fields=["user", "order", "expires_at"])]
