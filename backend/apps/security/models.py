from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.fields import EncryptedTextField
from apps.core.models import TimeStampedModel


class PanicAlert(TimeStampedModel):
    class Kind(models.TextChoices):
        HELP = "help", _("Help needed")  # sent at once on the hold; the person can say more after
        ROBBERY = "robbery", _("Robbery / break-in")
        KIDNAPPING = "kidnapping", _("Kidnapping")
        FIRE = "fire", _("Fire")
        MEDICAL = "medical", _("Medical emergency")
        SUSPICIOUS = "suspicious_person", _("Suspicious person")
        DRILL = "drill", _("Test (drill)")

    class Status(models.TextChoices):
        TRIGGERED = "triggered", _("Raised")
        ACKNOWLEDGED = "acknowledged", _("Seen by security")
        RESPONDING = "responding", _("Security on the way")
        RESOLVED = "resolved", _("Resolved")
        FALSE_ALARM = "false_alarm", _("False alarm")
        CANCELLED = "cancelled", _("Cancelled by the resident")

    OPEN = (Status.TRIGGERED, Status.ACKNOWLEDGED, Status.RESPONDING)

    estate = models.ForeignKey("estates.Estate", on_delete=models.CASCADE, related_name="alerts")
    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="alerts_raised"
    )
    member = models.ForeignKey(
        "estates.EstateMember", on_delete=models.SET_NULL, null=True, blank=True, related_name="alerts"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.HELP)
    silent = models.BooleanField(default=False, help_text=_("Only security and managers are told; no sound."))
    location = EncryptedTextField(blank=True, help_text=_("JSON {lat, lng, accuracy}; only with consent."))
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.TRIGGERED, db_index=True)
    client_id = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        help_text=_("The phone's id for this alert, so a retry doesn't raise a second one."),
    )
    channel = models.CharField(max_length=10, default="app", help_text=_("app, web or whatsapp"))
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    responding_at = models.DateTimeField(null=True, blank=True)
    responding_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    close_note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["estate", "status", "-created_at"])]

    def __str__(self):
        return f"{self.get_kind_display()} @ {self.estate} ({self.status})"

    @property
    def is_open(self) -> bool:
        return self.status in self.OPEN


class AlertDelivery(TimeStampedModel):
    """One attempt to reach one person on one channel. 'delivered' means the phone or SMS provider
    confirmed it; 'acknowledged' means the person reacted in the app."""

    class Channel(models.TextChoices):
        PUSH = "push", _("Push")
        SMS = "sms", "SMS"
        WS = "ws", _("Security desk screen")

    class Status(models.TextChoices):
        QUEUED = "queued", _("Queued")
        SENT = "sent", _("Sent")
        DELIVERED = "delivered", _("Delivered")
        ACKNOWLEDGED = "acknowledged", _("Seen")
        FAILED = "failed", _("Failed")

    class Audience(models.TextChoices):
        STAFF = "staff", _("Security / estate staff")
        RESIDENT = "resident", _("Resident")
        RAISER = "raiser", _("The person who raised it")

    alert = models.ForeignKey(PanicAlert, on_delete=models.CASCADE, related_name="deliveries")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    phone_number = models.CharField(max_length=16, blank=True)
    audience = models.CharField(max_length=10, choices=Audience.choices)
    channel = models.CharField(max_length=6, choices=Channel.choices)
    status = models.CharField(max_length=13, choices=Status.choices, default=Status.QUEUED, db_index=True)
    push_token = models.CharField(max_length=200, blank=True)
    provider_ref = models.CharField(max_length=120, blank=True)
    notification = models.ForeignKey(
        "notifications.Notification", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    error = models.CharField(max_length=200, blank=True)
    fallback_for = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [models.Index(fields=["channel", "status", "created_at"])]


class IncidentNote(TimeStampedModel):
    alert = models.ForeignKey(PanicAlert, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    kind = models.CharField(max_length=14, default="note", help_text=_("note, or the status it moved to"))
    note = models.CharField(max_length=1000, blank=True)

    class Meta:
        ordering = ("created_at",)
