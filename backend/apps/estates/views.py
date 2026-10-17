from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.core.idempotency import idempotent
from apps.orgs.permissions import OrgScopedMixin

from . import services
from .models import Announcement, DuesPlan, Estate, EstateMember, GatePass
from .serializers import (
    AnnouncementSerializer,
    ApproveSerializer,
    DuesPlanSerializer,
    EstateCreateSerializer,
    EstateSerializer,
    GateCheckSerializer,
    GateEventSerializer,
    GateNoteSerializer,
    GatePassCreateSerializer,
    GatePassSerializer,
    GateVerifySerializer,
    HousesAddedSerializer,
    HouseSerializer,
    HousesSerializer,
    JoinSerializer,
    MemberCreateSerializer,
    MemberReasonSerializer,
    MemberSerializer,
    MyEstateSerializer,
)

ESTATE_FILTER = OpenApiParameter("estate", str, description="Only this estate")


def _body(serializer_class, request) -> dict:
    s = serializer_class(data=request.data)
    s.is_valid(raise_exception=True)
    return s.validated_data


class JoinThrottle(UserRateThrottle):
    scope = "estate_join"


class GateThrottle(UserRateThrottle):
    scope = "gate_verify"


def _by_estate(qs, request):
    estate = request.query_params.get("estate")
    return qs.filter(estate_id=estate) if estate else qs


# ---- Estate office --------------------------------------------------------------------------------


class EstateViewSet(
    OrgScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Estate.objects.none()
    serializer_class = EstateSerializer
    capability_scope = "estate"
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return Estate.objects.filter(organization=self.org).select_related("property")

    @extend_schema(request=EstateCreateSerializer, responses={201: EstateSerializer})
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        data = _body(EstateCreateSerializer, request)
        houses = data.pop("houses")
        estate = services.create_estate(org=self.org, by=request.user, request=request, **data)
        services.add_houses(estate, houses)
        return Response(EstateSerializer(estate).data, status=status.HTTP_201_CREATED)

    @extend_schema(methods=["get"], responses=HouseSerializer(many=True))
    @extend_schema(methods=["post"], request=HousesSerializer, responses={201: HousesAddedSerializer})
    @action(detail=True, methods=["get", "post"])
    def houses(self, request, *args, **kwargs):
        estate = self.get_object()
        if request.method == "POST":
            created = services.add_houses(estate, _body(HousesSerializer, request)["labels"])
            return Response({"created": created}, status=status.HTTP_201_CREATED)
        return Response(HouseSerializer(estate.property.units.order_by("label"), many=True).data)

    @extend_schema(request=None, responses=EstateSerializer)
    @action(detail=True, methods=["post"], url_path="regenerate-code")
    def regenerate_code(self, request, *args, **kwargs):
        return Response(EstateSerializer(services.regenerate_code(self.get_object())).data)


class MemberViewSet(
    OrgScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Residents. ?estate=&status=pending|approved|suspended|removed"""

    queryset = EstateMember.objects.none()
    serializer_class = MemberSerializer
    capability_scope = "estate"
    cursor_ordering = ("full_name", "id")

    def get_queryset(self):
        return EstateMember.objects.filter(estate__organization=self.org).select_related("unit")

    def filter_queryset(self, queryset):
        if self.action != "list":
            return queryset
        qs = _by_estate(queryset, self.request)
        st = self.request.query_params.get("status")
        return qs.filter(status=st) if st else qs.exclude(status=EstateMember.Status.REMOVED)

    @extend_schema(parameters=[ESTATE_FILTER, OpenApiParameter("status", str)])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=MemberCreateSerializer, responses={201: MemberSerializer})
    def create(self, request, *args, **kwargs):
        data = _body(MemberCreateSerializer, request)
        estate = get_object_or_404(Estate, pk=data.pop("estate"), organization=self.org)
        member = services.add_member(
            estate=estate, by=request.user, unit_id=data.pop("unit"), request=request, **data
        )
        return Response(MemberSerializer(member).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ApproveSerializer, responses=MemberSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, *args, **kwargs):
        data = _body(ApproveSerializer, request)
        member = services.approve(
            self.get_object(),
            by=request.user,
            unit_id=data.get("unit"),
            role=data.get("role"),
            request=request,
        )
        return Response(MemberSerializer(member).data)

    def _status(self, request, new):
        member = self.get_object()
        if member.status == EstateMember.Status.REMOVED:
            raise serializers.ValidationError({"status": ["This resident was removed."]})
        reason = _body(MemberReasonSerializer, request)["reason"]
        return Response(
            MemberSerializer(
                services.set_status(member, status_=new, by=request.user, reason=reason, request=request)
            ).data
        )

    @extend_schema(request=MemberReasonSerializer, responses=MemberSerializer)
    @action(detail=True, methods=["post"])
    def suspend(self, request, *args, **kwargs):
        return self._status(request, EstateMember.Status.SUSPENDED)

    @extend_schema(request=MemberReasonSerializer, responses=MemberSerializer)
    @action(detail=True, methods=["post"])
    def remove(self, request, *args, **kwargs):
        return self._status(request, EstateMember.Status.REMOVED)


class DuesPlanViewSet(
    OrgScopedMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Estate dues. Creating or changing a plan raises charges for verified residents straight away."""

    queryset = DuesPlan.objects.none()
    serializer_class = DuesPlanSerializer
    capability_scope = "estate"
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return DuesPlan.objects.filter(estate__organization=self.org)

    def filter_queryset(self, queryset):
        return _by_estate(queryset, self.request) if self.action == "list" else queryset

    @extend_schema(parameters=[ESTATE_FILTER])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def _check_estate(self, serializer):
        estate = serializer.validated_data.get("estate")
        if estate is not None and estate.organization_id != self.org.pk:
            raise serializers.ValidationError({"estate": ["Choose one of your estates."]})

    def perform_create(self, serializer):
        self._check_estate(serializer)
        plan = serializer.save()
        services.generate_dues(estate=plan.estate)

    def perform_update(self, serializer):
        if "estate" in serializer.validated_data:
            raise serializers.ValidationError({"estate": ["A plan can't move to another estate."]})
        plan = serializer.save()
        services.generate_dues(estate=plan.estate)


class AnnouncementViewSet(
    OrgScopedMixin, mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    queryset = Announcement.objects.none()
    serializer_class = AnnouncementSerializer
    capability_scope = "estate"
    cursor_ordering = ("-created_at",)

    def get_queryset(self):
        return Announcement.objects.filter(estate__organization=self.org)

    def filter_queryset(self, queryset):
        return _by_estate(queryset, self.request) if self.action == "list" else queryset

    @extend_schema(parameters=[ESTATE_FILTER])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @idempotent
    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        estate = s.validated_data["estate"]
        if estate.organization_id != self.org.pk:
            raise serializers.ValidationError({"estate": ["Choose one of your estates."]})
        a = services.announce(by=request.user, request=request, **s.validated_data)
        return Response(self.get_serializer(a).data, status=status.HTTP_201_CREATED)


class GateViewSet(OrgScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """The gate: verify a code, check visitors in and out. GET lists today's and recent passes (the log)."""

    queryset = GatePass.objects.none()
    serializer_class = GateCheckSerializer
    capability_scope = "gate"
    cursor_ordering = ("-valid_from", "id")
    capabilities = {
        "list": "gate.verify",
        "retrieve": "gate.verify",
        "verify": "gate.verify",
        "check_in": "gate.verify",
        "check_out": "gate.verify",
        "deny": "gate.verify",
    }

    def get_queryset(self):
        return (
            GatePass.objects.filter(estate__organization=self.org)
            .select_related("host__unit", "job__artisan", "job__ticket")
            .prefetch_related("events__by")
        )

    def filter_queryset(self, queryset):
        if self.action != "list":
            return queryset
        qs = _by_estate(queryset, self.request)
        st = self.request.query_params.get("status")
        return qs.filter(status=st) if st else qs

    @extend_schema(parameters=[ESTATE_FILTER, OpenApiParameter("status", str)])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_throttles(self):
        return [GateThrottle()] if self.action == "verify" else super().get_throttles()

    def _ok(self, gp):
        return Response(GateCheckSerializer(self.get_queryset().get(pk=gp.pk)).data)

    @extend_schema(request=GateVerifySerializer, responses=GateCheckSerializer)
    @action(detail=False, methods=["post"])
    def verify(self, request, *args, **kwargs):
        data = _body(GateVerifySerializer, request)
        estate = get_object_or_404(Estate, pk=data["estate"], organization=self.org)
        return self._ok(services.find_pass(estate, data["code"]))

    @extend_schema(request=GateNoteSerializer, responses=GateCheckSerializer)
    @action(detail=True, methods=["post"], url_path="check-in")
    def check_in(self, request, *args, **kwargs):
        note = _body(GateNoteSerializer, request)["note"]
        return self._ok(services.check_in(self.get_object(), by=request.user, note=note))

    @extend_schema(request=GateNoteSerializer, responses={201: GateEventSerializer})
    @action(detail=True, methods=["post"], url_path="check-out")
    def check_out(self, request, *args, **kwargs):
        e = services.check_out(
            self.get_object(), by=request.user, note=_body(GateNoteSerializer, request)["note"]
        )
        return Response(GateEventSerializer(e).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=GateNoteSerializer, responses={201: GateEventSerializer})
    @action(detail=True, methods=["post"])
    def deny(self, request, *args, **kwargs):
        e = services.deny(self.get_object(), by=request.user, note=_body(GateNoteSerializer, request)["note"])
        return Response(GateEventSerializer(e).data, status=status.HTTP_201_CREATED)


# ---- Residents ------------------------------------------------------------------------------------


class MyEstateViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Estates I belong to (or asked to join)."""

    queryset = EstateMember.objects.none()
    serializer_class = MyEstateSerializer

    def get_queryset(self):
        return (
            EstateMember.objects.filter(user=self.request.user, estate__is_active=True)
            .exclude(status=EstateMember.Status.REMOVED)
            .select_related("estate", "unit")
        )

    def get_throttles(self):
        return [JoinThrottle()] if self.action == "join" else super().get_throttles()

    @extend_schema(request=JoinSerializer, responses={201: MyEstateSerializer})
    @action(detail=False, methods=["post"])
    def join(self, request):
        data = _body(JoinSerializer, request)
        member = services.join(user=request.user, code=data["code"], house=data["house"], request=request)
        return Response(MyEstateSerializer(member).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        parameters=[OpenApiParameter("estate", str, required=True)],
        responses=AnnouncementSerializer(many=True),
    )
    @action(detail=False, methods=["get"])
    def announcements(self, request):
        member = services.member_of(request.user, request.query_params.get("estate"))
        if member is None:
            return Response([])
        qs = Announcement.objects.filter(estate=member.estate)
        if member.role != EstateMember.Role.EXCO:
            qs = qs.filter(audience=Announcement.Audience.ALL)
        return Response(AnnouncementSerializer(qs[:50], many=True).data)


class MyGatePassViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Gate passes I made for my visitors."""

    queryset = GatePass.objects.none()
    serializer_class = GatePassSerializer
    cursor_ordering = ("-valid_from", "id")

    def get_queryset(self):
        return GatePass.objects.filter(host__user=self.request.user).select_related("estate")

    def filter_queryset(self, queryset):
        if self.action != "list":
            return queryset
        if self.request.query_params.get("status", "active") == "active":
            services.expire_passes()
            return queryset.filter(status=GatePass.Status.ACTIVE)
        return queryset

    @extend_schema(parameters=[OpenApiParameter("status", str, enum=["active", "all"])])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=GatePassCreateSerializer, responses={201: GatePassSerializer})
    @idempotent
    def create(self, request, *args, **kwargs):
        data = _body(GatePassCreateSerializer, request)
        member = services.member_of(request.user, data.pop("estate"))
        if member is None:
            raise serializers.ValidationError({"estate": ["Only verified residents can create gate passes."]})
        gp = services.create_pass(member=member, job_id=data.pop("job", None), **data)
        return Response(GatePassSerializer(gp).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=GatePassSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return Response(GatePassSerializer(services.cancel_pass(self.get_object())).data)
