"""
Referrals, rewarded with bill fee waivers (no stored value: a waiver removes our own service fee from one
electricity or cable TV purchase; it has no cash value).

* Everyone has a code. Someone who joins with it gets REFERRAL_WAIVERS_NEW_USER waivers at once.
* The referral qualifies on the new person's first real purchase: a delivered bill, or a rent or dues
  payment made online. The referrer then gets REFERRAL_WAIVERS_REFERRER waivers, at most
  REFERRAL_MONTHLY_CAP rewarded referrals a month (more are recorded as "capped").
* Waivers expire after REFERRAL_WAIVER_DAYS. One is used per order that has a fee; if that order isn't
  paid (expires) or is refunded, the waiver is released for the next purchase.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _t
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.core import audit

from .models import FeeWaiver, Referral, ReferralCode

logger = logging.getLogger(__name__)
R = Referral.Status


def code_for(user) -> ReferralCode:
    for _attempt in range(5):
        try:
            with transaction.atomic():
                rc, _made = ReferralCode.objects.get_or_create(user=user)
            return rc
        except IntegrityError:  # code collision (or a parallel request created it)
            existing = ReferralCode.objects.filter(user=user).first()
            if existing:
                return existing
    raise RuntimeError("Couldn't make a referral code")


def find(code: str) -> ReferralCode | None:
    code = "".join(ch for ch in (code or "").upper() if ch.isalnum())
    return (
        ReferralCode.objects.select_related("user").filter(code=code, user__is_active=True).first()
        if code
        else None
    )


def _grant(user, n: int, reason, referral=None) -> int:
    if n <= 0:
        return 0
    expires = timezone.now() + timedelta(days=settings.REFERRAL_WAIVER_DAYS)
    FeeWaiver.objects.bulk_create(
        [FeeWaiver(user=user, reason=reason, referral=referral, expires_at=expires) for _ in range(n)]
    )
    return n


def attribute(user, code: str, *, window_days: int | None = None) -> Referral:
    """Link a new account to whoever invited it: at sign-up, or later ("I have a code") within the window."""
    if not settings.REFERRALS_ENABLED:
        raise serializers.ValidationError({"code": [_("Referrals are not available right now.")]})
    rc = find(code)
    if rc is None:
        raise serializers.ValidationError(
            {"code": [_("We don't recognise this code. Check it with your friend.")]}
        )
    if rc.user_id == user.pk:
        raise serializers.ValidationError({"code": [_("You can't use your own code.")]})
    if Referral.objects.filter(referred=user).exists():
        raise serializers.ValidationError({"code": [_("You've already used a referral code.")]})
    window = window_days if window_days is not None else settings.REFERRAL_REDEEM_DAYS
    if timezone.now() - user.created_at > timedelta(days=window) or _has_purchased(user):
        raise serializers.ValidationError(
            {"code": [_("Codes can only be used by new accounts, before their first purchase.")]}
        )
    try:
        with transaction.atomic():
            ref = Referral.objects.create(referrer=rc.user, referred=user, code=rc.code)
            _grant(user, settings.REFERRAL_WAIVERS_NEW_USER, FeeWaiver.Reason.JOINED_WITH_CODE, ref)
    except IntegrityError as exc:
        raise serializers.ValidationError({"code": [_("You've already used a referral code.")]}) from exc
    audit.record("referrals.joined", actor=user, obj=ref, changes={"referrer": str(rc.user_id)})
    return ref


def _has_purchased(user) -> bool:
    from apps.bills.models import Order
    from apps.payments.models import Payment

    return (
        Order.objects.filter(user=user, status=Order.Status.DELIVERED).exists()
        or Payment.objects.filter(tenant__user=user, status="succeeded").exclude(gateway="manual").exists()
    )


def qualify(user, *, by: str) -> Referral | None:
    """Called after a delivered bill or an online rent/dues payment. Safe to call every time."""
    if user is None or not settings.REFERRALS_ENABLED:
        return None
    with transaction.atomic():
        ref = Referral.objects.select_for_update().filter(referred=user, status=R.PENDING).first()
        if ref is None:
            return None
        now = timezone.now()
        month_start = timezone.localtime(now).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        rewarded = Referral.objects.filter(
            referrer=ref.referrer, status=R.QUALIFIED, qualified_at__gte=month_start
        ).count()
        ref.qualified_at, ref.qualified_by = now, by
        if rewarded >= settings.REFERRAL_MONTHLY_CAP:
            ref.status = R.CAPPED
        else:
            ref.status = R.QUALIFIED
            _grant(ref.referrer, settings.REFERRAL_WAIVERS_REFERRER, FeeWaiver.Reason.REFERRED_SOMEONE, ref)
        ref.save(update_fields=["status", "qualified_at", "qualified_by", "updated_at"])
    if ref.status == R.QUALIFIED:
        _tell_referrer(ref)
    return ref


def _tell_referrer(ref: Referral) -> None:
    from apps.notifications.services import push_or_sms

    referrer = ref.referrer
    push_or_sms(
        recipients=[(referrer, referrer.phone_number)],
        title=_t("Homesika: thanks for inviting %(name)s")
        % {"name": ref.referred.first_name or _t("a friend")},
        body=_t("Your next %(n)s electricity or cable TV service fees are free.")
        % {"n": settings.REFERRAL_WAIVERS_REFERRER},
        kind="referral_reward",
        data={"type": "referral"},
    )


# ---- Using waivers ------------------------------------------------------------------------------------


def available(user):
    return FeeWaiver.objects.filter(user=user, order__isnull=True, expires_at__gt=timezone.now())


def apply_to(order) -> bool:
    """Use one waiver on a new order with a fee (called inside create_order). Returns True if applied."""
    if order.user_id is None or order.fee <= 0:
        return False
    with transaction.atomic():
        waiver = available(order.user).select_for_update(skip_locked=True).order_by("expires_at").first()
        if waiver is None:
            return False
        waiver.order, waiver.used_at = order, timezone.now()
        waiver.save(update_fields=["order", "used_at", "updated_at"])
        order.fee_waived, order.fee = order.fee, 0
        order.total = order.amount
        order.save(update_fields=["fee", "fee_waived", "total", "updated_at"])
    return True


def release(order_ids) -> int:
    """Orders that were never paid, or were refunded: give their waivers back."""
    return FeeWaiver.objects.filter(order_id__in=list(order_ids)).update(
        order=None, used_at=None, updated_at=timezone.now()
    )


def summary(user) -> dict:
    rc = code_for(user)
    waivers = available(user)
    soonest = waivers.first()
    made = Referral.objects.filter(referrer=user)
    url = f"{settings.WEB_APP_URL.rstrip('/')}/join?code={rc.code}"
    return {
        "code": rc.code,
        "share_url": url,
        "share_message": _t(
            "Join me on Homesika for rent, bills, repairs and estate security. Use my code %(code)s when "
            "you sign up and your first electricity or TV fees are free: %(url)s"
        )
        % {"code": rc.code, "url": url},
        "waivers_available": waivers.count(),
        "waivers_expire_at": soonest.expires_at if soonest else None,
        "invited": made.count(),
        "qualified": made.filter(status__in=(R.QUALIFIED, R.CAPPED)).count(),
        "can_redeem": settings.REFERRALS_ENABLED
        and not Referral.objects.filter(referred=user).exists()
        and timezone.now() - user.created_at <= timedelta(days=settings.REFERRAL_REDEEM_DAYS)
        and not _has_purchased(user),
        "enabled": settings.REFERRALS_ENABLED,
    }
