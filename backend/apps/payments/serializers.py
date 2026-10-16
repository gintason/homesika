from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.core.money import to_major
from apps.core.serializers import MoneyField
from apps.leasing.models import Charge, TenantProfile

from .models import Payment, PaymentLink, SettlementAccount


class SettlementAccountSerializer(serializers.ModelSerializer):
    account_number = serializers.RegexField(
        r"^\d{10}$", write_only=True, error_messages={"invalid": _("Enter the 10-digit account number.")}
    )

    class Meta:
        model = SettlementAccount
        fields = (
            "id",
            "gateway",
            "bank_code",
            "bank_name",
            "account_number",
            "account_last4",
            "account_name",
            "status",
            "failure_reason",
            "created_at",
        )
        read_only_fields = ("id", "gateway", "account_last4", "status", "failure_reason", "created_at")


class PaymentLinkSerializer(serializers.ModelSerializer):
    amount = MoneyField(required=False, allow_zero=False)
    charges = serializers.PrimaryKeyRelatedField(many=True, queryset=Charge.objects.none())
    tenant = serializers.PrimaryKeyRelatedField(queryset=TenantProfile.objects.none())
    tenant_name = serializers.CharField(source="tenant.full_name", read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = PaymentLink
        fields = (
            "id",
            "reference",
            "tenant",
            "tenant_name",
            "charges",
            "amount",
            "currency",
            "description",
            "status",
            "expires_at",
            "gateway",
            "url",
            "created_at",
        )
        read_only_fields = (
            "id",
            "reference",
            "currency",
            "status",
            "expires_at",
            "gateway",
            "url",
            "created_at",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = self.context.get("org")
        if org is not None:
            self.fields["charges"].child_relation.queryset = Charge.objects.filter(organization=org)
            self.fields["tenant"].queryset = TenantProfile.objects.filter(organization=org)

    def get_url(self, obj) -> str:
        from .services import pay_url

        return pay_url(obj)


class PaymentSerializer(serializers.ModelSerializer):
    amount = MoneyField(read_only=True)
    unallocated_amount = MoneyField(read_only=True)
    tenant_name = serializers.CharField(source="tenant.full_name", read_only=True)
    receipt_number = serializers.CharField(source="receipt.number", read_only=True, default=None)
    applied_to = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = (
            "id",
            "tenant",
            "tenant_name",
            "gateway",
            "gateway_reference",
            "channel",
            "amount",
            "unallocated_amount",
            "currency",
            "status",
            "paid_at",
            "receipt_number",
            "needs_review",
            "review_reason",
            "note",
            "applied_to",
        )

    def get_applied_to(self, obj) -> list[dict]:
        return [
            {
                "charge": str(a.charge_id),
                "description": a.charge.description or a.charge.get_kind_display(),
                "amount": str(to_major(a.amount, obj.currency)),
            }
            for a in obj.allocations.all()
        ]


class ManualPaymentSerializer(serializers.Serializer):
    tenant = serializers.PrimaryKeyRelatedField(queryset=TenantProfile.objects.none())
    amount = MoneyField(allow_zero=False)
    channel = serializers.ChoiceField(
        choices=[
            ("cash", _("Cash")),
            ("bank_transfer", _("Bank transfer")),
            ("pos", _("POS")),
            ("cheque", _("Cheque")),
        ]
    )
    paid_at = serializers.DateTimeField(default=timezone.now)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    charges = serializers.PrimaryKeyRelatedField(many=True, required=False, queryset=Charge.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = self.context.get("org")
        if org is not None:
            self.fields["tenant"].queryset = TenantProfile.objects.filter(organization=org)
            self.fields["charges"].child_relation.queryset = Charge.objects.filter(organization=org)

    def validate_paid_at(self, value):
        if value > timezone.now():
            raise serializers.ValidationError(_("The payment date can't be in the future."))
        return value


class TenantPaySerializer(serializers.Serializer):
    charges = serializers.ListField(child=serializers.UUIDField(), min_length=1)
    amount = MoneyField(required=False, allow_zero=False)
