from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Notification(TimeStampedModel):
    """One message we send (receipt, reminder, alert): what, to whom, by which channel, and what happened."""

    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        EMAIL = "email", _("Email")
        PUSH = "push", _("Push")
        WHATSAPP = "whatsapp", "WhatsApp"

    class Status(models.TextChoices):
        QUEUED = "queued", _("Queued")
        SENT = "sent", _("Sent")
        FAILED = "failed", _("Failed")

    channel = models.CharField(max_length=8, choices=Channel.choices)
    kind = models.CharField(max_length=40, db_index=True, help_text=_("e.g. receipt, rent_reminder"))
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    organization = models.ForeignKey(
        "orgs.Organization", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    to = models.CharField(max_length=255)
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.QUEUED, db_index=True)
    provider_ref = models.CharField(max_length=100, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
