from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class KbArticle(TimeStampedModel):
    """Knowledge base: curated FAQs and how-tos the assistant may quote. organization = null means
    platform-wide (written by Homesika); an organization can add its own (house rules, payment details)."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")

    organization = models.ForeignKey(
        "orgs.Organization", on_delete=models.CASCADE, null=True, blank=True, related_name="kb_articles"
    )
    slug = models.SlugField(max_length=80)
    title = models.CharField(max_length=160)
    body = models.TextField()
    language = models.CharField(max_length=3, default="en")
    audience = models.JSONField(
        default=list, blank=True, help_text=_('Roles that may see it; [] = everyone. e.g. ["tenant"]')
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PUBLISHED, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "slug", "language"], name="kb_unique_slug_language"
            )
        ]

    def __str__(self):
        return self.title


class AssistantState(TimeStampedModel):
    """The model-facing history of a conversation's current session, replayed unchanged on every call
    (append-only; thinking and tool blocks included). A new session starts after inactivity or length."""

    conversation = models.OneToOneField(
        "messaging.Conversation", on_delete=models.CASCADE, related_name="assistant"
    )
    session = models.PositiveIntegerField(default=1)
    session_started_at = models.DateTimeField(auto_now_add=True)
    history = models.JSONField(default=list, blank=True)
    context = models.JSONField(
        default=dict, blank=True, help_text=_("e.g. the last listing a prospect looked at.")
    )


class AssistantTurn(TimeStampedModel):
    """One model call: what it cost and what happened. No message text is stored here."""

    conversation = models.ForeignKey(
        "messaging.Conversation", on_delete=models.CASCADE, related_name="assistant_turns"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    organization = models.ForeignKey(
        "orgs.Organization", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    sender = models.CharField(
        max_length=40, blank=True, db_index=True, help_text=_("Phone or user id, for limits.")
    )
    model = models.CharField(max_length=60)
    stop_reason = models.CharField(max_length=30, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cache_read_tokens = models.PositiveIntegerField(default=0)
    cache_write_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    tools = models.JSONField(default=list, blank=True)
    flags = models.JSONField(
        default=list, blank=True, help_text=_("Guardrail events, e.g. output_filtered, refusal.")
    )
    refusal_category = models.CharField(max_length=40, blank=True)
    fallback_used = models.BooleanField(default=False)
    error = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["sender", "created_at"]),
            models.Index(fields=["organization", "created_at"]),
        ]


class PendingAction(TimeStampedModel):
    """Something the assistant proposed that only runs after the person says yes."""

    class Status(models.TextChoices):
        PROPOSED = "proposed", _("Waiting for confirmation")
        EXECUTED = "executed", _("Done")
        REJECTED = "rejected", _("Cancelled")
        EXPIRED = "expired", _("Expired")
        FAILED = "failed", _("Failed")

    conversation = models.ForeignKey(
        "messaging.Conversation", on_delete=models.CASCADE, related_name="pending_actions"
    )
    tool = models.CharField(max_length=60)
    arguments = models.JSONField(default=dict)
    summary = models.CharField(max_length=300)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PROPOSED, db_index=True)
    expires_at = models.DateTimeField()
    decided_at = models.DateTimeField(null=True, blank=True)
    result = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.tool}:{self.status}"
