import csv
import io
from datetime import date

from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import audit
from apps.core.idempotency import idempotent
from apps.core.money import to_major
from apps.orgs.permissions import OrgScopedMixin
from apps.properties.views import OrgContextMixin

from . import statements
from .models import Expense
from .serializers import ExpenseSerializer


class ExpenseViewSet(OrgScopedMixin, OrgContextMixin, viewsets.ModelViewSet):
    """?property=, ?category=, ?from=YYYY-MM-DD, ?to=YYYY-MM-DD"""

    queryset = Expense.objects.none()  # schema generation only; get_queryset() scopes to the org
    serializer_class = ExpenseSerializer
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
