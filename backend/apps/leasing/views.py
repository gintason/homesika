from django.db.models import Prefetch, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core import audit
from apps.core.money import to_major
from apps.orgs.permissions import OrgScopedMixin
from apps.properties.views import OrgContextMixin

from . import services
from .models import Charge, Lease, TenantProfile
from .serializers import (
    ChargeSerializer,
    EndLeaseSerializer,
    LeaseSerializer,
    MyLeaseSerializer,
    TenantSerializer,
    WaiveSerializer,
)


class TenantViewSet(OrgScopedMixin, OrgContextMixin, viewsets.ModelViewSet):
    queryset = TenantProfile.objects.none()  # schema generation only; get_queryset() scopes to the org
    serializer_class = TenantSerializer
    capability_scope = "tenant"
    pagination_class = None

    def get_queryset(self):
        qs = TenantProfile.objects.filter(organization=self.org).prefetch_related(
            Prefetch("leases", queryset=Lease.objects.select_related("unit__property"))
        )
        q = self.request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(Q(full_name__icontains=q) | Q(phone_number__icontains=q))
        return qs

    def perform_create(self, serializer):
        serializer.instance = services.create_tenant(
            org=self.org, by=self.request.user, request=self.request, **serializer.validated_data
        )

    def perform_destroy(self, instance):
        if instance.leases.exists():
            from rest_framework import serializers

            raise serializers.ValidationError(
                {"tenant": ["This tenant has lease records and can't be deleted."]}
            )
        instance.delete()


class LeaseViewSet(OrgScopedMixin, OrgContextMixin, viewsets.ModelViewSet):
    queryset = Lease.objects.none()  # schema generation only; get_queryset() scopes to the org
    serializer_class = LeaseSerializer
    capability_scope = "lease"
    capabilities = {"list": "tenant.view", "retrieve": "tenant.view"}
    http_method_names = ["get", "post", "patch", "delete"]
    pagination_class = None

    def get_queryset(self):
        outstanding = Sum("charges__amount", filter=Q(charges__status__in=Charge.OUTSTANDING)) - Sum(
            "charges__amount_paid", filter=Q(charges__status__in=Charge.OUTSTANDING)
        )
        qs = (
            Lease.objects.filter(organization=self.org)
            .select_related("unit__property", "tenant")
            .annotate(balance=outstanding)
        )
        for param in ("status", "unit", "tenant"):
            value = self.request.query_params.get(param)
            if value:
                qs = qs.filter(**{param: value})
        return qs

    def perform_create(self, serializer):
        activate = serializer.validated_data.pop("activate", False)
        lease = serializer.save(organization=self.org, currency=self.org.currency)
        if activate:
            lease = services.activate_lease(lease, by=self.request.user, request=self.request)
        serializer.instance = self.get_queryset().get(pk=lease.pk)

    def perform_update(self, serializer):
        serializer.validated_data.pop("activate", None)
        serializer.save()

    def perform_destroy(self, instance):
        if instance.status != Lease.Status.DRAFT:
            from rest_framework import serializers

            raise serializers.ValidationError(
                {"status": ["Only a draft lease can be deleted. End it instead."]}
            )
        instance.delete()

    @action(detail=True, methods=["post"])
    def activate(self, request, *args, **kwargs):
        lease = services.activate_lease(self.get_object(), by=request.user, request=request)
        return Response(self.get_serializer(self.get_queryset().get(pk=lease.pk)).data)

    @action(detail=True, methods=["post"])
    def end(self, request, *args, **kwargs):
        s = EndLeaseSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        lease = services.end_lease(
            self.get_object(),
            on=s.validated_data["ended_on"],
            terminated=s.validated_data["terminated"],
            by=request.user,
            request=request,
        )
        return Response(self.get_serializer(self.get_queryset().get(pk=lease.pk)).data)


class ChargeViewSet(OrgScopedMixin, OrgContextMixin, viewsets.ModelViewSet):
    """Charges of the org. ?status=outstanding|paid|..., ?overdue=1, ?lease=, ?tenant=, ?unit=."""

    queryset = Charge.objects.none()  # schema generation only; get_queryset() scopes to the org
    serializer_class = ChargeSerializer
    capability_scope = "charge"
    capabilities = {
        "list": "tenant.view",
        "retrieve": "tenant.view",
        "create": "charge.manage",
        "waive": "charge.manage",
    }
    http_method_names = ["get", "post"]

    def get_queryset(self):
        qs = Charge.objects.filter(organization=self.org).select_related("tenant", "unit__property")
        params = self.request.query_params
        status_ = params.get("status")
        if status_ == "outstanding":
            qs = qs.filter(status__in=Charge.OUTSTANDING)
        elif status_:
            qs = qs.filter(status=status_)
        if params.get("overdue") == "1":
            qs = qs.filter(status__in=Charge.OUTSTANDING, due_date__lt=timezone.localdate())
        for param in ("lease", "tenant", "unit"):
            if params.get(param):
                qs = qs.filter(**{param: params[param]})
        return qs.order_by("due_date", "kind")

    def perform_create(self, serializer):
        lease = serializer.validated_data["lease"]
        charge = serializer.save(
            organization=self.org, unit=lease.unit, tenant=lease.tenant, currency=lease.currency
        )
        audit.record(
            "charge.created",
            actor=self.request.user,
            organization=self.org,
            obj=charge,
            changes={"amount": charge.amount, "kind": charge.kind},
            request=self.request,
        )

    @action(detail=True, methods=["post"])
    def waive(self, request, *args, **kwargs):
        s = WaiveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        charge = services.waive_charge(
            self.get_object(), reason=s.validated_data["reason"], by=request.user, request=request
        )
        return Response(self.get_serializer(charge).data)


def _money(minor, currency):
    return str(to_major(minor or 0, currency))


class ArrearsView(OrgScopedMixin, generics.GenericAPIView):
    capabilities = {"get": "tenant.view"}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, org_id):
        ccy = self.org.currency
        rows = services.arrears_by_lease(self.org)
        return Response(
            {
                "currency": ccy,
                "total_owed": _money(sum(r["owed"] for r in rows), ccy),
                "results": [
                    {
                        "lease": r["lease_id"],
                        "tenant": r["tenant_id"],
                        "tenant_name": r["tenant__full_name"],
                        "tenant_phone": r["tenant__phone_number"],
                        "unit": r["unit__label"],
                        "property": r["unit__property__name"],
                        "owed": _money(r["owed"], ccy),
                        "charges": r["charges"],
                        "oldest_due": r["oldest_due"],
                        "days_overdue": r["days_overdue"],
                    }
                    for r in rows
                ],
            }
        )


class DashboardView(OrgScopedMixin, generics.GenericAPIView):
    capabilities = {"get": "org.view"}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, org_id):
        s = services.org_summary(self.org)
        ccy = self.org.currency
        return Response(
            {
                **s,
                "currency": ccy,
                "overdue_amount": _money(s["overdue_amount"], ccy),
                "due_next_30_days": _money(s["due_next_30_days"], ccy),
            }
        )


# ---- Tenant self-service ---------------------------------------------------------------------


class MyLeasesView(generics.ListAPIView):
    serializer_class = MyLeaseSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return (
            Lease.objects.filter(tenant__user=self.request.user)
            .exclude(status=Lease.Status.DRAFT)
            .select_related("unit__property", "organization")
            .order_by("-start_date")
        )


class MyChargesView(generics.ListAPIView):
    """My charges across all my landlords. Default: what I still owe; ?all=1 for history."""

    serializer_class = ChargeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Charge.objects.filter(tenant__user=self.request.user).select_related("tenant", "unit__property")
        if self.request.query_params.get("all") != "1":
            qs = qs.filter(status__in=Charge.OUTSTANDING)
        return qs.exclude(status=Charge.Status.VOID).order_by("due_date")


class MyChargeDetailView(generics.RetrieveAPIView):
    serializer_class = ChargeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return get_object_or_404(Charge, pk=self.kwargs["pk"], tenant__user=self.request.user)
