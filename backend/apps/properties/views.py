from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers, viewsets

from apps.core import audit
from apps.orgs.permissions import OrgScopedMixin

from .models import Property, Unit
from .serializers import PropertySerializer, UnitSerializer


class OrgContextMixin:
    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if hasattr(self, "org"):
            ctx.update(org=self.org, currency=self.org.currency)
        return ctx


class PropertyViewSet(OrgScopedMixin, OrgContextMixin, viewsets.ModelViewSet):
    serializer_class = PropertySerializer
    capability_scope = "property"
    pagination_class = None

    def get_queryset(self):
        qs = Property.objects.filter(organization=self.org).annotate(
            unit_count=Count("units", distinct=True),
            occupied_count=Count("units", filter=Q(units__status=Unit.Status.OCCUPIED), distinct=True),
        )
        if self.request.query_params.get("archived") != "1":
            qs = qs.filter(is_archived=False)
        return qs.order_by("name")

    def perform_create(self, serializer):
        obj = serializer.save(organization=self.org)
        audit.record(
            "property.created", actor=self.request.user, organization=self.org, obj=obj, request=self.request
        )

    def perform_destroy(self, instance):
        if instance.units.filter(leases__status="active").exists():
            raise serializers.ValidationError(
                {"property": [_("End the active leases before deleting this property.")]}
            )
        audit.record(
            "property.deleted",
            actor=self.request.user,
            organization=self.org,
            obj=instance,
            changes={"name": instance.name},
            request=self.request,
        )
        instance.delete()


class UnitViewSet(OrgScopedMixin, OrgContextMixin, viewsets.ModelViewSet):
    """Units of one property (/properties/<property_pk>/units/) or of the whole org (/units/)."""

    serializer_class = UnitSerializer
    capability_scope = "property"
    pagination_class = None

    def _property(self):
        if "property_pk" not in self.kwargs:
            return None
        return get_object_or_404(Property, organization=self.org, pk=self.kwargs["property_pk"])

    def get_queryset(self):
        qs = Unit.objects.filter(property__organization=self.org).select_related("property")
        prop = self._property()
        if prop:
            qs = qs.filter(property=prop)
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if hasattr(self, "org") and "property_pk" in self.kwargs:
            ctx["property"] = self._property()
        return ctx

    def perform_create(self, serializer):
        prop = self._property()
        if prop is None:
            raise serializers.ValidationError({"property": [_("Create units under a property.")]})
        serializer.save(property=prop)

    def perform_destroy(self, instance):
        if instance.leases.filter(status="active").exists():
            raise serializers.ValidationError(
                {"unit": [_("End the active lease before deleting this unit.")]}
            )
        instance.delete()
