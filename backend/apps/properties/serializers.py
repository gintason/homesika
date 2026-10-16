from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.core.serializers import MoneyField

from .models import Property, Unit


class UnitSerializer(serializers.ModelSerializer):
    default_rent_amount = MoneyField(required=False, allow_null=True)
    property_name = serializers.CharField(source="property.name", read_only=True)

    class Meta:
        model = Unit
        fields = (
            "id",
            "property",
            "property_name",
            "label",
            "kind",
            "bedrooms",
            "default_rent_amount",
            "status",
            "meter_number",
            "disco",
            "created_at",
        )
        read_only_fields = ("id", "property", "property_name", "created_at")

    def validate_label(self, value):
        prop = self.context.get("property") or getattr(self.instance, "property", None)
        clash = Unit.objects.filter(property=prop, label__iexact=value.strip())
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if prop and clash.exists():
            raise serializers.ValidationError(_("This property already has a unit with that name."))
        return value.strip()


class PropertySerializer(serializers.ModelSerializer):
    unit_count = serializers.IntegerField(read_only=True)
    occupied_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Property
        fields = (
            "id",
            "name",
            "kind",
            "address",
            "city",
            "state",
            "country",
            "notes",
            "is_archived",
            "unit_count",
            "occupied_count",
            "created_at",
        )
        read_only_fields = ("id", "unit_count", "occupied_count", "created_at")

    def validate_name(self, value):
        org = self.context["org"]
        clash = Property.objects.filter(organization=org, name__iexact=value.strip())
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError(_("You already have a property with this name."))
        return value.strip()
