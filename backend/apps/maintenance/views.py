from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.artisans.models import ArtisanProfile
from apps.core.idempotency import idempotent
from apps.orgs.permissions import OrgScopedMixin
from apps.properties.models import Unit

from . import services
from .models import Job, Ticket, TicketEvent, TicketPhoto
from .serializers import (
    ArtisanJobSerializer,
    AssignSerializer,
    CommentSerializer,
    DeclineSerializer,
    EventSerializer,
    NoteSerializer,
    PhotoUploadSerializer,
    RateSerializer,
    ReasonSerializer,
    ReportSerializer,
    ScheduleSerializer,
    StaffCreateSerializer,
    TicketPhotoSerializer,
    TicketSerializer,
)


class TicketThrottle(UserRateThrottle):
    scope = "tickets"


def _ticket_qs(qs):
    return qs.select_related("unit__property", "organization", "tenant", "raised_by").prefetch_related(
        "photos",
        Prefetch("events", queryset=TicketEvent.objects.select_related("actor__artisan")),
        Prefetch("jobs", queryset=Job.objects.select_related("artisan__user", "rating")),
    )


def _body(serializer_class, request) -> dict:
    s = serializer_class(data=request.data)
    s.is_valid(raise_exception=True)
    return s.validated_data


def _photo(request, ticket, stage=TicketPhoto.Stage.REPORT):
    upload = _body(PhotoUploadSerializer, request)["image"]
    photo = services.add_photo(ticket, upload, by=request.user, stage=stage)
    return Response(
        TicketPhotoSerializer(photo, context={"request": request}).data, status=status.HTTP_201_CREATED
    )


STATUS_FILTER = OpenApiParameter(
    "status", str, description="open (default), closed, all, or one status, e.g. awaiting_approval"
)


def _filter_status(qs, value):
    if value in ("", "open"):
        return qs.filter(status__in=Ticket.OPEN)
    if value == "closed":
        return qs.filter(status__in=Ticket.CLOSED)
    if value == "all":
        return qs
    return qs.filter(status=value)


# ---- Tenant -------------------------------------------------------------------------------------


class MyTicketViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """My repair requests (as a tenant)."""

    queryset = Ticket.objects.none()  # schema generation only
    serializer_class = TicketSerializer
    cursor_ordering = ("-created_at",)
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return _ticket_qs(services.tenant_tickets(self.request.user))

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "viewer": "tenant"}

    @extend_schema(parameters=[STATUS_FILTER])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def filter_queryset(self, queryset):
        if self.action != "list":
            return queryset
        return _filter_status(queryset, self.request.query_params.get("status", "all"))

    def _ok(self, ticket, code=status.HTTP_200_OK):
        ticket = _ticket_qs(Ticket.objects.filter(pk=ticket.pk)).get()
        return Response(self.get_serializer(ticket).data, status=code)

    @extend_schema(request=ReportSerializer, responses={201: TicketSerializer})
    @idempotent
    def create(self, request, *args, **kwargs):
        data = _body(ReportSerializer, request)
        ticket = services.report(
            user=request.user, lease_id=data.pop("lease"), channel=Ticket.Channel.APP, request=request, **data
        )
        return self._ok(ticket, status.HTTP_201_CREATED)

    def get_throttles(self):
        return [TicketThrottle()] if self.action == "create" else super().get_throttles()

    @extend_schema(
        request={"multipart/form-data": PhotoUploadSerializer}, responses={201: TicketPhotoSerializer}
    )
    @action(detail=True, methods=["post"])
    def photos(self, request, pk=None):
        return _photo(request, self.get_object())

    @extend_schema(request=ReasonSerializer, responses=TicketSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        reason = _body(ReasonSerializer, request)["reason"]
        return self._ok(services.cancel(self.get_object(), by=request.user, role="tenant", reason=reason))

    @extend_schema(request=None, responses=TicketSerializer)
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        return self._ok(services.confirm(self.get_object(), by=request.user, role="tenant", request=request))

    @extend_schema(request=NoteSerializer, responses=TicketSerializer)
    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        note = _body(NoteSerializer, request)["note"]
        return self._ok(services.reopen(self.get_object(), by=request.user, note=note, request=request))

    @extend_schema(request=RateSerializer, responses=TicketSerializer)
    @action(detail=True, methods=["post"])
    def rate(self, request, pk=None):
        ticket = self.get_object()
        services.rate(ticket, by=request.user, **_body(RateSerializer, request))
        return self._ok(ticket)

    @extend_schema(request=NoteSerializer, responses={201: EventSerializer})
    @action(detail=True, methods=["post"])
    def comments(self, request, pk=None):
        ticket = self.get_object()
        if not ticket.is_open:
            raise services.WrongState()
        event = services.comment(
            ticket, by=request.user, role="tenant", note=_body(NoteSerializer, request)["note"]
        )
        return Response(EventSerializer(event).data, status=status.HTTP_201_CREATED)


# ---- Staff --------------------------------------------------------------------------------------


class OrgTicketViewSet(
    OrgScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Repair requests for the organization's units. ?status=open|closed|all|<status>&property=&q="""

    queryset = Ticket.objects.none()
    serializer_class = TicketSerializer
    capability_scope = "maintenance"
    cursor_ordering = ("-created_at",)
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    capabilities = {
        "list": "maintenance.view",
        "retrieve": "maintenance.view",
        "create": "maintenance.manage",
        "approve": "maintenance.approve",
        "reject": "maintenance.approve",
        "assign": "maintenance.manage",
        "cancel": "maintenance.manage",
        "resolve": "maintenance.manage",
        "comments": "maintenance.manage",
        "photos": "maintenance.manage",
        "confirm": "maintenance.manage",
    }

    def get_queryset(self):
        return _ticket_qs(Ticket.objects.filter(organization=self.org))

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "viewer": "staff"}

    def filter_queryset(self, queryset):
        if self.action != "list":
            return queryset
        p = self.request.query_params
        qs = _filter_status(queryset, p.get("status", "open"))
        if p.get("property"):
            qs = qs.filter(unit__property_id=p["property"])
        if p.get("q"):
            q = p["q"].strip()[:60]
            qs = qs.filter(
                Q(title__icontains=q) | Q(reference__iexact=q.lstrip("#")) | Q(tenant__full_name__icontains=q)
            )
        return qs

    @extend_schema(parameters=[STATUS_FILTER, OpenApiParameter("property", str), OpenApiParameter("q", str)])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def _ok(self, ticket, code=status.HTTP_200_OK):
        ticket = _ticket_qs(Ticket.objects.filter(pk=ticket.pk)).get()
        return Response(self.get_serializer(ticket).data, status=code)

    @extend_schema(request=StaffCreateSerializer, responses={201: TicketSerializer})
    @idempotent
    def create(self, request, *args, **kwargs):
        data = _body(StaffCreateSerializer, request)
        unit = get_object_or_404(
            Unit.objects.select_related("property"), pk=data.pop("unit"), property__organization=self.org
        )
        ticket = services.staff_create(org=self.org, by=request.user, unit=unit, request=request, **data)
        return self._ok(ticket, status.HTTP_201_CREATED)

    @extend_schema(request=NoteSerializer, responses=TicketSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, *args, **kwargs):
        note = _body(NoteSerializer, request)["note"]
        return self._ok(services.approve(self.get_object(), by=request.user, note=note, request=request))

    @extend_schema(request=ReasonSerializer, responses=TicketSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, *args, **kwargs):
        reason = _body(ReasonSerializer, request)["reason"]
        return self._ok(services.reject(self.get_object(), by=request.user, reason=reason, request=request))

    @extend_schema(request=AssignSerializer, responses=TicketSerializer)
    @action(detail=True, methods=["post"])
    def assign(self, request, *args, **kwargs):
        data = _body(AssignSerializer, request)
        artisan = ArtisanProfile.objects.filter(pk=data["artisan"]).first()
        if artisan is None:
            from rest_framework import serializers

            raise serializers.ValidationError({"artisan": ["Choose a verified artisan who is taking jobs."]})
        ticket = self.get_object()
        services.assign(ticket, artisan=artisan, by=request.user, note=data["note"], request=request)
        return self._ok(ticket)

    @extend_schema(request=ReasonSerializer, responses=TicketSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, *args, **kwargs):
        reason = _body(ReasonSerializer, request)["reason"]
        return self._ok(
            services.cancel(self.get_object(), by=request.user, role="staff", reason=reason, request=request)
        )

    @extend_schema(request=NoteSerializer, responses=TicketSerializer)
    @action(detail=True, methods=["post"])
    def resolve(self, request, *args, **kwargs):
        note = _body(NoteSerializer, request)["note"]
        return self._ok(services.resolve(self.get_object(), by=request.user, note=note, request=request))

    @extend_schema(request=None, responses=TicketSerializer)
    @action(detail=True, methods=["post"])
    def confirm(self, request, *args, **kwargs):
        """Only for tickets with no tenant in the app to confirm it."""
        ticket = self.get_object()
        if ticket.tenant is not None and ticket.tenant.user_id is not None:
            raise services.WrongState()
        return self._ok(services.confirm(ticket, by=request.user, role="staff", request=request))

    @extend_schema(request=CommentSerializer, responses={201: EventSerializer})
    @action(detail=True, methods=["post"])
    def comments(self, request, *args, **kwargs):
        data = _body(CommentSerializer, request)
        event = services.comment(self.get_object(), by=request.user, role="staff", **data)
        return Response(EventSerializer(event).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request={"multipart/form-data": PhotoUploadSerializer}, responses={201: TicketPhotoSerializer}
    )
    @action(detail=True, methods=["post"])
    def photos(self, request, *args, **kwargs):
        return _photo(request, self.get_object())


# ---- Artisan -------------------------------------------------------------------------------------


class MyJobViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """My jobs (as an artisan). ?status=active (default) or history"""

    queryset = Job.objects.none()  # schema generation only
    serializer_class = ArtisanJobSerializer
    cursor_ordering = ("-created_at",)
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        qs = (
            services.artisan_jobs(self.request.user)
            .select_related(
                "organization", "ticket__unit__property", "ticket__tenant", "ticket__raised_by", "rating"
            )
            .prefetch_related("ticket__photos", "ticket__events__actor__artisan")
        )
        if self.action == "list":
            if self.request.query_params.get("status", "active") == "history":
                return qs.exclude(status__in=Job.ACTIVE)
            return qs.filter(status__in=Job.ACTIVE)
        return qs

    @extend_schema(parameters=[OpenApiParameter("status", str, enum=["active", "history"])])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def _ok(self, job):
        return Response(self.get_serializer(self.get_queryset().get(pk=job.pk)).data)

    @extend_schema(request=ScheduleSerializer, responses=ArtisanJobSerializer)
    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        when = _body(ScheduleSerializer, request).get("scheduled_for")
        return self._ok(services.accept(self.get_object(), scheduled_for=when))

    @extend_schema(request=DeclineSerializer, responses=ArtisanJobSerializer)
    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        return self._ok(
            services.decline(self.get_object(), reason=_body(DeclineSerializer, request)["reason"])
        )

    @extend_schema(request=ScheduleSerializer, responses=ArtisanJobSerializer)
    @action(detail=True, methods=["post"])
    def schedule(self, request, pk=None):
        when = _body(ScheduleSerializer, request).get("scheduled_for")
        if when is None:
            from rest_framework import serializers

            raise serializers.ValidationError({"scheduled_for": ["Choose a day and time."]})
        return self._ok(services.reschedule(self.get_object(), scheduled_for=when))

    @extend_schema(request=None, responses=ArtisanJobSerializer)
    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        return self._ok(services.start(self.get_object()))

    @extend_schema(request=NoteSerializer, responses=ArtisanJobSerializer)
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return self._ok(services.complete(self.get_object(), note=_body(NoteSerializer, request)["note"]))

    @extend_schema(
        request={"multipart/form-data": PhotoUploadSerializer}, responses={201: TicketPhotoSerializer}
    )
    @action(detail=True, methods=["post"])
    def photos(self, request, pk=None):
        job = self.get_object()
        if job.status not in (Job.Status.ACCEPTED, Job.Status.ON_SITE):
            raise services.WrongState()
        return _photo(request, job.ticket, stage=TicketPhoto.Stage.COMPLETION)

    @extend_schema(request=NoteSerializer, responses={201: EventSerializer})
    @action(detail=True, methods=["post"])
    def comments(self, request, pk=None):
        job = self.get_object()
        if job.status not in (Job.Status.ACCEPTED, Job.Status.ON_SITE, Job.Status.COMPLETED):
            raise services.WrongState()
        event = services.comment(
            job.ticket, by=request.user, role="artisan", note=_body(NoteSerializer, request)["note"]
        )
        return Response(EventSerializer(event).data, status=status.HTTP_201_CREATED)
