"""
Panic alerts: raise fast, reach people reliably, and keep a record.

Raising (the app's hold-to-trigger button, the web, or the assistant after a YES):
* A verified resident (or estate staff) raises it; the phone sends its own id so a retry on a bad
  network returns the same alert. A second press within 2 minutes joins the open alert instead of
  starting another. More than PANIC_MAX_PER_HOUR in an hour is refused with "call 112".
* "Silent" alerts go only to security and managers, with nothing sent back to the raiser's phone.
* Location is stored (encrypted) only if the person agreed to share it.

Reaching people (Celery "alerts" queue, separate workers):
* The security desk screen updates at once over WebSocket.
* Security and managers get a push and, by default, an SMS at the same time (PANIC_SMS_STAFF_ALWAYS).
* Residents (non-silent alerts, if the estate allows) get a push; anyone without a working phone in the
  app, whose push failed, or whose push isn't confirmed within PANIC_PUSH_FALLBACK_SECONDS, gets an SMS.
* Every attempt is an AlertDelivery row, so delivery times per channel can be measured.

Afterwards: security acknowledge, say they're on the way, and resolve it or mark it a false alarm;
the raiser can cancel ("I'm safe"). Notes form the incident log. A drill sends a clearly marked TEST to
staff to prove delivery works.
"""

import json
import logging
from datetime import timedelta

from asgiref.sync import async_to_sync
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Min
from django.utils import timezone
from django.utils.translation import gettext as _t
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers, status

from apps.core import audit
from apps.core.exceptions import HomesikaAPIException
from apps.estates.models import Estate, EstateMember
from apps.notifications import push
from apps.notifications.services import notify_sms
from apps.orgs.models import Membership

from .models import AlertDelivery, IncidentNote, PanicAlert

logger = logging.getLogger(__name__)
A = PanicAlert.Status
D = AlertDelivery.Status
STAFF_ROLES = ("owner", "manager", "estate_admin", "security")


class TooManyAlerts(HomesikaAPIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = _("You've raised several alerts in the last hour. If you're in danger, call 112 now.")
    default_code = "panic_rate_limited"


class NotAllowed(HomesikaAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = _("Only verified residents and estate staff can raise an alert here.")
    default_code = "panic_not_allowed"


class WrongState(HomesikaAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = _("This alert has already moved on. Refresh to see its status.")
    default_code = "alert_wrong_state"


def _is_staff(user, estate: Estate) -> bool:
    return Membership.objects.filter(
        organization=estate.organization, user=user, status="active", role__in=STAFF_ROLES
    ).exists()


def _house(alert: PanicAlert) -> str:
    m = alert.member
    if m is None:
        return ""
    return m.unit.label if m.unit_id else m.house_label


def desk_group(estate_id) -> str:
    return f"estate-desk-{estate_id}"


def broadcast(alert: PanicAlert, event: str) -> None:
    """Live update for every security-desk screen watching this estate."""
    from channels.layers import get_channel_layer

    from .serializers import alert_summary

    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(
            desk_group(alert.estate_id), {"type": "desk.event", "event": event, "alert": alert_summary(alert)}
        )
    except Exception:  # noqa: BLE001 - the desk also polls; never fail an alert over the live channel
        logger.exception("Desk broadcast failed for alert %s", alert.pk)


# ---- Raising ------------------------------------------------------------------------------------


def raise_alert(
    *,
    user,
    estate: Estate,
    kind=PanicAlert.Kind.HELP,
    silent=False,
    location=None,
    client_id="",
    channel="app",
    member: EstateMember | None = None,
) -> tuple[PanicAlert, bool]:
    """Returns (alert, created). Never blocks a first alert. `member` is for a resident with no app
    account (WhatsApp); otherwise the user's own approved membership is used."""
    if not estate.is_active or not estate.panic_enabled:
        raise serializers.ValidationError({"estate": [_("Panic alerts are turned off for this estate.")]})
    if member is not None and (
        member.estate_id != estate.pk or member.status != EstateMember.Status.APPROVED
    ):
        member = None
    if member is None and user is not None:
        member = (
            EstateMember.objects.select_related("unit")
            .filter(estate=estate, user=user, status=EstateMember.Status.APPROVED)
            .first()
        )
    if member is None and (user is None or not _is_staff(user, estate)):
        raise NotAllowed()
    mine = {"raised_by": user} if user is not None else {"member": member, "raised_by__isnull": True}
    if kind not in PanicAlert.Kind.values or kind == PanicAlert.Kind.DRILL:
        kind = PanicAlert.Kind.HELP
    client_id = (client_id or "").strip()[:64] or None
    if client_id:
        existing = PanicAlert.objects.filter(client_id=client_id).first()
        if existing:
            return existing, False
    now = timezone.now()
    recent = PanicAlert.objects.filter(
        estate=estate, status__in=PanicAlert.OPEN, created_at__gte=now - timedelta(minutes=2), **mine
    ).first()
    if recent:
        if kind != PanicAlert.Kind.HELP and recent.kind == PanicAlert.Kind.HELP:
            set_kind(recent, kind=kind, by=user)
        return recent, False
    if (
        PanicAlert.objects.filter(created_at__gte=now - timedelta(hours=1), **mine)
        .exclude(kind=PanicAlert.Kind.DRILL)
        .count()
        >= settings.PANIC_MAX_PER_HOUR
    ):
        raise TooManyAlerts()
    loc = ""
    if isinstance(location, dict) and {"lat", "lng"} <= set(location):
        try:
            loc = json.dumps(
                {k: round(float(location[k]), 6) for k in ("lat", "lng")}
                | (
                    {"accuracy": round(float(location["accuracy"]), 1)}
                    if location.get("accuracy") is not None
                    else {}
                )
            )
        except (TypeError, ValueError):
            loc = ""
    try:
        with transaction.atomic():
            alert = PanicAlert.objects.create(
                estate=estate,
                raised_by=user,
                member=member,
                kind=kind,
                silent=bool(silent),
                location=loc,
                client_id=client_id,
                channel=channel,
            )
            IncidentNote.objects.create(alert=alert, author=user, kind="triggered")
    except IntegrityError:  # the same client_id raced in
        return PanicAlert.objects.get(client_id=client_id), False
    audit.record(
        "security.alert_raised",
        actor=user,
        organization=estate.organization,
        obj=alert,
        changes={"kind": kind, "silent": bool(silent), "location": bool(loc)},
    )
    transaction.on_commit(lambda: _after_raise(alert.pk))
    return alert, True


def _after_raise(alert_id) -> None:
    from . import tasks

    alert = PanicAlert.objects.select_related("estate", "member__unit").get(pk=alert_id)
    broadcast(alert, "alert.new")
    tasks.fan_out.apply_async(args=[str(alert_id)], priority=9)


def set_kind(alert: PanicAlert, *, kind: str, by) -> PanicAlert:
    """'What's happening?' after the hold: the person (or staff) says what kind of emergency it is."""
    if kind not in PanicAlert.Kind.values or kind == PanicAlert.Kind.DRILL:
        raise serializers.ValidationError({"kind": [_("Choose what's happening.")]})
    if not alert.is_open:
        raise WrongState()
    alert.kind = kind
    alert.save(update_fields=["kind", "updated_at"])
    IncidentNote.objects.create(alert=alert, author=by, kind="kind", note=alert.get_kind_display())
    broadcast(alert, "alert.updated")
    return alert


# ---- Fan-out ------------------------------------------------------------------------------------


def _message(alert: PanicAlert) -> tuple[str, str]:
    house = _house(alert)
    who = (
        alert.member.full_name
        if alert.member_id
        else (alert.raised_by.full_name if alert.raised_by_id else "")
    )
    if alert.kind == PanicAlert.Kind.DRILL:
        return (
            _t("TEST: %(estate)s alert drill") % {"estate": alert.estate.name},
            _t("This is only a test of panic alerts. Open the app to confirm you got it."),
        )
    title = _t("EMERGENCY at %(estate)s: %(kind)s") % {
        "estate": alert.estate.name,
        "kind": alert.get_kind_display(),
    }
    body = _t("%(who)s, %(house)s needs help now. Open Homesika.") % {
        "who": who or _t("A resident"),
        "house": house or alert.estate.name,
    }
    return title, body


def recipients(alert: PanicAlert) -> list[tuple]:
    """(user or None, phone, audience) for everyone who must hear about this alert."""
    out, seen = [], set()
    staff = Membership.objects.filter(
        organization=alert.estate.organization, status="active", role__in=STAFF_ROLES, user__isnull=False
    ).select_related("user")
    for m in staff:
        if m.user_id not in seen and m.user_id != alert.raised_by_id:
            seen.add(m.user_id)
            out.append((m.user, m.user.phone_number, AlertDelivery.Audience.STAFF))
    if not alert.silent and alert.estate.alert_residents and alert.kind != PanicAlert.Kind.DRILL:
        for m in alert.estate.members.filter(status=EstateMember.Status.APPROVED).select_related("user"):
            uid = m.user_id
            mine = m.pk == alert.member_id or (uid is not None and uid == alert.raised_by_id)
            if mine or (uid and uid in seen) or m.phone_number in seen:
                continue
            seen.add(uid or m.phone_number)
            out.append((m.user, m.phone_number, AlertDelivery.Audience.RESIDENT))
    return out


def _sms(alert: PanicAlert, d: AlertDelivery, text: str) -> None:
    note = notify_sms(
        to=d.phone_number,
        body=text[:480],
        kind="panic_alert",
        user=d.user,
        organization=alert.estate.organization,
    )
    d.notification, d.status, d.sent_at = note, D.SENT, timezone.now()
    d.save(update_fields=["notification", "status", "sent_at", "updated_at"])


def fan_out(alert_id) -> dict:
    alert = PanicAlert.objects.select_related("estate__organization", "member__unit", "raised_by").get(
        pk=alert_id
    )
    if alert.deliveries.exclude(audience=AlertDelivery.Audience.RAISER).exists():
        return {"skipped": True}  # already fanned out (task retried)
    title, body = _message(alert)
    people = recipients(alert)
    tokens = push.active_tokens({u.pk for u, _p, _a in people if u is not None})
    pushes, rows = [], []
    for user, phone, audience in people:
        for token in tokens.get(getattr(user, "pk", None), []):
            rows.append(
                AlertDelivery(
                    alert=alert,
                    user=user,
                    phone_number=phone,
                    audience=audience,
                    channel=AlertDelivery.Channel.PUSH,
                    push_token=token,
                )
            )
            pushes.append(
                push.Push(
                    token=token,
                    title=title,
                    body=body,
                    urgent=True,
                    data={"type": "panic", "alert": str(alert.pk), "estate": str(alert.estate_id)},
                )
            )
    AlertDelivery.objects.bulk_create(rows)
    dead = []
    if pushes:
        try:
            tickets = push.provider().send(pushes)
        except push.PushError as exc:
            tickets = [push.Ticket(False, error=f"unreachable: {exc}")] * len(pushes)
        now = timezone.now()
        for row, t in zip(rows, tickets, strict=False):
            row.status = D.SENT if t.ok else D.FAILED
            row.provider_ref, row.error, row.sent_at = t.id, t.error[:200], now if t.ok else None
            if t.error == "DeviceNotRegistered":
                dead.append(row.push_token)
        AlertDelivery.objects.bulk_update(rows, ["status", "provider_ref", "error", "sent_at", "updated_at"])
        push.deactivate(dead)
    text = f"{title}. {body}"
    sms_count = 0
    for user, phone, audience in people:
        if not phone:
            continue
        mine = [r for r in rows if r.user_id == getattr(user, "pk", None) and user is not None]
        push_ok = any(r.status == D.SENT for r in mine)
        staff_always = audience == AlertDelivery.Audience.STAFF and settings.PANIC_SMS_STAFF_ALWAYS
        if staff_always or not push_ok:
            d = AlertDelivery.objects.create(
                alert=alert,
                user=user,
                phone_number=phone,
                audience=audience,
                channel=AlertDelivery.Channel.SMS,
                fallback_for=mine[0] if (mine and not staff_always) else None,
            )
            _sms(alert, d, text)
            sms_count += 1
    if not alert.silent and alert.kind != PanicAlert.Kind.DRILL:
        _tell_raiser(alert, _t("Homesika: your alert was sent to estate security. If you can, call 112 too."))
    return {"push": len(pushes), "sms": sms_count, "recipients": len(people)}


def _tell_raiser(alert: PanicAlert, text: str) -> None:
    """Never for silent alerts: a sound or message on the raiser's phone could put them at risk."""
    if alert.silent:
        return
    if not alert.raised_by_id:  # a resident with no app account (raised on WhatsApp): SMS only
        if alert.member_id:
            notify_sms(
                to=alert.member.phone_number,
                body=text,
                kind="panic_status",
                organization=alert.estate.organization,
            )
        return
    user = alert.raised_by
    toks = push.active_tokens({user.pk}).get(user.pk, [])
    ok = False
    if toks:
        try:
            ok = any(
                t.ok
                for t in push.provider().send(
                    [
                        push.Push(
                            token=t,
                            title=alert.estate.name,
                            body=text,
                            urgent=True,
                            data={"type": "panic_status", "alert": str(alert.pk)},
                        )
                        for t in toks
                    ]
                )
            )
        except push.PushError:
            ok = False
    if not ok:
        notify_sms(
            to=user.phone_number,
            body=text,
            kind="panic_status",
            user=user,
            organization=alert.estate.organization,
        )


def check_deliveries(now=None) -> dict:
    """Every minute: confirm pushes with Expo receipts; SMS anyone whose push failed or wasn't confirmed
    in time (open alerts only). Also mark SMS deliveries delivered when the SMS provider sent them."""
    now = now or timezone.now()
    cutoff = now - timedelta(seconds=settings.PANIC_PUSH_FALLBACK_SECONDS)
    pending = list(
        AlertDelivery.objects.filter(
            channel=AlertDelivery.Channel.PUSH,
            status=D.SENT,
            sent_at__lt=cutoff,
            alert__status__in=PanicAlert.OPEN,
        ).select_related("alert__estate__organization", "alert__member__unit", "alert__raised_by", "user")[
            :500
        ]
    )
    receipts = {}
    ids = [d.provider_ref for d in pending if d.provider_ref]
    if ids:
        try:
            receipts = push.provider().receipts(ids)
        except push.PushError:
            receipts = {}
    counts = {"delivered": 0, "fallback_sms": 0}
    for d in pending:
        r = receipts.get(d.provider_ref)
        if r is not None and r.ok:
            d.status, d.delivered_at = D.DELIVERED, now
            d.save(update_fields=["status", "delivered_at", "updated_at"])
            counts["delivered"] += 1
            continue
        if r is not None:
            d.status, d.error = D.FAILED, r.error[:200]
            d.save(update_fields=["status", "error", "updated_at"])
            if r.error == "DeviceNotRegistered":
                push.deactivate([d.push_token])
        elif d.sent_at > now - timedelta(seconds=settings.PANIC_PUSH_FALLBACK_SECONDS * 2):
            continue  # no receipt yet: give it one more window
        counts["fallback_sms"] += int(_fallback_sms(d))
    sms_rows = AlertDelivery.objects.filter(
        channel=AlertDelivery.Channel.SMS, status=D.SENT, notification__status="sent"
    ).select_related("notification")
    for d in sms_rows[:500]:
        d.status, d.delivered_at = D.DELIVERED, d.notification.sent_at or now
        d.save(update_fields=["status", "delivered_at", "updated_at"])
    AlertDelivery.objects.filter(
        channel=AlertDelivery.Channel.SMS, status=D.SENT, notification__status="failed"
    ).update(status=D.FAILED, error="sms failed")
    return counts


def _fallback_sms(d: AlertDelivery) -> bool:
    """SMS this person unless they're already reached (another push delivered/seen, or an SMS exists)."""
    reached = (
        AlertDelivery.objects.filter(alert=d.alert, user=d.user)
        .filter(status__in=(D.DELIVERED, D.ACKNOWLEDGED))
        .exists()
        if d.user_id
        else False
    )
    has_sms = AlertDelivery.objects.filter(
        alert=d.alert, phone_number=d.phone_number, channel=AlertDelivery.Channel.SMS
    ).exists()
    if reached or has_sms or not d.phone_number:
        return False
    title, body = _message(d.alert)
    sms = AlertDelivery.objects.create(
        alert=d.alert,
        user=d.user,
        phone_number=d.phone_number,
        audience=d.audience,
        channel=AlertDelivery.Channel.SMS,
        fallback_for=d,
    )
    _sms(d.alert, sms, f"{title}. {body}")
    return True


def received(alert: PanicAlert, *, user) -> int:
    """The app says this person got (and opened or saw) the alert."""
    now = timezone.now()
    return (
        alert.deliveries.filter(user=user, channel=AlertDelivery.Channel.PUSH)
        .exclude(status=D.ACKNOWLEDGED)
        .update(status=D.ACKNOWLEDGED, delivered_at=now, updated_at=now)
    )


# ---- Lifecycle ----------------------------------------------------------------------------------


def _lock(alert):
    return (
        PanicAlert.objects.select_for_update(of=("self",))
        .select_related("estate__organization", "member__unit", "raised_by")
        .get(pk=alert.pk)
    )


@transaction.atomic
def acknowledge(alert: PanicAlert, *, by) -> PanicAlert:
    alert = _lock(alert)
    if alert.status != A.TRIGGERED:
        raise WrongState()
    alert.status, alert.acknowledged_at, alert.acknowledged_by = A.ACKNOWLEDGED, timezone.now(), by
    alert.save(update_fields=["status", "acknowledged_at", "acknowledged_by", "updated_at"])
    IncidentNote.objects.create(alert=alert, author=by, kind="acknowledged")
    received(alert, user=by)
    transaction.on_commit(
        lambda: (
            broadcast(alert, "alert.updated"),
            _tell_raiser(alert, _t("Homesika: estate security has seen your alert.")),
        )
    )
    return alert


@transaction.atomic
def respond(alert: PanicAlert, *, by, note="") -> PanicAlert:
    alert = _lock(alert)
    if alert.status not in (A.TRIGGERED, A.ACKNOWLEDGED):
        raise WrongState()
    now = timezone.now()
    alert.acknowledged_at = alert.acknowledged_at or now
    alert.acknowledged_by = alert.acknowledged_by or by
    alert.status, alert.responding_at, alert.responding_by = A.RESPONDING, now, by
    alert.save(
        update_fields=[
            "status",
            "acknowledged_at",
            "acknowledged_by",
            "responding_at",
            "responding_by",
            "updated_at",
        ]
    )
    IncidentNote.objects.create(alert=alert, author=by, kind="responding", note=note[:1000])
    transaction.on_commit(
        lambda: (
            broadcast(alert, "alert.updated"),
            _tell_raiser(alert, _t("Homesika: security is on the way.")),
        )
    )
    return alert


@transaction.atomic
def close(alert: PanicAlert, *, by, outcome: str, note: str) -> PanicAlert:
    """outcome: resolved | false_alarm (staff), cancelled (the raiser: 'I'm safe')."""
    alert = _lock(alert)
    if not alert.is_open:
        raise WrongState()
    if outcome not in (A.RESOLVED, A.FALSE_ALARM, A.CANCELLED):
        raise serializers.ValidationError({"outcome": [_("Choose resolved, false alarm or cancelled.")]})
    if outcome != A.CANCELLED and not note.strip():
        raise serializers.ValidationError({"note": [_("Write what happened, for the incident log.")]})
    alert.status, alert.closed_at, alert.closed_by, alert.close_note = (
        outcome,
        timezone.now(),
        by,
        note.strip()[:500],
    )
    alert.save(update_fields=["status", "closed_at", "closed_by", "close_note", "updated_at"])
    IncidentNote.objects.create(alert=alert, author=by, kind=outcome, note=note[:1000])
    audit.record(f"security.alert_{outcome}", actor=by, organization=alert.estate.organization, obj=alert)

    def after():
        broadcast(alert, "alert.updated")
        if alert.kind == PanicAlert.Kind.DRILL:
            return
        reached = (
            AlertDelivery.objects.filter(alert=alert, channel=AlertDelivery.Channel.PUSH)
            .exclude(status=D.FAILED)
            .values_list("push_token", flat=True)
            .distinct()
        )
        if outcome != A.CANCELLED:
            msg = _t("All clear at %(estate)s: the alert is over.") % {"estate": alert.estate.name}
        else:
            msg = _t("%(estate)s: the resident cancelled the alert. They say they're safe.") % {
                "estate": alert.estate.name
            }
        tokens = list(reached)
        if tokens:
            try:
                push.provider().send(
                    [
                        push.Push(
                            token=t,
                            title=alert.estate.name,
                            body=msg,
                            data={"type": "panic_status", "alert": str(alert.pk)},
                        )
                        for t in tokens
                    ]
                )
            except push.PushError:
                logger.warning("All-clear push failed for alert %s", alert.pk)
        if outcome != A.CANCELLED:
            _tell_raiser(alert, msg)

    transaction.on_commit(after)
    return alert


def add_note(alert: PanicAlert, *, by, note: str) -> IncidentNote:
    if not note.strip():
        raise serializers.ValidationError({"note": [_("Write a note.")]})
    n = IncidentNote.objects.create(alert=alert, author=by, note=note.strip()[:1000])
    broadcast(alert, "alert.updated")
    return n


def drill(*, estate: Estate, by) -> PanicAlert:
    """A clearly marked TEST to security and managers only, to prove delivery works end to end."""
    alert = PanicAlert.objects.create(
        estate=estate, raised_by=by, kind=PanicAlert.Kind.DRILL, silent=True, channel="web"
    )
    IncidentNote.objects.create(alert=alert, author=by, kind="drill")
    audit.record("security.drill", actor=by, organization=estate.organization, obj=alert)
    transaction.on_commit(lambda: _after_raise(alert.pk))
    return alert


# ---- Reporting ----------------------------------------------------------------------------------


def metrics(alert: PanicAlert) -> dict:
    """Seconds from raising to the first delivery per channel and audience, and to acknowledgement."""
    out: dict = {"recipients": 0, "by_channel": {}}
    rows = alert.deliveries.all()
    out["recipients"] = len({(d.user_id or d.phone_number) for d in rows if d.audience != "raiser"})
    for ch in ("push", "sms"):
        chan = [d for d in rows if d.channel == ch]
        firsts = [d.delivered_at for d in chan if d.delivered_at]
        out["by_channel"][ch] = {
            "sent": sum(1 for d in chan if d.status != D.FAILED),
            "delivered": sum(1 for d in chan if d.status in (D.DELIVERED, D.ACKNOWLEDGED)),
            "failed": sum(1 for d in chan if d.status == D.FAILED),
            "first_delivery_seconds": round((min(firsts) - alert.created_at).total_seconds(), 1)
            if firsts
            else None,
        }
    staff = [d for d in rows if d.audience == "staff"]
    out["staff_reached"] = len(
        {d.user_id for d in staff if d.status in (D.SENT, D.DELIVERED, D.ACKNOWLEDGED)}
    )
    out["staff_total"] = len({d.user_id for d in staff})
    out["acknowledge_seconds"] = (
        round((alert.acknowledged_at - alert.created_at).total_seconds(), 1)
        if alert.acknowledged_at
        else None
    )
    return out


def false_alarms(user, *, days=90) -> int:
    if user is None:
        return 0
    return PanicAlert.objects.filter(
        raised_by=user, status=A.FALSE_ALARM, created_at__gte=timezone.now() - timedelta(days=days)
    ).count()


def delivery_report(estate: Estate, *, days=30) -> dict:
    """For the dashboard: alerts in the window and the median time to first delivery."""
    alerts = PanicAlert.objects.filter(estate=estate, created_at__gte=timezone.now() - timedelta(days=days))
    times = []
    for a in alerts.annotate(first=Min("deliveries__delivered_at")):
        if a.first:
            times.append((a.first - a.created_at).total_seconds())
    times.sort()
    median = times[len(times) // 2] if times else None
    return {
        "alerts": alerts.exclude(kind=PanicAlert.Kind.DRILL).count(),
        "drills": alerts.filter(kind=PanicAlert.Kind.DRILL).count(),
        "false_alarms": alerts.filter(status=A.FALSE_ALARM).count(),
        "median_first_delivery_seconds": round(median, 1) if median is not None else None,
    }
