from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Language(models.TextChoices):
    ENGLISH = "en", _("English")
    PIDGIN = "pcm", _("Nigerian Pidgin")


class Contact(TimeStampedModel):
    """A WhatsApp sender. Linked to a Homesika user when the phone number matches one."""

    class OptIn(models.TextChoices):
        UNKNOWN = "unknown", _("Not asked")
        OPTED_IN = "opted_in", _("Opted in")
        OPTED_OUT = "opted_out", _("Opted out")

    wa_id = models.CharField(max_length=20, unique=True, help_text=_("WhatsApp id (digits of the phone)."))
    phone_number = models.CharField(max_length=16, db_index=True)
    name = models.CharField(max_length=120, blank=True, help_text=_("WhatsApp profile name."))
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="wa_contacts"
    )
    opt_in = models.CharField(max_length=10, choices=OptIn.choices, default=OptIn.UNKNOWN)
    opted_in_at = models.DateTimeField(null=True, blank=True)
    opted_out_at = models.DateTimeField(null=True, blank=True)
    language = models.CharField(max_length=3, choices=Language.choices, default=Language.ENGLISH)
    last_inbound_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.phone_number


class Conversation(TimeStampedModel):
    """A thread with one person on one channel. On WhatsApp there is one open thread per contact."""

    class Channel(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        APP = "app", _("Mobile app")
        WEB = "web", _("Web dashboard")

    class Status(models.TextChoices):
        BOT = "bot", _("Assistant replying")
        HANDOFF = "handoff", _("A person has taken over")
        CLOSED = "closed", _("Closed")

    channel = models.CharField(max_length=8, choices=Channel.choices)
    contact = models.ForeignKey(
        Contact, on_delete=models.CASCADE, null=True, blank=True, related_name="conversations"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="conversations",
    )
    organization = models.ForeignKey(
        "orgs.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversations",
        help_text=_("The organization whose staff handle this thread (set on escalation or enquiry)."),
    )
    language = models.CharField(max_length=3, choices=Language.choices, default=Language.ENGLISH)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.BOT, db_index=True)
    handoff_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    handoff_at = models.DateTimeField(null=True, blank=True)
    last_inbound_at = models.DateTimeField(null=True, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["contact"],
                condition=Q(channel="whatsapp") & ~Q(status="closed"),
                name="one_open_whatsapp_thread_per_contact",
            )
        ]

    def __str__(self):
        return f"{self.channel}:{self.pk}"


class Message(TimeStampedModel):
    class Direction(models.TextChoices):
        INBOUND = "in", _("From the person")
        OUTBOUND = "out", _("To the person")

    class Sender(models.TextChoices):
        PERSON = "person", _("The person")
        ASSISTANT = "assistant", _("Assistant")
        STAFF = "staff", _("Staff member")
        SYSTEM = "system", _("Automatic message")

    class Status(models.TextChoices):
        RECEIVED = "received", _("Received")
        QUEUED = "queued", _("Queued")
        SENT = "sent", _("Sent")
        DELIVERED = "delivered", _("Delivered")
        READ = "read", _("Read")
        FAILED = "failed", _("Failed")

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    direction = models.CharField(max_length=3, choices=Direction.choices)
    sender = models.CharField(max_length=10, choices=Sender.choices)
    kind = models.CharField(
        max_length=20, default="text", help_text=_("text, template, interactive, media...")
    )
    body = models.TextField(blank=True)
    template_name = models.CharField(max_length=80, blank=True)
    provider_message_id = models.CharField(max_length=128, null=True, blank=True, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, db_index=True)
    error = models.CharField(max_length=255, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    notification = models.ForeignKey(
        "notifications.Notification", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ("created_at",)

    def __str__(self):
        return f"{self.direction}:{self.body[:30]}"


class Escalation(TimeStampedModel):
    """A conversation that needs a person: disputes, payment problems, emergencies, complaints..."""

    class Reason(models.TextChoices):
        DISPUTE = "dispute", _("Dispute")
        PAYMENT_PROBLEM = "payment_problem", _("Payment problem")
        EMERGENCY = "emergency", _("Emergency")
        USER_REQUEST = "user_request", _("Asked for a person")
        COMPLAINT = "complaint", _("Complaint")
        LOW_CONFIDENCE = "low_confidence", _("Assistant couldn't help")
        LIMIT = "limit", _("Usage limit reached")
        REFUSAL = "refusal", _("Assistant declined")

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        ASSIGNED = "assigned", _("Being handled")
        RESOLVED = "resolved", _("Resolved")

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="escalations")
    organization = models.ForeignKey(
        "orgs.Organization", on_delete=models.SET_NULL, null=True, blank=True, related_name="escalations"
    )
    reason = models.CharField(max_length=16, choices=Reason.choices)
    summary = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.reason}:{self.status}"
