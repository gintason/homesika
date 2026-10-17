"""
One ticket, three viewers. The serializer context's `viewer` decides what's shown:

* staff:   everything, including internal notes and the artisan's phone once they've accepted.
* tenant:  their own ticket; no internal notes; the artisan's name, badge and rating (phone once accepted).
* artisan: the job; before accepting only the area and the problem, after accepting the address and the
           tenant's first name and phone so they can get in.
"""

from rest_framework import serializers

from apps.artisans.models import Trade
from apps.core.media import signed_url

from .models import Job, Ticket, TicketEvent, TicketPhoto

KNOWS_CONTACT = (Job.Status.ACCEPTED, Job.Status.ON_SITE, Job.Status.COMPLETED, Job.Status.CONFIRMED)


class TicketPhotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField(help_text="A link that works for about 15 minutes.")

    class Meta:
        model = TicketPhoto
        fields = ("id", "stage", "url", "created_at")

    def get_url(self, obj) -> str | None:
        return signed_url(self.context.get("request"), obj.image.name)


class EventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = TicketEvent
        fields = ("id", "kind", "actor_role", "actor_name", "note", "internal", "created_at")

    def get_actor_name(self, obj) -> str:
        if obj.actor is None:
            return ""
        if obj.actor_role == "artisan" and hasattr(obj.actor, "artisan"):
            return obj.actor.artisan.display_name
        return obj.actor.first_name or ""


class ArtisanBriefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    display_name = serializers.CharField()
    is_verified = serializers.BooleanField()
    rating_avg = serializers.FloatField(allow_null=True)
    rating_count = serializers.IntegerField()
    jobs_completed = serializers.IntegerField()
    phone_number = serializers.CharField(allow_null=True, help_text="Only once they've accepted.")


class JobBriefSerializer(serializers.ModelSerializer):
    artisan = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = (
            "id",
            "status",
            "artisan",
            "offer_expires_at",
            "scheduled_for",
            "started_at",
            "completed_at",
            "completion_note",
        )

    def get_artisan(self, obj) -> ArtisanBriefSerializer:
        a = obj.artisan
        return {
            "id": a.pk,
            "display_name": a.display_name,
            "is_verified": a.is_verified,
            "rating_avg": a.rating_avg,
            "rating_count": a.rating_count,
            "jobs_completed": a.jobs_completed,
            "phone_number": a.user.phone_number if obj.status in KNOWS_CONTACT else None,
        }


class RatingBriefSerializer(serializers.Serializer):
    score = serializers.IntegerField()
    comment = serializers.CharField()


class TicketSerializer(serializers.ModelSerializer):
    unit = serializers.SerializerMethodField()
    tenant = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()
    events = serializers.SerializerMethodField()
    job = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    can = serializers.SerializerMethodField(help_text="What the viewer can do next.")

    class Meta:
        model = Ticket
        fields = (
            "id",
            "reference",
            "status",
            "category",
            "priority",
            "title",
            "description",
            "access_notes",
            "channel",
            "raised_by_staff",
            "unit",
            "tenant",
            "closed_reason",
            "approved_at",
            "done_at",
            "confirmed_at",
            "auto_confirmed",
            "created_at",
            "updated_at",
            "photos",
            "job",
            "rating",
            "events",
            "can",
        )

    @property
    def viewer(self) -> str:
        return self.context.get("viewer", "tenant")

    def get_unit(self, obj) -> dict:
        p = obj.unit.property
        return {
            "id": str(obj.unit.pk),
            "label": obj.unit.label,
            "property": p.name,
            "address": p.address,
            "city": p.city,
            "organization": obj.organization.name,
        }

    def get_tenant(self, obj) -> dict | None:
        if self.viewer != "staff" or obj.tenant is None:
            return None
        return {
            "id": str(obj.tenant.pk),
            "full_name": obj.tenant.full_name,
            "phone_number": obj.tenant.phone_number,
        }

    def get_photos(self, obj) -> TicketPhotoSerializer(many=True):
        return TicketPhotoSerializer(obj.photos.all(), many=True, context=self.context).data

    def get_events(self, obj) -> EventSerializer(many=True):
        rows = [e for e in obj.events.all() if self.viewer == "staff" or not e.internal]
        return EventSerializer(rows, many=True, context=self.context).data

    def _job(self, obj):
        jobs = list(obj.jobs.all())
        active = next((j for j in jobs if j.status in Job.ACTIVE or j.status == Job.Status.CONFIRMED), None)
        return active

    def get_job(self, obj) -> JobBriefSerializer(allow_null=True):
        job = self._job(obj)
        return JobBriefSerializer(job, context=self.context).data if job else None

    def get_rating(self, obj) -> RatingBriefSerializer(allow_null=True):
        job = self._job(obj)
        r = getattr(job, "rating", None) if job else None
        return {"score": r.score, "comment": r.comment} if r else None

    def get_can(self, obj) -> list[str]:
        S = Ticket.Status
        s, out = obj.status, []
        if self.viewer == "staff":
            if s == S.AWAITING_APPROVAL:
                out += ["approve", "reject", "resolve"]
            if s == S.APPROVED:
                out += ["assign", "reject", "resolve"]
            if s == S.ASSIGNED:
                job = self._job(obj)
                if job and job.status in (Job.Status.OFFERED, Job.Status.ACCEPTED):
                    out.append("reassign")
            if s == S.DONE and (obj.tenant is None or obj.tenant.user_id is None):
                out.append("confirm")  # no tenant in the app to do it
            if obj.is_open:
                out += ["cancel", "comment", "photo"]
        else:
            if s in (S.AWAITING_APPROVAL, S.APPROVED):
                out.append("cancel")
            if s == S.DONE:
                out += ["confirm", "reopen"]
            if s == S.CONFIRMED and self._job(obj) is not None and self.get_rating(obj) is None:
                out.append("rate")
            if obj.is_open:
                out += ["comment", "photo"]
        return out


class ReportSerializer(serializers.Serializer):
    lease = serializers.UUIDField(help_text="One of the tenant's active leases (GET /me/leases/).")
    category = serializers.ChoiceField(choices=Trade.choices)
    priority = serializers.ChoiceField(choices=Ticket.Priority.choices, default=Ticket.Priority.NORMAL)
    title = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=2000)
    access_notes = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class StaffCreateSerializer(serializers.Serializer):
    unit = serializers.UUIDField()
    category = serializers.ChoiceField(choices=Trade.choices)
    priority = serializers.ChoiceField(choices=Ticket.Priority.choices, default=Ticket.Priority.NORMAL)
    title = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=2000)
    access_notes = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class NoteSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class CommentSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=1000)
    internal = serializers.BooleanField(
        default=False, help_text="Staff only: hidden from tenant and artisan."
    )


class AssignSerializer(serializers.Serializer):
    artisan = serializers.UUIDField()
    note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class RateSerializer(serializers.Serializer):
    score = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class PhotoUploadSerializer(serializers.Serializer):
    image = serializers.ImageField()


class ScheduleSerializer(serializers.Serializer):
    scheduled_for = serializers.DateTimeField(required=False, allow_null=True)


class DeclineSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class ArtisanJobSerializer(serializers.ModelSerializer):
    ticket = serializers.SerializerMethodField()
    organization = serializers.CharField(source="organization.name")
    location = serializers.SerializerMethodField()
    contact = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    can = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = (
            "id",
            "status",
            "organization",
            "offer_note",
            "offer_expires_at",
            "scheduled_for",
            "started_at",
            "completed_at",
            "completion_note",
            "confirmed_at",
            "created_at",
            "ticket",
            "location",
            "contact",
            "rating",
            "can",
        )

    def get_ticket(self, obj) -> dict:
        t = obj.ticket
        return {
            "id": str(t.pk),
            "reference": t.reference,
            "status": t.status,
            "category": t.category,
            "priority": t.priority,
            "title": t.title,
            "description": t.description,
            "access_notes": t.access_notes if obj.status in KNOWS_CONTACT else "",
            "photos": TicketPhotoSerializer(t.photos.all(), many=True, context=self.context).data,
            "events": EventSerializer(
                [e for e in t.events.all() if not e.internal and e.created_at >= obj.created_at],
                many=True,
                context=self.context,
            ).data,
        }

    def get_location(self, obj) -> dict:
        p = obj.ticket.unit.property
        loc = {"area": p.city or p.state, "state": p.state}
        if obj.status in KNOWS_CONTACT:
            loc.update(address=p.address, property=p.name, unit=obj.ticket.unit.label)
        return loc

    def get_contact(self, obj) -> dict | None:
        if obj.status not in KNOWS_CONTACT or obj.status == Job.Status.CONFIRMED:
            return None
        t = obj.ticket
        if t.tenant is not None:
            return {"name": t.tenant.full_name.split()[0], "phone_number": t.tenant.phone_number}
        staff = t.raised_by
        return {"name": staff.first_name, "phone_number": staff.phone_number} if staff else None

    def get_rating(self, obj) -> RatingBriefSerializer(allow_null=True):
        r = getattr(obj, "rating", None)
        return {"score": r.score, "comment": r.comment} if r else None

    def get_can(self, obj) -> list[str]:
        J = Job.Status
        return {
            J.OFFERED: ["accept", "decline"],
            J.ACCEPTED: ["schedule", "start", "complete", "comment", "photo"],
            J.ON_SITE: ["complete", "comment", "photo"],
            J.COMPLETED: ["comment"],
        }.get(obj.status, [])
