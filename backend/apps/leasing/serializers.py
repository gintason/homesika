from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.accounts.serializers import PhoneField
from apps.core.serializers import MoneyField
from apps.properties.models import Unit

from .models import Charge, Lease, TenantProfile


class TenantSerializer(serializers.ModelSerializer):
    phone_number = PhoneField()
    has_app = serializers.SerializerMethodField()
    active_lease = serializers.SerializerMethodField()

    class Meta:
        model = TenantProfile
        fields = (
            "id",
            "full_name",
            "phone_number",
            "email",
            "occupation",
            "next_of_kin",
            "id_document",
            "notes",
            "has_app",
            "active_lease",
            "created_at",
        )
        read_only_fields = ("id", "has_app", "active_lease", "created_at")

    def get_has_app(self, obj) -> bool:
        return obj.user_id is not None

    def get_active_lease(self, obj) -> dict | None:
        lease = next((le for le in obj.leases.all() if le.status == Lease.Status.ACTIVE), None)
        if not lease:
            return None
        return {"id": str(lease.id), "unit": lease.unit.label, "property": lease.unit.property.name}

    def validate_phone_number(self, value):
        if (
            self.instance
            and TenantProfile.objects.filter(organization=self.instance.organization, phone_number=value)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise serializers.ValidationError(_("You already have a tenant with this phone number."))
        return value


class LeaseSerializer(serializers.ModelSerializer):
    rent_amount = MoneyField(allow_zero=False)
    service_charge_amount = MoneyField(required=False)
    deposit_amount = MoneyField(required=False)
    unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.none())
    tenant = serializers.PrimaryKeyRelatedField(queryset=TenantProfile.objects.none())
    unit_label = serializers.CharField(source="unit.label", read_only=True)
    property_name = serializers.CharField(source="unit.property.name", read_only=True)
    tenant_name = serializers.CharField(source="tenant.full_name", read_only=True)
    balance = MoneyField(read_only=True)
    activate = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Lease
        fields = (
            "id",
            "unit",
            "unit_label",
            "property_name",
            "tenant",
            "tenant_name",
            "start_date",
            "end_date",
            "rent_amount",
            "rent_frequency",
            "service_charge_amount",
            "deposit_amount",
            "currency",
            "status",
            "ended_on",
            "notes",
            "balance",
            "activate",
            "created_at",
        )
        read_only_fields = ("id", "currency", "status", "ended_on", "balance", "created_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = self.context.get("org")
        if org is not None:
            self.fields["unit"].queryset = Unit.objects.filter(property__organization=org)
            self.fields["tenant"].queryset = TenantProfile.objects.filter(organization=org)

    def validate(self, attrs):
        if self.instance and self.instance.status != Lease.Status.DRAFT:
            locked = set(attrs) - {"notes", "activate"}
            if locked:
                raise serializers.ValidationError(
                    _("Only notes can change once a lease is active. End it and create a new one.")
                )
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"end_date": [_("The end date must be after the start date.")]})
        return attrs


class EndLeaseSerializer(serializers.Serializer):
    ended_on = serializers.DateField(default=timezone.localdate)
    terminated = serializers.BooleanField(default=False)


class ChargeSerializer(serializers.ModelSerializer):
    amount = MoneyField(allow_zero=False)
    amount_paid = MoneyField(read_only=True)
    balance = MoneyField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    lease = serializers.PrimaryKeyRelatedField(queryset=Lease.objects.none())
    tenant_name = serializers.CharField(source="tenant.full_name", read_only=True, default="")
    unit_label = serializers.CharField(source="unit.label", read_only=True)
    property_name = serializers.CharField(source="unit.property.name", read_only=True)
    organization = serializers.UUIDField(source="organization_id", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = Charge
        fields = (
            "id",
            "lease",
            "kind",
            "description",
            "period_start",
            "period_end",
            "due_date",
            "amount",
            "amount_paid",
            "balance",
            "currency",
            "status",
            "is_overdue",
            "waived_reason",
            "tenant_name",
            "unit_label",
            "property_name",
            "organization",
            "organization_name",
            "created_at",
        )
        read_only_fields = (
            "id",
            "period_start",
            "period_end",
            "amount_paid",
            "balance",
            "currency",
            "status",
            "is_overdue",
            "waived_reason",
            "created_at",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = self.context.get("org")
        if org is not None:
            self.fields["lease"].queryset = Lease.objects.filter(organization=org, status=Lease.Status.ACTIVE)

    def validate_kind(self, value):
        if value in (Charge.Kind.RENT, Charge.Kind.DUES):
            raise serializers.ValidationError(_("Rent is generated from the lease. Add other charges here."))
        return value


class WaiveSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200)


class MyLeaseSerializer(serializers.ModelSerializer):
    rent_amount = MoneyField(read_only=True)
    service_charge_amount = MoneyField(read_only=True)
    unit_label = serializers.CharField(source="unit.label")
    property_name = serializers.CharField(source="unit.property.name")
    property_address = serializers.CharField(source="unit.property.address")
    landlord = serializers.CharField(source="organization.name")
    landlord_phone = serializers.CharField(source="organization.phone_number")
    unit = serializers.UUIDField(source="unit_id", read_only=True)
    meter_number = serializers.CharField(source="unit.meter_number", read_only=True)
    disco = serializers.CharField(source="unit.disco", read_only=True)

    class Meta:
        model = Lease
        fields = (
            "id",
            "unit",
            "meter_number",
            "disco",
            "unit_label",
            "property_name",
            "property_address",
            "landlord",
            "landlord_phone",
            "start_date",
            "end_date",
            "rent_amount",
            "rent_frequency",
            "service_charge_amount",
            "currency",
            "status",
        )
