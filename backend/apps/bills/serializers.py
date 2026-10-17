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
    fee = serializers.SerializerMethodField(help_text="Homesika's fee per order, naira (added to the total).")

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
            "fee",
            "plans",
        )

    def get_fee(self, obj) -> str:
        from apps.core.money import to_major

        from .services import fee_for

        return str(to_major(fee_for(obj.category, 0), "NGN"))

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


class OrderIntlSerializer(serializers.Serializer):
    country = serializers.CharField(required=False)
    operator_name = serializers.CharField(required=False)
    local_currency = serializers.CharField(required=False)


class OrderSerializer(serializers.ModelSerializer):
    amount = MoneyField(read_only=True)
    fee = MoneyField(read_only=True)
    fee_waived = MoneyField(read_only=True, help_text="Service fee not charged (a referral reward)")
    total = MoneyField(read_only=True)
    biller_name = serializers.CharField(source="biller.name", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True, default=None)
    token = serializers.SerializerMethodField()
    intl = serializers.SerializerMethodField(help_text="International airtime: country and network")

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
            "fee_waived",
            "total",
            "intl",
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

    def get_intl(self, obj) -> OrderIntlSerializer(allow_null=True):
        i = obj.intl or {}
        return {k: i[k] for k in ("country", "operator_name", "local_currency") if k in i} or None

    def get_token(self, obj) -> str:
        return obj.token if obj.status == Order.Status.DELIVERED else ""


# ---- International airtime (Phase 6) ----------------------------------------------------------------


class IntlCountrySerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    currency = serializers.CharField()
    calling_code = serializers.CharField()


class IntlLookupSerializer(serializers.Serializer):
    country = serializers.CharField(max_length=2)
    phone = serializers.CharField(max_length=24)


class IntlOperatorSerializer(serializers.Serializer):
    operator_id = serializers.CharField()
    name = serializers.CharField()
    country = serializers.CharField()
    denomination = serializers.ChoiceField(choices=["range", "fixed"])
    min_amount = serializers.CharField(allow_null=True)
    max_amount = serializers.CharField(allow_null=True)
    fixed_amounts = serializers.ListField(child=serializers.CharField())
    local_currency = serializers.CharField()
    fx_rate = serializers.FloatField(allow_null=True, help_text="Local currency per naira: an estimate only")
    sample = serializers.BooleanField(help_text="True: SAMPLE data (no real provider connected)")


class IntlLookupResultSerializer(serializers.Serializer):
    phone = serializers.CharField(help_text="The number in international format")
    operator = IntlOperatorSerializer()


class IntlOrderSerializer(IntlLookupSerializer):
    amount = MoneyField(allow_zero=False, help_text='Naira, e.g. "5000.00"')
