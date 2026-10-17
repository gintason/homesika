from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.estates.models import Estate
from apps.orgs.permissions import OrgScopedMixin

from . import services
from .models import AlertDelivery, IncidentNote, PanicAlert
from .serializers import (
    AlertDetailSerializer,
    AlertNoteSerializer,
    AlertSerializer,
    CloseSerializer,
    DeliveryReportSerializer,
    IncidentNoteSerializer,
    KindSerializer,
    MyAlertSerializer,
    TriggerSerializer,
)


def _body(serializer_class, request) -> dict:
    s = serializer_class(data=request.data)
    s.is_valid(raise_exception=True)
    return s.validated_data


def _alert_qs(qs):
    return qs.select_related("estate", "member__unit", "raised_by")


# ---- The person raising it ------------------------------------------------------------------------


class MyAlertViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Panic alerts I raised. POST raises one (safe to retry with the same client_id)."""

    queryset = PanicAlert.objects.none()
    serializer_class = MyAlertSerializer
    cursor_ordering = ("-created_at",)

    def get_queryset(self):
        if self.action == "received":
            # anyone the alert was sent to can say they got it
            return PanicAlert.objects.filter(deliveries__user=self.request.user).distinct()
        return _alert_qs(PanicAlert.objects.filter(raised_by=self.request.user).exclude(kind="drill"))

    @extend_schema(request=TriggerSerializer, responses={201: MyAlertSerializer, 200: MyAlertSerializer})
    def create(self, request, *args, **kwargs):
        data = _body(TriggerSerializer, request)
        estate = get_object_or_404(Estate, pk=data["estate"])
        alert, created = services.raise_alert(
            user=request.user,
            estate=estate,
            kind=data["kind"],
            silent=data["silent"],
            location=data.get("location"),
            client_id=data.get("client_id", ""),
            channel="app"
            if "Expo" in request.headers.get("User-Agent", "") or request.headers.get("X-Client") == "mobile"
            else "web",
        )
        return Response(
            MyAlertSerializer(alert).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

    @extend_schema(request=KindSerializer, responses=MyAlertSerializer)
    @action(detail=True, methods=["post"])
    def kind(self, request, pk=None):
        alert = services.set_kind(
            self.get_object(), kind=_body(KindSerializer, request)["kind"], by=request.user
        )
        return Response(MyAlertSerializer(alert).data)

    @extend_schema(request=None, responses=MyAlertSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """'I'm safe now'."""
        alert = services.close(
            self.get_object(), by=request.user, outcome=PanicAlert.Status.CANCELLED, note=""
        )
        return Response(MyAlertSerializer(alert).data)

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=["post"])
    def received(self, request, pk=None):
        """The app calls this when an alert push is opened or shown, so the desk knows it reached you."""
        services.received(self.get_object(), user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---- The security desk ----------------------------------------------------------------------------


STATUS_FILTER = OpenApiParameter("status", str, description="open (default), closed or all")
ESTATE_FILTER = OpenApiParameter("estate", str, description="Only this estate")


class OrgAlertViewSet(
    OrgScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Panic alerts in the organization's estates."""

    queryset = PanicAlert.objects.none()
    serializer_class = AlertSerializer
    capability_scope = "security"
    cursor_ordering = ("-created_at",)
    capabilities = {
        "list": "security.view",
        "retrieve": "security.view",
        "report": "security.view",
        "acknowledge": "security.respond",
        "respond": "security.respond",
        "resolve": "security.respond",
        "false_alarm": "security.respond",
        "notes": "security.respond",
        "kind": "security.respond",
        "drill": "estate.manage",
    }

    def get_queryset(self):
        qs = _alert_qs(PanicAlert.objects.filter(estate__organization=self.org))
        if self.action == "retrieve":
            qs = qs.prefetch_related(
                Prefetch("notes", queryset=IncidentNote.objects.select_related("author")),
                Prefetch("deliveries", queryset=AlertDelivery.objects.select_related("user")),
            )
        return qs

    def get_serializer_class(self):
        return AlertDetailSerializer if self.action != "list" else AlertSerializer

    def filter_queryset(self, queryset):
        if self.action != "list":
            return queryset
        p = self.request.query_params
        if p.get("estate"):
            queryset = queryset.filter(estate_id=p["estate"])
        value = p.get("status", "open")
        if value == "open":
            return queryset.filter(status__in=PanicAlert.OPEN)
        if value == "closed":
            return queryset.exclude(status__in=PanicAlert.OPEN)
        return queryset

    @extend_schema(parameters=[STATUS_FILTER, ESTATE_FILTER])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def _ok(self, alert):
        self.action = "retrieve"
        return Response(AlertDetailSerializer(self.get_queryset().get(pk=alert.pk)).data)

    @extend_schema(request=None, responses=AlertDetailSerializer)
    @action(detail=True, methods=["post"])
    def acknowledge(self, request, *args, **kwargs):
        return self._ok(services.acknowledge(self.get_object(), by=request.user))

    @extend_schema(request=AlertNoteSerializer, responses=AlertDetailSerializer)
    @action(detail=True, methods=["post"])
    def respond(self, request, *args, **kwargs):
        note = _body(AlertNoteSerializer, request)["note"]
        return self._ok(services.respond(self.get_object(), by=request.user, note=note))

    @extend_schema(request=CloseSerializer, responses=AlertDetailSerializer)
    @action(detail=True, methods=["post"])
    def resolve(self, request, *args, **kwargs):
        note = _body(CloseSerializer, request)["note"]
        return self._ok(services.close(self.get_object(), by=request.user, outcome="resolved", note=note))

    @extend_schema(request=CloseSerializer, responses=AlertDetailSerializer)
    @action(detail=True, methods=["post"], url_path="false-alarm")
    def false_alarm(self, request, *args, **kwargs):
        note = _body(CloseSerializer, request)["note"]
        return self._ok(services.close(self.get_object(), by=request.user, outcome="false_alarm", note=note))

    @extend_schema(request=KindSerializer, responses=AlertDetailSerializer)
    @action(detail=True, methods=["post"])
    def kind(self, request, *args, **kwargs):
        kind = _body(KindSerializer, request)["kind"]
        return self._ok(services.set_kind(self.get_object(), kind=kind, by=request.user))

    @extend_schema(request=CloseSerializer, responses={201: IncidentNoteSerializer})
    @action(detail=True, methods=["post"])
    def notes(self, request, *args, **kwargs):
        n = services.add_note(
            self.get_object(), by=request.user, note=_body(CloseSerializer, request)["note"]
        )
        return Response(IncidentNoteSerializer(n).data, status=status.HTTP_201_CREATED)

    def _estate(self):
        estate_id = self.request.query_params.get("estate") or self.request.data.get("estate")
        return get_object_or_404(Estate, pk=estate_id, organization=self.org) if estate_id else None

    @extend_schema(
        parameters=[OpenApiParameter("estate", str, required=True)],
        request=None,
        responses={201: AlertDetailSerializer},
    )
    @action(detail=False, methods=["post"])
    def drill(self, request, *args, **kwargs):
        """Send a clearly marked TEST alert to security and managers to prove delivery works."""
        estate = self._estate()
        if estate is None:
            from rest_framework import serializers

            raise serializers.ValidationError({"estate": ["Choose an estate."]})
        alert = services.drill(estate=estate, by=request.user)
        resp = self._ok(alert)
        resp.status_code = status.HTTP_201_CREATED
        return resp

    @extend_schema(
        parameters=[OpenApiParameter("estate", str, required=True), OpenApiParameter("days", int)],
        responses=DeliveryReportSerializer,
    )
    @action(detail=False, methods=["get"])
    def report(self, request, *args, **kwargs):
        estate = self._estate()
        if estate is None:
            from rest_framework import serializers

            raise serializers.ValidationError({"estate": ["Choose an estate."]})
        try:
            days = max(1, min(365, int(request.query_params.get("days", 30))))
        except ValueError:
            days = 30
        return Response(services.delivery_report(estate, days=days))
