from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.accounts.serializers import PhoneField

from .models import Membership, Organization, Role


class OrganizationSerializer(serializers.ModelSerializer):
    my_role = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = (
            "id",
            "name",
            "kind",
            "country",
            "currency",
            "timezone",
            "phone_number",
            "email",
            "address",
            "rent_reminders_enabled",
            "my_role",
            "created_at",
        )
        read_only_fields = ("id", "my_role", "created_at")

    def get_my_role(self, obj) -> str | None:
        roles = self.context.get("roles") or {}
        return roles.get(obj.pk)

    def validate(self, attrs):
        from apps.core import markets

        country = (attrs.get("country") or getattr(self.instance, "country", None) or "NG").upper()
        if not markets.is_enabled(country):
            raise serializers.ValidationError(
                {"country": [_("Homesika isn't available in this country yet.")]}
            )
        m = markets.country(country)
        if self.instance is None:  # new organization: the country decides the currency and time zone
            attrs.setdefault("currency", m.currency)
            attrs.setdefault("timezone", m.timezone)
            if attrs["currency"] != m.currency:
                raise serializers.ValidationError(
                    {"currency": [_("Use %(c)s for this country.") % {"c": m.currency}]}
                )
        return attrs

    def validate_kind(self, value):
        if value == Organization.Kind.PLATFORM:
            raise serializers.ValidationError(_("This organization type can't be created here."))
        return value


class MembershipSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    phone_number = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = ("id", "name", "phone_number", "role", "status", "created_at")
        read_only_fields = ("id", "name", "phone_number", "status", "created_at")

    def get_name(self, obj) -> str:
        return obj.user.full_name if obj.user else ""

    def get_phone_number(self, obj) -> str:
        return obj.user.phone_number if obj.user else obj.invited_phone


class InviteSerializer(serializers.Serializer):
    phone_number = PhoneField()
    role = serializers.ChoiceField(choices=[r for r in Role.choices])
