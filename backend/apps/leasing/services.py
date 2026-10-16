from datetime import date

from django.db import IntegrityError, transaction
from django.db.models import Count, Min, Q, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.accounts.models import User
from apps.core import audit
from apps.properties.models import Unit

from . import schedule
from .models import FREQUENCY_MONTHS, Charge, Lease, TenantProfile


def link_tenant_profiles(user: User) -> int:
    """A tenant joined the app: attach every landlord's profile that has their phone number."""
    return TenantProfile.objects.filter(phone_number=user.phone_number, user__isnull=True).update(user=user)


def create_tenant(*, org, by, request=None, **fields) -> TenantProfile:
    fields["user"] = User.objects.filter(phone_number=fields["phone_number"]).first()
    try:
        with transaction.atomic():
            tenant = TenantProfile.objects.create(organization=org, **fields)
    except IntegrityError as exc:
        raise serializers.ValidationError(
            {"phone_number": [_("You already have a tenant with this phone number.")]}
        ) from exc
    audit.record("tenant.created", actor=by, organization=org, obj=tenant, request=request)
    return tenant


def _generate_charges(lease: Lease) -> list[Charge]:
    rows = []
    months = FREQUENCY_MONTHS[lease.rent_frequency]
    common = {
        "organization_id": lease.organization_id,
        "lease": lease,
        "unit_id": lease.unit_id,
        "tenant_id": lease.tenant_id,
        "currency": lease.currency,
    }
    if lease.deposit_amount:
        rows.append(
            Charge(
                kind=Charge.Kind.DEPOSIT,
                description="Caution deposit",
                due_date=lease.start_date,
                amount=lease.deposit_amount,
                **common,
            )
        )
    for p in schedule.periods(lease.start_date, lease.end_date, months):
        label = f"{p.start:%d %b %Y} – {p.end:%d %b %Y}"
        rows.append(
            Charge(
                kind=Charge.Kind.RENT,
                description=f"Rent {label}",
                period_start=p.start,
                period_end=p.end,
                due_date=p.start,
                amount=schedule.prorate(lease.rent_amount, p.fraction),
                **common,
            )
        )
        if lease.service_charge_amount:
            rows.append(
                Charge(
                    kind=Charge.Kind.SERVICE_CHARGE,
                    description=f"Service charge {label}",
                    period_start=p.start,
                    period_end=p.end,
                    due_date=p.start,
                    amount=schedule.prorate(lease.service_charge_amount, p.fraction),
                    **common,
                )
            )
    return Charge.objects.bulk_create([r for r in rows if r.amount > 0])


@transaction.atomic
def activate_lease(lease: Lease, *, by, request=None) -> Lease:
    lease = Lease.objects.select_for_update().get(pk=lease.pk)
    if lease.status != Lease.Status.DRAFT:
        raise serializers.ValidationError({"status": [_("Only a draft lease can be activated.")]})
    unit = Unit.objects.select_for_update().get(pk=lease.unit_id)
    if Lease.objects.filter(unit=unit, status=Lease.Status.ACTIVE).exists():
        raise serializers.ValidationError({"unit": [_("This unit already has an active lease.")]})
    lease.status = Lease.Status.ACTIVE
    lease.save(update_fields=["status", "updated_at"])
    unit.status = Unit.Status.OCCUPIED
    unit.save(update_fields=["status", "updated_at"])
    charges = _generate_charges(lease)
    audit.record(
        "lease.activated",
        actor=by,
        organization=lease.organization,
        obj=lease,
        changes={"charges": len(charges)},
        request=request,
    )
    return lease


@transaction.atomic
def end_lease(lease: Lease, *, on: date, terminated: bool, by, request=None) -> Lease:
    lease = Lease.objects.select_for_update().get(pk=lease.pk)
    if lease.status != Lease.Status.ACTIVE:
        raise serializers.ValidationError({"status": [_("Only an active lease can be ended.")]})
    if on < lease.start_date:
        raise serializers.ValidationError(
            {"ended_on": [_("The end date can't be before the lease started.")]}
        )
    lease.status = Lease.Status.TERMINATED if terminated else Lease.Status.ENDED
    lease.ended_on = on
    lease.save(update_fields=["status", "ended_on", "updated_at"])
    # Future periods that haven't been paid are cancelled; anything already paid stays on record.
    voided = Charge.objects.filter(lease=lease, status=Charge.Status.OPEN, period_start__gt=on).update(
        status=Charge.Status.VOID, updated_at=timezone.now()
    )
    Unit.objects.filter(pk=lease.unit_id).update(status=Unit.Status.VACANT, updated_at=timezone.now())
    audit.record(
        "lease.ended",
        actor=by,
        organization=lease.organization,
        obj=lease,
        changes={"on": on.isoformat(), "terminated": terminated, "voided_charges": voided},
        request=request,
    )
    return lease


@transaction.atomic
def waive_charge(charge: Charge, *, reason: str, by, request=None) -> Charge:
    charge = Charge.objects.select_for_update().get(pk=charge.pk)
    if charge.status not in Charge.OUTSTANDING:
        raise serializers.ValidationError({"status": [_("Only an unpaid charge can be waived.")]})
    charge.status, charge.waived_reason = Charge.Status.WAIVED, reason
    charge.save(update_fields=["status", "waived_reason", "updated_at"])
    audit.record(
        "charge.waived",
        actor=by,
        organization=charge.organization,
        obj=charge,
        changes={"amount": charge.amount, "paid": charge.amount_paid, "reason": reason},
        request=request,
    )
    return charge


def outstanding(qs):
    return qs.filter(status__in=Charge.OUTSTANDING)


def arrears_by_lease(org, today: date | None = None) -> list[dict]:
    """Overdue balances grouped per lease: who owes what, since when."""
    today = today or timezone.localdate()
    rows = (
        outstanding(Charge.objects.filter(organization=org, due_date__lt=today))
        .values(
            "lease_id",
            "tenant_id",
            "tenant__full_name",
            "tenant__phone_number",
            "unit_id",
            "unit__label",
            "unit__property__name",
        )
        .annotate(owed=Sum("amount") - Sum("amount_paid"), charges=Count("id"), oldest_due=Min("due_date"))
        .order_by("oldest_due")
    )
    return [{**r, "days_overdue": (today - r["oldest_due"]).days} for r in rows]


def org_summary(org, today: date | None = None) -> dict:
    today = today or timezone.localdate()
    qs = outstanding(Charge.objects.filter(organization=org))
    overdue = qs.filter(due_date__lt=today).aggregate(a=Sum("amount"), p=Sum("amount_paid"), n=Count("id"))
    due_30 = qs.filter(due_date__gte=today, due_date__lte=today + timezone.timedelta(days=30)).aggregate(
        a=Sum("amount"), p=Sum("amount_paid")
    )
    units = Unit.objects.filter(property__organization=org).aggregate(
        total=Count("id"), occupied=Count("id", filter=Q(status=Unit.Status.OCCUPIED))
    )
    return {
        "overdue_amount": (overdue["a"] or 0) - (overdue["p"] or 0),
        "overdue_charges": overdue["n"],
        "due_next_30_days": (due_30["a"] or 0) - (due_30["p"] or 0),
        "units": units["total"],
        "occupied_units": units["occupied"],
    }
