"""
Monthly owner statement: what was billed, collected and spent, per property. Collections come from
allocations (so each naira is attributed to the property of the charge it paid); overpayments not yet
matched to a charge are shown separately. Amounts are minor units (kobo).
"""

import calendar
from dataclasses import dataclass
from datetime import date

from django.db.models import Sum

from apps.leasing.models import Charge
from apps.payments.models import Allocation, Payment

from .models import Expense


@dataclass(frozen=True)
class Period:
    start: date
    end: date

    @classmethod
    def month(cls, year: int, month: int) -> "Period":
        return cls(date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]))


def build(org, period: Period, property_id=None) -> dict:
    allocations = Allocation.objects.filter(
        payment__organization=org,
        payment__status=Payment.Status.SUCCEEDED,
        payment__paid_at__date__range=(period.start, period.end),
    ).select_related("payment__tenant", "payment__receipt", "charge__unit__property")
    charges = Charge.objects.filter(organization=org, due_date__range=(period.start, period.end)).exclude(
        status__in=(Charge.Status.VOID, Charge.Status.WAIVED)
    )
    expenses = Expense.objects.filter(organization=org, spent_on__range=(period.start, period.end))
    if property_id:
        allocations = allocations.filter(charge__unit__property_id=property_id)
        charges = charges.filter(unit__property_id=property_id)
        expenses = expenses.filter(property_id=property_id)

    by_property: dict[str, dict] = {}

    def bucket(prop_id, name):
        return by_property.setdefault(
            str(prop_id) if prop_id else "", {"property": name, "billed": 0, "collected": 0, "expenses": 0}
        )

    for row in charges.values("unit__property_id", "unit__property__name").annotate(total=Sum("amount")):
        bucket(row["unit__property_id"], row["unit__property__name"])["billed"] += row["total"]
    for a in allocations:
        bucket(a.charge.unit.property_id, a.charge.unit.property.name)["collected"] += a.amount
    for row in expenses.values("property_id", "property__name").annotate(total=Sum("amount")):
        bucket(row["property_id"], row["property__name"] or "General")["expenses"] += row["total"]
    for b in by_property.values():
        b["net"] = b["collected"] - b["expenses"]

    unallocated = 0
    if not property_id:
        unallocated = (
            Payment.objects.filter(
                organization=org,
                status=Payment.Status.SUCCEEDED,
                paid_at__date__range=(period.start, period.end),
            ).aggregate(s=Sum("unallocated_amount"))["s"]
            or 0
        )

    collected = sum(a.amount for a in allocations)
    spent = expenses.aggregate(s=Sum("amount"))["s"] or 0
    outstanding_qs = Charge.objects.filter(
        organization=org, status__in=Charge.OUTSTANDING, due_date__lte=period.end
    )
    if property_id:
        outstanding_qs = outstanding_qs.filter(unit__property_id=property_id)
    outstanding = sum(c.balance for c in outstanding_qs)

    return {
        "period": {"start": period.start, "end": period.end},
        "currency": org.currency,
        "totals": {
            "billed": charges.aggregate(s=Sum("amount"))["s"] or 0,
            "collected": collected,
            "unallocated": unallocated,
            "expenses": spent,
            "net": collected + unallocated - spent,
            "outstanding_now": outstanding,
        },
        "by_property": sorted(by_property.values(), key=lambda b: b["property"] or ""),
        "expenses_by_category": {
            row["category"]: row["total"]
            for row in expenses.values("category").annotate(total=Sum("amount")).order_by("category")
        },
        "collections": [
            {
                "date": a.payment.paid_at.date(),
                "tenant": a.payment.tenant.full_name,
                "property": a.charge.unit.property.name,
                "unit": a.charge.unit.label,
                "for": a.charge.description or a.charge.get_kind_display(),
                "channel": a.payment.channel or a.payment.gateway,
                "receipt": getattr(getattr(a.payment, "receipt", None), "number", ""),
                "amount": a.amount,
            }
            for a in allocations.order_by("payment__paid_at")
        ],
        "expense_lines": [
            {
                "date": e.spent_on,
                "category": e.get_category_display(),
                "property": e.property.name if e.property_id else "",
                "vendor": e.vendor,
                "description": e.description,
                "amount": e.amount,
            }
            for e in expenses.select_related("property").order_by("spent_on")
        ],
    }
