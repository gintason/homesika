"""
Estates: residents, dues, announcements and gate passes.

* Residents join with the estate's code and their house; an estate admin approves them ("verified
  resident"). Admins can also add a resident directly.
* On approval the resident gets a payer record in the estate's organization, so dues are ordinary
  charges: they show in the resident's Charges, are paid with the same checkout and get receipts.
* Dues plans raise one charge per verified resident per period, from the period they joined. Rerunning
  is harmless. Reminders: 3 days before, on the day, then 7 and 30 days late.
* Gate passes: a 6-digit code (SMS to the visitor), a time window and a number of uses. The security
  desk verifies the code and checks the visitor in and out; the host is told when they arrive.
"""

from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _t
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers, status

from apps.accounts.validators import normalise_phone, phone_validator
from apps.core import audit
from apps.core.exceptions import HomesikaAPIException
from apps.core.money import format_money
from apps.leasing.models import FREQUENCY_MONTHS, Charge, TenantProfile
from apps.leasing.schedule import add_months
from apps.notifications.services import notify, notify_sms, push_or_sms
from apps.properties.models import Property, Unit

from .models import (
    Announcement,
    DuesCharge,
    DuesPlan,
    DuesReminderLog,
    Estate,
    EstateMember,
    GateEvent,
    GatePass,
)

M = EstateMember.Status
DUES_STAGES = {-3: "before_3", 0: "due", 7: "late_7", 30: "late_30"}


class CodeNotFound(HomesikaAPIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = _("We couldn't find an estate with that code. Check it with your estate office.")
    default_code = "estate_code_not_found"


class PassInvalid(HomesikaAPIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = _("No valid pass with that code.")
    default_code = "gate_pass_invalid"


def _phone(raw: str, field: str = "phone_number") -> str:
    phone = normalise_phone(raw or "")
    try:
        phone_validator(phone)
    except Exception as exc:  # noqa: BLE001 - Django ValidationError
        raise serializers.ValidationError({field: [_("Enter a valid phone number.")]}) from exc
    return phone


# ---- Estates and houses ---------------------------------------------------------------------------


@transaction.atomic
def create_estate(*, org, by, name, address, city="", state="", request=None) -> Estate:
    prop = Property.objects.create(
        organization=org,
        name=name.strip(),
        kind=Property.Kind.COMPOUND,
        address=address.strip(),
        city=city,
        state=state,
    )
    estate = Estate.objects.create(
        organization=org, property=prop, name=name.strip(), address=address.strip(), city=city, state=state
    )
    audit.record("estate.created", actor=by, organization=org, obj=estate, request=request)
    return estate


def add_houses(estate: Estate, labels: list[str]) -> int:
    created = 0
    for label in {" ".join(str(x).split())[:60] for x in labels if str(x).strip()}:
        _unit, made = Unit.objects.get_or_create(
            property=estate.property,
            label=label,
            defaults={"kind": Unit.Kind.HOUSE, "status": Unit.Status.OCCUPIED},
        )
        created += int(made)
    return created


def regenerate_code(estate: Estate) -> Estate:
    from .models import _join_code

    for _attempt in range(5):
        estate.join_code = _join_code()
        try:
            with transaction.atomic():
                estate.save(update_fields=["join_code", "updated_at"])
            return estate
        except IntegrityError:
            continue
    raise RuntimeError("Couldn't make a unique join code")


# ---- Members ------------------------------------------------------------------------------------


def _unit_of(estate: Estate, unit_id):
    if not unit_id:
        return None
    unit = Unit.objects.filter(pk=unit_id, property=estate.property).first()
    if unit is None:
        raise serializers.ValidationError({"unit": [_("Choose a house in this estate.")]})
    return unit


@transaction.atomic
def join(*, user, code: str, house: str, request=None) -> EstateMember:
    estate = Estate.objects.filter(join_code=(code or "").strip().upper(), is_active=True).first()
    if estate is None:
        raise CodeNotFound()
    existing = estate.members.exclude(status=M.REMOVED).filter(phone_number=user.phone_number).first()
    if existing:
        if existing.user_id is None:
            existing.user = user
            existing.save(update_fields=["user", "updated_at"])
        return existing
    if not house.strip():
        raise serializers.ValidationError({"house": [_("Enter your house or flat number.")]})
    unit = Unit.objects.filter(property=estate.property, label__iexact=house.strip()).first()
    member = EstateMember.objects.create(
        estate=estate,
        user=user,
        full_name=user.full_name or user.phone_number,
        phone_number=user.phone_number,
        unit=unit,
        house_label=house.strip()[:60],
    )
    audit.record(
        "estate.join_requested", actor=user, organization=estate.organization, obj=member, request=request
    )
    return member


def _payer_for(member: EstateMember) -> TenantProfile:
    org = member.estate.organization
    payer, _made = TenantProfile.objects.get_or_create(
        organization=org,
        phone_number=member.phone_number,
        defaults={"full_name": member.full_name, "user": member.user},
    )
    if member.user_id and payer.user_id is None:
        payer.user = member.user
        payer.save(update_fields=["user", "updated_at"])
    return payer


@transaction.atomic
def approve(member: EstateMember, *, by, unit_id=None, role=None, request=None) -> EstateMember:
    member = (
        EstateMember.objects.select_for_update(of=("self",))
        .select_related("estate__organization")
        .get(pk=member.pk)
    )
    if member.status not in (M.PENDING, M.SUSPENDED):
        raise serializers.ValidationError({"status": [_("This resident is already approved or removed.")]})
    unit = _unit_of(member.estate, unit_id) if unit_id else member.unit
    if unit is None:
        raise serializers.ValidationError({"unit": [_("Choose the resident's house first.")]})
    member.unit, member.status = unit, M.APPROVED
    member.role = role or member.role
    member.approved_by, member.approved_at = by, member.approved_at or timezone.now()
    member.payer = _payer_for(member)
    member.save()
    audit.record(
        "estate.member_approved",
        actor=by,
        organization=member.estate.organization,
        obj=member,
        request=request,
    )
    notify_sms(
        to=member.phone_number,
        kind="estate_approved",
        user=member.user,
        organization=member.estate.organization,
        body=_t("Homesika: you're now a verified resident of %(estate)s (%(house)s).")
        % {"estate": member.estate.name, "house": unit.label},
    )
    generate_dues(estate=member.estate, member=member)
    return member


@transaction.atomic
def add_member(
    *, estate: Estate, by, full_name, phone_number, unit_id, role=EstateMember.Role.RESIDENT, request=None
) -> EstateMember:
    from apps.accounts.models import User

    phone = _phone(phone_number)
    unit = _unit_of(estate, unit_id)
    if estate.members.exclude(status=M.REMOVED).filter(phone_number=phone).exists():
        raise serializers.ValidationError({"phone_number": [_("This person is already a member.")]})
    member = EstateMember.objects.create(
        estate=estate,
        user=User.objects.filter(phone_number=phone).first(),
        full_name=full_name.strip(),
        phone_number=phone,
        unit=unit,
        house_label=unit.label if unit else "",
        role=role,
    )
    return approve(member, by=by, unit_id=unit.pk if unit else None, request=request)


@transaction.atomic
def set_status(member: EstateMember, *, status_: str, by, reason="", request=None) -> EstateMember:
    member.status, member.status_reason = status_, reason[:200]
    member.save(update_fields=["status", "status_reason", "updated_at"])
    audit.record(
        f"estate.member_{status_}",
        actor=by,
        organization=member.estate.organization,
        obj=member,
        changes={"reason": reason},
        request=request,
    )
    return member


def link_user(user) -> int:
    """After sign-up: attach memberships an admin created by phone number."""
    return EstateMember.objects.filter(phone_number=user.phone_number, user__isnull=True).update(user=user)


def verified_members(estate: Estate):
    return estate.members.filter(status=M.APPROVED).select_related("user", "unit")


def member_of(user, estate_id) -> EstateMember | None:
    return (
        EstateMember.objects.select_related("estate", "unit")
        .filter(estate_id=estate_id, user=user, status=M.APPROVED, estate__is_active=True)
        .first()
    )


# ---- Dues -----------------------------------------------------------------------------------------


def _periods(plan: DuesPlan, *, from_date, until):
    months = FREQUENCY_MONTHS[plan.frequency]
    n, start = 0, plan.start_date
    while start <= until:
        nxt = add_months(plan.start_date, months * (n + 1))
        if nxt > from_date:  # the period they joined in, and later ones
            yield start, nxt - timedelta(days=1)
        n += 1
        start = nxt


def generate_dues(*, estate: Estate | None = None, member: EstateMember | None = None, today=None) -> int:
    """Raise due charges up to 7 days ahead (so the "3 days before" reminder can go out)."""
    today = today or timezone.localdate()
    plans = DuesPlan.objects.filter(is_active=True, estate__is_active=True).select_related(
        "estate__organization"
    )
    if estate is not None:
        plans = plans.filter(estate=estate)
    created = 0
    for plan in plans:
        members = verified_members(plan.estate) if member is None else [member]
        for m in members:
            if m.payer_id is None or m.unit_id is None or m.status != M.APPROVED:
                continue
            joined = timezone.localtime(m.approved_at).date() if m.approved_at else today
            for start, end in _periods(plan, from_date=joined, until=today + timedelta(days=7)):
                if DuesCharge.objects.filter(plan=plan, member=m, period_start=start).exists():
                    continue
                try:
                    with transaction.atomic():
                        charge = Charge.objects.create(
                            organization=plan.estate.organization,
                            unit=m.unit,
                            tenant=m.payer,
                            kind=Charge.Kind.DUES,
                            description=f"{plan.name} ({start:%b %Y})",
                            period_start=start,
                            period_end=end,
                            due_date=start,
                            amount=plan.amount,
                            currency=plan.currency,
                        )
                        DuesCharge.objects.create(plan=plan, member=m, charge=charge, period_start=start)
                        created += 1
                except IntegrityError:
                    continue  # a concurrent run made it
    return created


def send_dues_reminders(today=None) -> dict:
    from apps.payments import services as payments
    from apps.payments.models import SettlementAccount

    today = today or timezone.localdate()
    by_due = {today - timedelta(days=offset): stage for offset, stage in DUES_STAGES.items()}
    links = DuesCharge.objects.filter(
        charge__status__in=Charge.OUTSTANDING, charge__due_date__in=list(by_due), member__status=M.APPROVED
    ).select_related("charge__organization", "charge__tenant", "member__estate", "member__user")
    payout_orgs = set(
        SettlementAccount.objects.filter(status="active").values_list("organization_id", flat=True)
    )
    sent = 0
    for link in links:
        charge, m = link.charge, link.member
        stage = by_due[charge.due_date]
        try:
            with transaction.atomic():
                DuesReminderLog.objects.create(charge=charge, stage=stage)
                url = ""
                if charge.organization_id in payout_orgs:
                    pl = payments.create_link(
                        org=charge.organization,
                        tenant=charge.tenant,
                        charge_ids=[charge.pk],
                        description=charge.description,
                    )
                    url = payments.pay_url(pl)
                amount = format_money(charge.balance, charge.currency, plain=True)
                when = (
                    _t("is due on %(d)s") % {"d": f"{charge.due_date:%d %b}"}
                    if stage.startswith("before")
                    else _t("is due today")
                    if stage == "due"
                    else _t("is overdue")
                )
                body = _t("%(estate)s: your %(what)s of %(amount)s %(when)s.") % {
                    "estate": m.estate.name,
                    "what": charge.description,
                    "amount": amount,
                    "when": when,
                }
                body += (" " + _t("Pay: %(url)s") % {"url": url}) if url else ""
                notify(
                    to=m.phone_number,
                    body=body,
                    kind="dues_reminder",
                    user=m.user,
                    organization=charge.organization,
                    wa_params=[m.estate.name, charge.description, amount, when, url or "-"],
                )
                sent += 1
        except IntegrityError:
            continue  # already reminded at this stage
    return {"sent": sent}


# ---- Announcements ------------------------------------------------------------------------------


def announce(
    *, estate: Estate, by, title, body, audience=Announcement.Audience.ALL, urgent=False, request=None
):
    a = Announcement.objects.create(
        estate=estate, title=title.strip(), body=body.strip(), audience=audience, urgent=urgent, created_by=by
    )
    members = verified_members(estate)
    if audience == Announcement.Audience.EXCO:
        members = members.filter(role=EstateMember.Role.EXCO)
    counts = push_or_sms(
        recipients=[(m.user, m.phone_number) for m in members],
        title=f"{estate.name}: {a.title}",
        body=a.body[:200],
        kind="estate_announcement",
        data={"type": "announcement", "estate": str(estate.pk), "id": str(a.pk)},
        sms="always" if urgent else "fallback" if settings.ANNOUNCEMENT_SMS_FALLBACK else "never",
        organization=estate.organization,
    )
    a.push_sent, a.sms_sent = counts["push"], counts["sms"]
    a.save(update_fields=["push_sent", "sms_sent", "updated_at"])
    audit.record(
        "estate.announcement",
        actor=by,
        organization=estate.organization,
        obj=a,
        changes=counts,
        request=request,
    )
    return a


# ---- Gate passes --------------------------------------------------------------------------------


@transaction.atomic
def create_pass(
    *,
    member: EstateMember,
    visitor_name,
    visitor_phone="",
    kind=GatePass.Kind.VISITOR,
    valid_from=None,
    hours: int = 12,
    max_uses: int = 1,
    job_id=None,
    note="",
) -> GatePass:
    if member.status != M.APPROVED:
        raise serializers.ValidationError({"host": [_("Only verified residents can create gate passes.")]})
    now = timezone.now()
    start = valid_from or now
    if start < now - timedelta(minutes=10):
        raise serializers.ValidationError({"valid_from": [_("Choose a time from now on.")]})
    if not 1 <= hours <= 24 * 7:
        raise serializers.ValidationError({"hours": [_("A pass can last from 1 hour to 7 days.")]})
    if not 1 <= max_uses <= 50:
        raise serializers.ValidationError({"max_uses": [_("Choose between 1 and 50 entries.")]})
    phone = _phone(visitor_phone, "visitor_phone") if visitor_phone else ""
    job = None
    if job_id:
        from apps.maintenance.models import Job

        job = (
            Job.objects.select_related("artisan__user", "ticket")
            .filter(pk=job_id, ticket__unit=member.unit, status__in=("accepted", "on_site"))
            .first()
        )
        if job is None:
            raise serializers.ValidationError({"job": [_("Choose an accepted repair job for your house.")]})
        kind, visitor_name = GatePass.Kind.ARTISAN, visitor_name or job.artisan.display_name
        phone = phone or job.artisan.user.phone_number
    for _attempt in range(10):
        try:
            with transaction.atomic():
                gp = GatePass.objects.create(
                    estate=member.estate,
                    host=member,
                    visitor_name=visitor_name.strip()[:120],
                    visitor_phone=phone,
                    kind=kind,
                    job=job,
                    valid_from=start,
                    valid_to=start + timedelta(hours=hours),
                    max_uses=max_uses,
                    note=note.strip()[:200],
                )
            break
        except IntegrityError:
            continue
    else:
        raise RuntimeError("Couldn't make a unique gate code")
    if phone:
        extra = f" {member.estate.gate_instructions}" if member.estate.gate_instructions else ""
        notify_sms(
            to=phone,
            kind="gate_pass",
            organization=member.estate.organization,
            body=_t(
                "%(estate)s: your gate code is %(code)s, from %(host)s (%(house)s). "
                "Valid until %(until)s.%(extra)s"
            )
            % {
                "estate": member.estate.name,
                "code": gp.code,
                "host": member.full_name.split(" ")[0],
                "house": member.unit.label if member.unit else member.house_label,
                "until": f"{timezone.localtime(gp.valid_to):%a %d %b %I:%M %p}",
                "extra": extra,
            },
        )
    return gp


def _refresh(gp: GatePass, now=None) -> GatePass:
    now = now or timezone.now()
    if gp.status == GatePass.Status.ACTIVE and gp.valid_to < now:
        gp.status = GatePass.Status.EXPIRED
        gp.save(update_fields=["status", "updated_at"])
    return gp


def find_pass(estate: Estate, code: str) -> GatePass:
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    gp = (
        GatePass.objects.select_related("host__unit", "job__artisan")
        .filter(estate=estate, code=code, status=GatePass.Status.ACTIVE)
        .first()
    )
    if gp is None:
        raise PassInvalid()
    gp = _refresh(gp)
    if gp.status != GatePass.Status.ACTIVE or gp.valid_from > timezone.now() + timedelta(minutes=30):
        raise PassInvalid(_("This code isn't valid right now (expired or not yet started)."))
    return gp


@transaction.atomic
def check_in(gp: GatePass, *, by, note="") -> GatePass:
    gp = GatePass.objects.select_for_update(of=("self",)).select_related("host__user", "estate").get(pk=gp.pk)
    gp = _refresh(gp)
    if gp.status != GatePass.Status.ACTIVE:
        raise PassInvalid()
    gp.uses += 1
    if gp.uses >= gp.max_uses:
        gp.status = GatePass.Status.USED
    gp.save(update_fields=["uses", "status", "updated_at"])
    GateEvent.objects.create(gate_pass=gp, kind=GateEvent.Kind.CHECK_IN, by=by, note=note[:200])
    push_or_sms(
        recipients=[(gp.host.user, gp.host.phone_number)],
        title=gp.estate.name,
        body=_t("%(name)s has arrived at the gate.") % {"name": gp.visitor_name},
        kind="gate_arrival",
        data={"type": "gate", "pass": str(gp.pk)},
        organization=gp.estate.organization,
    )
    return gp


def check_out(gp: GatePass, *, by, note="") -> GateEvent:
    return GateEvent.objects.create(gate_pass=gp, kind=GateEvent.Kind.CHECK_OUT, by=by, note=note[:200])


def deny(gp: GatePass, *, by, note="") -> GateEvent:
    return GateEvent.objects.create(gate_pass=gp, kind=GateEvent.Kind.DENIED, by=by, note=note[:200])


def cancel_pass(gp: GatePass) -> GatePass:
    if gp.status == GatePass.Status.ACTIVE:
        gp.status = GatePass.Status.CANCELLED
        gp.save(update_fields=["status", "updated_at"])
    return gp


def expire_passes(now=None) -> int:
    now = now or timezone.now()
    return GatePass.objects.filter(status=GatePass.Status.ACTIVE, valid_to__lt=now).update(
        status=GatePass.Status.EXPIRED, updated_at=now
    )
