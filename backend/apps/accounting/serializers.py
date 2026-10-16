from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.core.serializers import MoneyField
from apps.properties.models import Property, Unit

from .models import Expense


class ExpenseSerializer(serializers.ModelSerializer):
    amount = MoneyField(allow_zero=False)
    property = serializers.PrimaryKeyRelatedField(
        queryset=Property.objects.none(), required=False, allow_null=True
    )
    unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.none(), required=False, allow_null=True)
    property_name = serializers.CharField(source="property.name", read_only=True, default=None)

    class Meta:
        model = Expense
        fields = (
            "id",
            "property",
            "property_name",
            "unit",
            "category",
            "amount",
            "currency",
            "spent_on",
            "vendor",
            "description",
            "created_at",
        )
        read_only_fields = ("id", "currency", "created_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = self.context.get("org")
        if org is not None:
            self.fields["property"].queryset = Property.objects.filter(organization=org)
            self.fields["unit"].queryset = Unit.objects.filter(property__organization=org)

    def validate_spent_on(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError(_("The date can't be in the future."))
        return value

    def validate(self, attrs):
        unit = attrs.get("unit")
        if unit is not None:
            prop = attrs.get("property")
            if prop is not None and unit.property_id != prop.pk:
                raise serializers.ValidationError({"unit": [_("This unit isn't in the chosen property.")]})
            attrs["property"] = unit.property
        return attrs
