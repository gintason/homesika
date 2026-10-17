import secrets

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.artisans.models import Trade, private_storage
from apps.core.models import TimeStampedModel


def _reference() -> str:
    return "R" + secrets.token_hex(4).upper()


class Ticket(TimeStampedModel):
    """A repair request for a unit. Raised by the tenant (needs the landlord's approval) or by staff."""

    class Priority(models.TextChoices):
        LOW = "low", _("Can wait")
        NORMAL = "normal", _("Normal")
        URGENT = "urgent", _("Urgent")
        EMERGENCY = "emergency", _("Emergency (danger or flooding)")

    class Status(models.TextChoices):
        AWAITING_APPROVAL = "awaiting_approval", _("Waiting for landlord approval")
        APPROVED = "approved", _("Approved, finding an artisan")
        ASSIGNED = "assigned", _("Artisan assigned")
        IN_PROGRESS = "in_progress", _("Work in progress")
        DONE = "done", _("Done, waiting for tenant to confirm")
        CONFIRMED = "confirmed", _("Fixed and confirmed")
        REJECTED = "rejected", _("Not approved")
        CANCELLED = "cancelled", _("Cancelled")

    OPEN = (
        Status.AWAITING_APPROVAL,
        Status.APPROVED,
        Status.ASSIGNED,
        Status.IN_PROGRESS,
        Status.DONE,
    )
    CLOSED = (Status.CONFIRMED, Status.REJECTED, Status.CANCELLED)

    class Channel(models.TextChoices):
        APP = "app", _("App")
        WEB = "web", _("Web")
        WHATSAPP = "whatsapp", "WhatsApp"

    reference = models.CharField(max_length=12, unique=True, default=_reference, editable=False)
    organization = models.ForeignKey("orgs.Organization", on_delete=models.CASCADE, related_name="tickets")
    unit = models.ForeignKey("properties.Unit", on_delete=models.PROTECT, related_name="tickets")
    lease = models.ForeignKey(
        "leasing.Lease", on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets"
    )
    tenant = models.ForeignKey(
        "leasing.TenantProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets"
    )
    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="tickets_raised"
    )
    raised_by_staff = models.BooleanField(default=False)
    category = models.CharField(max_length=12, choices=Trade.choices)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    title = models.CharField(max_length=120)
    description = models.TextField(max_length=2000)
    access_notes = models.CharField(
        max_length=200, blank=True, help_text=_("When the artisan can come in, e.g. 'after 4pm, call first'.")
    )
    status = models.CharField(
        max_length=18, choices=Status.choices, default=Status.AWAITING_APPROVAL, db_index=True
    )
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.APP)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    closed_reason = models.CharField(
        max_length=300, blank=True, help_text=_("Why it was rejected/cancelled.")
    )
    done_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    auto_confirmed = models.BooleanField(default=False)
    confirm_reminder_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["organization", "status", "-created_at"])]

    def __str__(self):
        return f"{self.reference} {self.title}"

    @property
    def is_open(self) -> bool:
        return self.status in self.OPEN

    @property
    def current_job(self):
        jobs = getattr(self, "_prefetched_objects_cache", {}).get("jobs")
        rows = jobs if jobs is not None else self.jobs.all()
        return next((j for j in rows if j.status in Job.ACTIVE), None)


def ticket_photo_path(instance, filename: str) -> str:
    t = instance.ticket
    return f"tickets/{t.organization_id}/{t.pk}/{secrets.token_hex(16)}.jpg"


class TicketPhoto(TimeStampedModel):
    class Stage(models.TextChoices):
        REPORT = "report", _("The problem")
        COMPLETION = "completion", _("The finished work")

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to=ticket_photo_path, storage=private_storage)
    stage = models.CharField(max_length=10, choices=Stage.choices, default=Stage.REPORT)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )

    class Meta:
        ordering = ("created_at",)


class TicketEvent(TimeStampedModel):
    """The ticket's timeline. `internal` notes are for staff only (never shown to tenant or artisan)."""

    class Kind(models.TextChoices):
        CREATED = "created", _("Reported")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Not approved")
        ASSIGNED = "assigned", _("Artisan asked to take the job")
        ACCEPTED = "accepted", _("Artisan accepted")
        DECLINED = "declined", _("Artisan declined")
        OFFER_EXPIRED = "offer_expired", _("Artisan didn't answer in time")
        SCHEDULED = "scheduled", _("Visit time set")
        STARTED = "started", _("Artisan arrived")
        COMPLETED = "completed", _("Artisan marked it done")
        RESOLVED = "resolved", _("Marked fixed by the landlord")
        CONFIRMED = "confirmed", _("Tenant confirmed it's fixed")
        REOPENED = "reopened", _("Tenant says it's not fixed")
        CANCELLED = "cancelled", _("Cancelled")
        COMMENT = "comment", _("Comment")
        RATED = "rated", _("Rated")

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=14, choices=Kind.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    actor_role = models.CharField(max_length=10, blank=True, help_text=_("tenant, staff, artisan or system."))
    note = models.CharField(max_length=1000, blank=True)
    internal = models.BooleanField(default=False)

    class Meta:
        ordering = ("created_at",)


class Job(TimeStampedModel):
    """An artisan's part of a ticket. One active job per ticket; a declined or cancelled one stays as
    history."""

    class Status(models.TextChoices):
        OFFERED = "offered", _("Offered")
        ACCEPTED = "accepted", _("Accepted")
        DECLINED = "declined", _("Declined")
        ON_SITE = "on_site", _("On site")
        COMPLETED = "completed", _("Completed, waiting for tenant")
        CONFIRMED = "confirmed", _("Confirmed by tenant")
        CANCELLED = "cancelled", _("Cancelled")

    ACTIVE = (Status.OFFERED, Status.ACCEPTED, Status.ON_SITE, Status.COMPLETED)

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="jobs")
    organization = models.ForeignKey("orgs.Organization", on_delete=models.CASCADE, related_name="jobs")
    artisan = models.ForeignKey("artisans.ArtisanProfile", on_delete=models.PROTECT, related_name="jobs")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OFFERED, db_index=True)
    offered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    offer_note = models.CharField(max_length=300, blank=True)
    offer_expires_at = models.DateTimeField()
    responded_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.CharField(max_length=300, blank=True)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_note = models.CharField(max_length=1000, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["ticket"],
                condition=Q(status__in=["offered", "accepted", "on_site", "completed"]),
                name="one_active_job_per_ticket",
            )
        ]

    def __str__(self):
        return f"{self.ticket.reference} · {self.artisan} ({self.status})"


class Rating(TimeStampedModel):
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="rating")
    rater = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    score = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(score__gte=1) & Q(score__lte=5), name="rating_score_1_to_5")
        ]
