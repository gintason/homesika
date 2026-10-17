"""
Analytics for an organization's dashboard (GET /orgs/{org}/analytics/) and for Homesika's own team
(GET /platform/metrics/, `manage.py platform_metrics`). Money is integer kobo here; the API turns it
into decimal strings. Everything is computed from the records themselves (no separate event store).

Definitions (shown in the dashboard's help text):
* billed: charges due in the month (rent, service charge, dues…), not waived or cancelled.
* collected: payments received in the month (any charge, any month).
* collection rate: of what was billed for the month, how much has been paid so far.
* paid on time: charges due in the month that were fully paid by their due date.
"""

from collections import defaultdict
from datetime import date, timedelta
from statistics import median

from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from apps.leasing.models import Charge
from apps.leasing.schedule import add_months
from apps.payments.models import Allocation, Payment

BILLED = ~Q(status__in=(Charge.Status.WAIVED, Charge.Status.VOID))


def _months(today: date, n: int) -> list[date]:
    first = today.replace(day=1)
    return [add_months(first, -i) for i in range(n - 1, -1, -1)]


def _end(month: date) -> date:
    return add_months(month, 1) - timedelta(days=1)


def _pct(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def monthly(org, *, months: int = 6, today: date | None = None) -> list[dict]:
    today = today or timezone.localdate()
    rows = []
    for m in _months(today, months):
        end = _end(m)
        charges = Charge.objects.filter(BILLED, organization=org, due_date__gte=m, due_date__lte=end)
        billed = charges.aggregate(t=Sum("amount"))["t"] or 0
        dues_billed = charges.filter(kind=Charge.Kind.DUES).aggregate(t=Sum("amount"))["t"] or 0
        paid_against = (
            Allocation.objects.filter(charge__in=charges, payment__status="succeeded").aggregate(
                t=Sum("amount")
            )["t"]
            or 0
        )
        dues_paid = (
            Allocation.objects.filter(
                charge__in=charges.filter(kind=Charge.Kind.DUES), payment__status="succeeded"
            ).aggregate(t=Sum("amount"))["t"]
            or 0
        )
        # Paid on time: fully paid, and the last payment towards it was on or before the due date.
        paid = charges.filter(status=Charge.Status.PAID).annotate(last=Max("allocations__payment__paid_at"))
        on_time = sum(1 for c in paid if c.last and timezone.localtime(c.last).date() <= c.due_date)
        collected = Payment.objects.filter(
            organization=org, status="succeeded", paid_at__date__gte=m, paid_at__date__lte=end
        ).aggregate(t=Sum("amount"), n=Count("id"))
        count = charges.count()
        rows.append(
            {
                "month": m.isoformat(),
                "billed": billed,
                "collected": collected["t"] or 0,
                "payments": collected["n"],
                "paid_against_billed": paid_against,
                "collection_rate": _pct(paid_against, billed),
                "charges": count,
                "paid_on_time": on_time,
                "on_time_rate": _pct(on_time, count),
                "dues_billed": dues_billed,
                "dues_collected": dues_paid,
            }
        )
    return rows


def snapshot(org, *, today: date | None = None) -> dict:
    from apps.listings.models import Lead, Viewing
    from apps.maintenance.models import Ticket
    from apps.properties.models import Unit
    from apps.security.models import PanicAlert

    today = today or timezone.localdate()
    now = timezone.now()
    since = now - timedelta(days=30)
    units = Unit.objects.filter(property__organization=org).aggregate(
        total=Count("id"), occupied=Count("id", filter=Q(status="occupied"))
    )
    overdue = Charge.objects.filter(organization=org, status__in=Charge.OUTSTANDING, due_date__lt=today)
    arrears = sum(c.balance for c in overdue.only("amount", "amount_paid", "status"))
    tickets = Ticket.objects.filter(organization=org)
    closed = tickets.filter(confirmed_at__gte=now - timedelta(days=90)).values_list(
        "created_at", "confirmed_at"
    )
    days_to_fix = [(b - a).total_seconds() / 86400 for a, b in closed]
    leads = Lead.objects.filter(organization=org, created_at__gte=since)
    alerts = PanicAlert.objects.filter(estate__organization=org, created_at__gte=since).exclude(kind="drill")
    return {
        "units": units["total"],
        "occupied": units["occupied"],
        "occupancy_rate": _pct(units["occupied"], units["total"]),
        "arrears": arrears,
        "tenants_in_arrears": overdue.values("tenant").distinct().count(),
        "repairs_open": tickets.filter(status__in=Ticket.OPEN).count(),
        "repairs_reported_30d": tickets.filter(created_at__gte=since).count(),
        "repair_median_days_90d": round(median(days_to_fix), 1) if days_to_fix else None,
        "leads_30d": leads.count(),
        "leads_won_30d": leads.filter(stage="won").count(),
        "viewings_30d": Viewing.objects.filter(listing__organization=org, created_at__gte=since).count(),
        "alerts_30d": alerts.count(),
        "false_alarms_30d": alerts.filter(status="false_alarm").count(),
    }


# ---- Homesika's own numbers -----------------------------------------------------------------------


def platform(*, months: int = 6, today: date | None = None) -> dict:
    """For Homesika staff only: growth, money through the platform, bills and engagement."""
    from apps.accounts.models import User
    from apps.bills.models import Order
    from apps.maintenance.models import Ticket
    from apps.orgs.models import Organization
    from apps.security.models import PanicAlert

    today = today or timezone.localdate()
    now = timezone.now()
    since = now - timedelta(days=30)
    active = set(
        Payment.objects.filter(paid_at__gte=since, tenant__user__isnull=False).values_list(
            "tenant__user", flat=True
        )
    )
    active |= set(
        Order.objects.filter(created_at__gte=since, user__isnull=False).values_list("user", flat=True)
    )
    active |= set(
        Ticket.objects.filter(created_at__gte=since, raised_by__isnull=False).values_list(
            "raised_by", flat=True
        )
    )
    active |= set(
        PanicAlert.objects.filter(created_at__gte=since, raised_by__isnull=False).values_list(
            "raised_by", flat=True
        )
    )
    rows = []
    for m in _months(today, months):
        end = _end(m)
        pay = Payment.objects.filter(status="succeeded", paid_at__date__gte=m, paid_at__date__lte=end)
        online = pay.exclude(gateway="manual")
        bills = Order.objects.filter(status="delivered", created_at__date__gte=m, created_at__date__lte=end)
        rows.append(
            {
                "month": m.isoformat(),
                "new_users": User.objects.filter(created_at__date__gte=m, created_at__date__lte=end).count(),
                "new_organizations": Organization.objects.filter(
                    created_at__date__gte=m, created_at__date__lte=end
                ).count(),
                "rent_and_dues_online": online.aggregate(t=Sum("amount"))["t"] or 0,
                "recorded_offline": pay.filter(gateway="manual").aggregate(t=Sum("amount"))["t"] or 0,
                "platform_fees": online.aggregate(t=Sum("platform_fee_amount"))["t"] or 0,
                "bills_delivered": bills.count(),
                "bills_value": bills.aggregate(t=Sum("amount"))["t"] or 0,
                "bills_fees": bills.aggregate(t=Sum("fee"))["t"] or 0,
            }
        )
    by_kind = defaultdict(int)
    for kind, n in Organization.objects.values_list("kind").annotate(n=Count("id")):
        by_kind[kind] = n
    paying = Organization.objects.filter(payments__paid_at__gte=since).distinct().count()
    from apps.referrals.models import FeeWaiver, Referral

    referrals = {status: n for status, n in Referral.objects.values_list("status").annotate(n=Count("id"))}
    referrals["waivers_used"] = FeeWaiver.objects.filter(order__status="delivered").count()
    return {
        "referrals": referrals,
        "users": User.objects.count(),
        "active_users_30d": len(active),
        "organizations": dict(by_kind),
        "organizations_with_payments_30d": paying,
        "months": rows,
    }
