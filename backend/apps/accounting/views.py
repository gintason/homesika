import csv
import io
from datetime import date

from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import audit
from apps.core.idempotency import idempotent
from apps.core.money import to_major
from apps.orgs.permissions import OrgScopedMixin
from apps.properties.views import OrgContextMixin

from . import analytics, statements
from .models import Expense
from .serializers import ExpenseSerializer


class ExpenseViewSet(OrgScopedMixin, OrgContextMixin, viewsets.ModelViewSet):
    """?property=, ?category=, ?from=YYYY-MM-DD, ?to=YYYY-MM-DD"""

    queryset = Expense.objects.none()  # schema generation only; get_queryset() scopes to the org
    serializer_class = ExpenseSerializer
    cursor_ordering = ("-spent_on", "-created_at")
    capability_scope = "expense"

    def get_queryset(self):
        qs = Expense.objects.filter(organization=self.org).select_related("property")
        p = self.request.query_params
        if p.get("property"):
            qs = qs.filter(property=p["property"])
        if p.get("category"):
            qs = qs.filter(category=p["category"])
        if p.get("from"):
            qs = qs.filter(spent_on__gte=p["from"])
        if p.get("to"):
            qs = qs.filter(spent_on__lte=p["to"])
        return qs.order_by("-spent_on", "-created_at")

    @idempotent
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        expense = serializer.save(
            organization=self.org, currency=self.org.currency, created_by=self.request.user
        )
        audit.record(
            "expense.created",
            actor=self.request.user,
            organization=self.org,
            obj=expense,
            changes={"amount": expense.amount, "category": expense.category},
            request=self.request,
        )

    def perform_destroy(self, instance):
        audit.record(
            "expense.deleted",
            actor=self.request.user,
            organization=self.org,
            obj=instance,
            changes={"amount": instance.amount},
            request=self.request,
        )
        instance.delete()


class StatementQuery(serializers.Serializer):
    month = serializers.RegexField(r"^\d{4}-(0[1-9]|1[0-2])$", required=False)
    property = serializers.UUIDField(required=False)
    export = serializers.ChoiceField(choices=["csv"], required=False)


def _major_tree(value, currency):
    """Convert every *amount-like* int in the statement to a decimal string in major units."""
    money_keys = {
        "billed",
        "collected",
        "unallocated",
        "expenses",
        "net",
        "outstanding_now",
        "amount",
    }
    if isinstance(value, dict):
        return {
            k: (
                str(to_major(v, currency))
                if k in money_keys and isinstance(v, int)
                else _major_tree(v, currency)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_major_tree(v, currency) for v in value]
    return value


class StatementView(OrgScopedMixin, APIView):
    """GET /orgs/{id}/statements/?month=2026-10[&property=][&export=csv]"""

    capabilities = {"get": "report.view"}

    @extend_schema(
        parameters=[StatementQuery], responses={200: OpenApiTypes.OBJECT, (200, "text/csv"): OpenApiTypes.STR}
    )
    def get(self, request, *args, **kwargs):
        q = StatementQuery(data=request.query_params)
        q.is_valid(raise_exception=True)
        today = timezone.localdate()
        year, month = map(int, q.validated_data.get("month", f"{today:%Y-%m}").split("-"))
        data = statements.build(
            self.org, statements.Period.month(year, month), property_id=q.validated_data.get("property")
        )
        ccy = data["currency"]
        if q.validated_data.get("export") == "csv":
            return _csv(self.org, data, ccy, date(year, month, 1))
        out = _major_tree(data, ccy)
        out["expenses_by_category"] = {
            k: str(to_major(v, ccy)) for k, v in data["expenses_by_category"].items()
        }
        return Response(out)


def _csv(org, data, ccy, month: date) -> HttpResponse:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"{org.name} statement", f"{month:%B %Y}", f"Currency: {ccy}"])
    w.writerow([])
    w.writerow(["Collections"])
    w.writerow(["Date", "Tenant", "Property", "Unit", "For", "Channel", "Receipt", "Amount"])
    for r in data["collections"]:
        w.writerow(
            [
                r["date"],
                r["tenant"],
                r["property"],
                r["unit"],
                r["for"],
                r["channel"],
                r["receipt"],
                to_major(r["amount"], ccy),
            ]
        )
    w.writerow([])
    w.writerow(["Expenses"])
    w.writerow(["Date", "Category", "Property", "Vendor", "Description", "Amount"])
    for r in data["expense_lines"]:
        w.writerow(
            [
                r["date"],
                r["category"],
                r["property"],
                r["vendor"],
                r["description"],
                to_major(r["amount"], ccy),
            ]
        )
    w.writerow([])
    w.writerow(["Totals"])
    for key, label in [
        ("billed", "Billed"),
        ("collected", "Collected"),
        ("unallocated", "Overpayments not yet applied"),
        ("expenses", "Expenses"),
        ("net", "Net"),
        ("outstanding_now", "Outstanding (as of today)"),
    ]:
        w.writerow([label, to_major(data["totals"][key], ccy)])
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="statement-{month:%Y-%m}.csv"'
    return resp


# ---- Analytics (Phase 6) --------------------------------------------------------------------------

MONEY_KEYS = {
    "billed",
    "collected",
    "paid_against_billed",
    "dues_billed",
    "dues_collected",
    "arrears",
    "rent_and_dues_online",
    "recorded_offline",
    "platform_fees",
    "bills_value",
    "bills_fees",
}


def _money(obj, ccy="NGN"):
    """Kobo ints -> decimal strings for the keys that are money."""
    if isinstance(obj, list):
        return [_money(x, ccy) for x in obj]
    if isinstance(obj, dict):
        return {k: (str(to_major(v, ccy)) if k in MONEY_KEYS else _money(v, ccy)) for k, v in obj.items()}
    return obj


class AnalyticsMonthSerializer(serializers.Serializer):
    month = serializers.DateField()
    billed = serializers.DecimalField(max_digits=16, decimal_places=2)
    collected = serializers.DecimalField(max_digits=16, decimal_places=2)
    payments = serializers.IntegerField()
    paid_against_billed = serializers.DecimalField(max_digits=16, decimal_places=2)
    collection_rate = serializers.FloatField(
        allow_null=True, help_text="% of the month's charges paid so far"
    )
    charges = serializers.IntegerField()
    paid_on_time = serializers.IntegerField()
    on_time_rate = serializers.FloatField(allow_null=True)
    dues_billed = serializers.DecimalField(max_digits=16, decimal_places=2)
    dues_collected = serializers.DecimalField(max_digits=16, decimal_places=2)


class AnalyticsSnapshotSerializer(serializers.Serializer):
    units = serializers.IntegerField()
    occupied = serializers.IntegerField()
    occupancy_rate = serializers.FloatField(allow_null=True)
    arrears = serializers.DecimalField(max_digits=16, decimal_places=2)
    tenants_in_arrears = serializers.IntegerField()
    repairs_open = serializers.IntegerField()
    repairs_reported_30d = serializers.IntegerField()
    repair_median_days_90d = serializers.FloatField(allow_null=True)
    leads_30d = serializers.IntegerField()
    leads_won_30d = serializers.IntegerField()
    viewings_30d = serializers.IntegerField()
    alerts_30d = serializers.IntegerField()
    false_alarms_30d = serializers.IntegerField()


class AnalyticsSerializer(serializers.Serializer):
    currency = serializers.CharField()
    months = AnalyticsMonthSerializer(many=True)
    now = AnalyticsSnapshotSerializer()


class AnalyticsQuery(serializers.Serializer):
    months = serializers.IntegerField(min_value=1, max_value=24, default=6)


class AnalyticsView(OrgScopedMixin, APIView):
    """GET /orgs/{id}/analytics/?months=6: month-by-month collection, plus today's snapshot."""

    capabilities = {"get": "report.view"}

    @extend_schema(parameters=[AnalyticsQuery], responses=AnalyticsSerializer)
    def get(self, request, *args, **kwargs):
        q = AnalyticsQuery(data=request.query_params)
        q.is_valid(raise_exception=True)
        ccy = self.org.currency
        return Response(
            {
                "currency": ccy,
                "months": _money(analytics.monthly(self.org, months=q.validated_data["months"]), ccy),
                "now": _money(analytics.snapshot(self.org), ccy),
            }
        )


class PlatformMonthSerializer(serializers.Serializer):
    month = serializers.DateField()
    new_users = serializers.IntegerField()
    new_organizations = serializers.IntegerField()
    rent_and_dues_online = serializers.DecimalField(max_digits=16, decimal_places=2)
    recorded_offline = serializers.DecimalField(max_digits=16, decimal_places=2)
    platform_fees = serializers.DecimalField(max_digits=16, decimal_places=2)
    bills_delivered = serializers.IntegerField()
    bills_value = serializers.DecimalField(max_digits=16, decimal_places=2)
    bills_fees = serializers.DecimalField(max_digits=16, decimal_places=2)


class PlatformMetricsSerializer(serializers.Serializer):
    users = serializers.IntegerField()
    active_users_30d = serializers.IntegerField(
        help_text="Paid, bought a bill, reported a repair or raised an alert"
    )
    organizations = serializers.DictField(child=serializers.IntegerField(), help_text="By kind")
    organizations_with_payments_30d = serializers.IntegerField()
    referrals = serializers.DictField(child=serializers.IntegerField(), required=False)
    months = PlatformMonthSerializer(many=True)


class PlatformMetricsView(APIView):
    """GET /platform/metrics/: Homesika's own numbers (staff accounts only). Amounts in NGN."""

    permission_classes = [permissions.IsAdminUser]

    @extend_schema(parameters=[AnalyticsQuery], responses=PlatformMetricsSerializer)
    def get(self, request):
        q = AnalyticsQuery(data=request.query_params)
        q.is_valid(raise_exception=True)
        return Response(_money(analytics.platform(months=q.validated_data["months"])))
