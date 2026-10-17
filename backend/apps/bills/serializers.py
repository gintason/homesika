from rest_framework import serializers

from apps.core.serializers import MoneyField
from apps.properties.models import Unit

from .models import Biller, Order, Plan


class PlanSerializer(serializers.ModelSerializer):
    price = MoneyField(read_only=True, allow_null=True)

    class Meta:
        model = Plan
        fields = ("id", "code", "name", "price", "validity_days", "data_mb")


class BillerSerializer(serializers.ModelSerializer):
    plans = serializers.SerializerMethodField()
    min_amount = MoneyField(read_only=True, allow_null=True)
    max_amount = MoneyField(read_only=True, allow_null=True)

    class Meta:
        model = Biller
        fields = (
            "id",
            "category",
            "code",
            "name",
            "customer_label",
            "requires_verification",
            "min_amount",
            "max_amount",
            "plans",
        )

    def get_plans(self, obj) -> list[dict]:
        return PlanSerializer(
            [p for p in obj.plans.all() if p.is_active], many=True, context=self.context
        ).data


class BillVerifySerializer(serializers.Serializer):
    biller = serializers.PrimaryKeyRelatedField(queryset=Biller.objects.filter(is_active=True))
    plan = serializers.PrimaryKeyRelatedField(
        queryset=Plan.objects.filter(is_active=True), required=False, allow_null=True
    )
    customer_id = serializers.CharField(max_length=40)


class CreateOrderSerializer(BillVerifySerializer):
    amount = MoneyField(required=False, allow_null=True, allow_zero=False)
    unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.all(), required=False, allow_null=True)


class OrderSerializer(serializers.ModelSerializer):
    amount = MoneyField(read_only=True)
    fee = MoneyField(read_only=True)
    total = MoneyField(read_only=True)
    biller_name = serializers.CharField(source="biller.name", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True, default=None)
    token = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "reference",
            "category",
            "biller",
            "biller_name",
            "plan",
            "plan_name",
            "customer_id",
            "customer_name",
            "amount",
            "fee",
            "total",
            "currency",
            "status",
            "checkout_url",
            "token",
            "units",
            "receipt_number",
            "failure_reason",
            "created_at",
            "paid_at",
            "delivered_at",
            "refunded_at",
            "expires_at",
        )

    def get_token(self, obj) -> str:
        return obj.token if obj.status == Order.Status.DELIVERED else ""
