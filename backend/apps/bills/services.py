"""
Bills: the money rules.

1. The person pays the exact total (amount + fee) at the gateway checkout, into Homesika's own account.
2. Only a payment re-verified with the gateway, for the exact amount, is fulfilled; anything else waits for
   review. Nothing is held for later use: no wallet, no balance.
3. Fulfilment sends each order to a provider exactly once per attempt. If a provider *definitely* failed
   (or never created the order), the next provider is tried (failover). If the outcome is unknown (timeout),
   the same provider is re-queried: never a second provider, never a refund, until we know.
4. If no provider delivers, the payment is refunded through the gateway, automatically.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext as _t
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers, status

from apps.accounts.validators import normalise_phone
from apps.core.exceptions import HomesikaAPIException
from apps.core.money import format_money
from apps.notifications.services import notify
from apps.payments import gateways

from . import providers
from .models import Biller, Category, Order, Plan, ReceiptCounter

logger = logging.getLogger(__name__)


class BillsUnavailable(HomesikaAPIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = _("Bill payments are temporarily unavailable. Please try again shortly.")
    default_code = "bills_unavailable"


class VerificationFailed(HomesikaAPIException):
    default_detail = _("We couldn't find that meter or smartcard number. Check it and try again.")
    default_code = "customer_not_found"


class LimitReached(HomesikaAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = _("You've reached today's limit for bill payments. Try again tomorrow.")
    default_code = "bills_daily_limit"


class OrderNotPayable(HomesikaAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = _("This order can no longer be paid. Please start a new one.")
    default_code = "order_not_payable"


# ---- Quote and verification ---------------------------------------------------------------------------


def fee_for(category: str, amount: int) -> int:
    return int((settings.BILLS_FEES or {}).get(category, 0))


def quote(biller: Biller, plan: Plan | None, amount: int | None) -> tuple[int, int, int]:
    """(amount, fee, total) in kobo, or a validation error."""
    if not biller.is_active:
        raise serializers.ValidationError({"biller": [_("This service isn't available right now.")]})
    if plan is not None and (plan.biller_id != biller.pk or not plan.is_active):
        raise serializers.ValidationError({"plan": [_("Choose an available plan.")]})
    if biller.category in (Category.DATA, Category.CABLE_TV, Category.ELECTRICITY) and plan is None:
        raise serializers.ValidationError({"plan": [_("Choose a plan.")]})
    if plan is not None and plan.price:
        amount = plan.price
    if not amount:
        raise serializers.ValidationError({"amount": [_("Enter an amount.")]})
    if amount % 100:
        raise serializers.ValidationError({"amount": [_("Enter a whole naira amount.")]})
    if biller.min_amount and amount < biller.min_amount:
        raise serializers.ValidationError(
            {"amount": [_("The minimum is %(m)s.") % {"m": format_money(biller.min_amount, "NGN")}]}
        )
    if biller.max_amount and amount > biller.max_amount:
        raise serializers.ValidationError(
            {"amount": [_("The maximum is %(m)s.") % {"m": format_money(biller.max_amount, "NGN")}]}
        )
    fee = fee_for(biller.category, amount)
    return amount, fee, amount + fee


def normalise_customer(biller: Biller, customer_id: str) -> str:
    cid = "".join(ch for ch in customer_id if ch.isdigit() or ch == "+")
    if biller.category in (Category.AIRTIME, Category.DATA):
        phone = normalise_phone(cid)
        if len(phone) != 14:  # +234 and 10 digits
            raise serializers.ValidationError({"customer_id": [_("Enter a valid Nigerian phone number.")]})
        return "0" + phone[4:]  # providers take the local 080... form
    if not 6 <= len(cid) <= 20:
        raise serializers.ValidationError({"customer_id": [_("Check the number and try again.")]})
    return cid


def verify_customer(biller: Biller, plan: Plan | None, customer_id: str) -> dict:
    """Ask the first provider that can (meter / smartcard owner). Cached for 10 minutes."""
    key = f"bills:verify:{biller.pk}:{plan.pk if plan else '-'}:{customer_id}"
    cached = cache.get(key)
    if cached:
        return cached
    for name in providers.enabled():
        p = providers.get(name)
        if not p.supports(biller, plan):
            continue
        try:
            result = p.verify_customer(biller, plan, customer_id)
        except providers.ProviderError as exc:
            logger.warning("Verify via %s failed: %s", name, exc)
            continue
        if not result.get("name"):
            raise VerificationFailed()
        cache.set(key, result, 600)
        return result
    raise BillsUnavailable()


# ---- Orders and payment ------------------------------------------------------------------------------


def _spent_today(user, phone: str) -> int:
    since = timezone.now() - timedelta(hours=24)
    qs = Order.objects.filter(created_at__gte=since).exclude(
        status__in=[Order.Status.EXPIRED, Order.Status.REFUNDED]
    )
    qs = qs.filter(user=user) if user else qs.filter(phone_number=phone)
    return qs.aggregate(s=Sum("total"))["s"] or 0


def create_order(
    *,
    user,
    phone: str,
    biller: Biller,
    plan: Plan | None,
    customer_id: str,
    amount: int | None,
    unit=None,
    channel: str = "app",
) -> Order:
    customer_id = normalise_customer(biller, customer_id)
    amount, fee, total = quote(biller, plan, amount)
    if _spent_today(user, phone) + total > settings.BILLS_DAILY_LIMIT:
        raise LimitReached()
    customer_name = ""
    if biller.requires_verification:
        customer_name = verify_customer(biller, plan, customer_id)[
            "name"
        ]  # server-side, never trusted from the client
    if not any(providers.get(n).supports(biller, plan) for n in providers.enabled()):
        raise BillsUnavailable()
    return Order.objects.create(
        user=user,
        phone_number=phone,
        unit=unit,
        category=biller.category,
        biller=biller,
        plan=plan,
        customer_id=customer_id,
        customer_name=customer_name[:150],
        amount=amount,
        fee=fee,
        total=total,
        channel=channel,
        expires_at=timezone.now() + timedelta(minutes=settings.BILLS_PAYMENT_TTL_MINUTES),
    )


def _payer_email(order: Order) -> str:
    email = getattr(order.user, "email", "") if order.user_id else ""
    return (
        email or f"{order.phone_number.lstrip('+')}@pay.homesika.com"
    )  # TODO(verify) placeholder email (as rent)


def describe(order: Order) -> str:
    label = (
        order.plan.name
        if order.plan_id and order.plan.price
        else format_money(order.amount, order.currency, plain=True)
    )
    return f"{order.biller.name} {label} for {order.customer_id}"


def start_checkout(order: Order) -> Order:
    order = Order.objects.select_related("biller", "plan", "user").get(pk=order.pk)
    if order.status != Order.Status.AWAITING_PAYMENT or order.expires_at <= timezone.now():
        raise OrderNotPayable()
    attempts = list(order.payment_attempts)
    for name in gateways.enabled():
        reference = order.reference if not attempts else f"{order.reference}-{len(attempts) + 1}"
        req = gateways.CheckoutRequest(
            reference=reference,
            amount=order.total,
            currency=order.currency,
            email=_payer_email(order),
            phone=order.phone_number,
            name=(order.user.full_name if order.user_id else "") or order.phone_number,
            callback_url=f"{settings.WEB_APP_URL.rstrip('/')}/bills/{order.reference}/done",
            subaccount_code="",
            platform_fee=0,
            description=describe(order)[:200],
            metadata={"bill_order": order.reference},
        )
        try:
            checkout = gateways.get(name).initialize(req)
        except gateways.GatewayError as exc:
            attempts.append({"gateway": name, "reference": reference, "ok": False, "error": str(exc)[:200]})
            continue
        attempts.append({"gateway": name, "reference": checkout.gateway_reference, "ok": True})
        Order.objects.filter(pk=order.pk).update(
            gateway=name,
            gateway_reference=checkout.gateway_reference,
            checkout_url=checkout.url,
            payment_attempts=attempts,
            updated_at=timezone.now(),
        )
        order.refresh_from_db()
        return order
    Order.objects.filter(pk=order.pk).update(payment_attempts=attempts)
    raise BillsUnavailable(_("Payments are temporarily unavailable. Please try again in a few minutes."))


def confirm_payment(gateway_name: str, reference: str) -> Order | None:
    """Re-verify with the gateway, then fulfil. Idempotent: a webhook, a status poll and reconciliation may
    all call this for the same payment."""
    order = Order.objects.filter(reference=reference.split("-")[0]).first()
    if order is None:
        logger.error("Bill payment %s via %s has no order", reference, gateway_name)
        return None
    if order.paid_at:
        return order
    tx = gateways.get(gateway_name).verify(reference)
    if tx.status != "success":
        return None
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.paid_at:
            return order
        order.paid_at, order.paid_amount = tx.paid_at or timezone.now(), tx.amount
        order.gateway, order.gateway_reference = gateway_name, reference
        if tx.amount != order.total or (tx.currency and tx.currency != order.currency):
            order.needs_review = True
            order.review_reason = (
                f"paid {tx.amount} {tx.currency}, order total {order.total} {order.currency}"
            )
            order.status = Order.Status.PROCESSING
            logger.error("Bill %s paid the wrong amount: %s", order.reference, order.review_reason)
        else:
            order.status = Order.Status.PROCESSING  # a late payment on an expired order is still honoured
        order.save()
        if not order.needs_review:
            transaction.on_commit(lambda: _queue("fulfil_order", order.pk))
    return order


def _queue(task: str, order_id, countdown: int = 0) -> None:
    from . import tasks

    getattr(tasks, task).apply_async(args=[str(order_id)], countdown=countdown)


# ---- Fulfilment --------------------------------------------------------------------------------------


def _request_id(order: Order, n: int) -> str:
    return f"HSK{order.reference[3:]}-{n}"  # unique per attempt, <= 50 chars


def _current(order: Order) -> dict | None:
    return order.attempts[-1] if order.attempts else None


def fulfil(order_id) -> Order:
    """Send to the next provider that hasn't definitely failed. One attempt in flight at a time."""
    with transaction.atomic():
        order = (
            Order.objects.select_for_update(of=("self",)).select_related("biller", "plan").get(pk=order_id)
        )
        if order.status != Order.Status.PROCESSING or order.needs_review:
            return order
        last = _current(order)
        if last and last["outcome"] not in (providers.FAILED, providers.REJECTED):
            return order  # an attempt is in flight or unresolved: requery decides
        tried = {a["provider"] for a in order.attempts}
        candidates = [
            n
            for n in providers.enabled()
            if n not in tried and providers.get(n).supports(order.biller, order.plan)
        ]
        if not candidates:
            transaction.on_commit(lambda: _queue("refund_order", order.pk))
            return order
        name = candidates[0]
        rid = _request_id(order, len(order.attempts) + 1)
        order.attempts = [
            *order.attempts,
            {"provider": name, "request_id": rid, "outcome": "sending", "at": timezone.now().isoformat()},
        ]
        order.provider, order.provider_reference, order.status_checks = name, rid, 0
        order.save(
            update_fields=["attempts", "provider", "provider_reference", "status_checks", "updated_at"]
        )
    result = providers.get(name).purchase(order, rid)  # outside the lock: network call
    return _apply(order.pk, result)


def requery(order_id) -> Order:
    order = Order.objects.select_related("biller", "plan").get(pk=order_id)
    last = _current(order)
    if (
        order.status != Order.Status.PROCESSING
        or not last
        or last["outcome"] not in (providers.PROCESSING, providers.UNKNOWN, "sending")
    ):
        return order
    Order.objects.filter(pk=order.pk).update(status_checks=order.status_checks + 1)
    order.status_checks += 1
    result = providers.get(last["provider"]).requery(order, last["request_id"])
    if result.outcome == "not_found":
        # Asked at least twice, a poll apart: the order was never created. Safe to move on.
        result = providers.Result(
            outcome=providers.REJECTED if order.status_checks >= 2 else providers.UNKNOWN,
            message="order not found at provider",
        )
    return _apply(order.pk, result)


def _apply(order_id, result: providers.Result) -> Order:
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.status != Order.Status.PROCESSING:
            return order
        attempts = list(order.attempts)
        attempts[-1] = {
            **attempts[-1],
            "outcome": result.outcome,
            "provider_ref": result.reference,
            "message": result.message[:200],
        }
        order.attempts = attempts
        if result.outcome == providers.DELIVERED:
            order.status, order.delivered_at = Order.Status.DELIVERED, timezone.now()
            order.token, order.units, order.provider_cost = result.token, result.units[:40], result.cost
            order.receipt_number = _next_receipt()
            order.save()
            transaction.on_commit(lambda: _notify_delivered(order))
            return order
        order.save(update_fields=["attempts", "updated_at"])
        if result.outcome in (providers.FAILED, providers.REJECTED):
            transaction.on_commit(
                lambda: _queue("fulfil_order", order.pk)
            )  # failover (or refund if none left)
        elif order.status_checks >= settings.BILLS_MAX_STATUS_CHECKS:
            order.needs_review = True
            order.review_reason = f"no final status from {order.provider} after {order.status_checks} checks"
            order.save(update_fields=["needs_review", "review_reason", "updated_at"])
            logger.error("Bill %s needs review: %s", order.reference, order.review_reason)
        else:
            delay = settings.BILLS_STATUS_POLL_SECONDS * (1 + order.status_checks)
            transaction.on_commit(lambda: _queue("requery_order", order.pk, countdown=delay))
    return order


def _next_receipt() -> str:
    counter, _ = ReceiptCounter.objects.select_for_update().get_or_create(key="bills")
    counter.last += 1
    counter.save(update_fields=["last"])
    return f"BIL-{counter.last:06d}"


def receipt_url(order: Order) -> str:
    return f"{settings.WEB_APP_URL.rstrip('/')}/bills/{order.reference}/done"


def _notify_delivered(order: Order) -> None:
    amount = format_money(order.total, order.currency, plain=True)
    if order.category == Category.ELECTRICITY and order.token:
        body = _t(
            "Homesika: %(biller)s token for meter %(meter)s: %(token)s (%(units)s). Paid "
            "%(amount)s. Receipt %(n)s"
        ) % {
            "biller": order.biller.name,
            "meter": order.customer_id,
            "token": order.token,
            "units": order.units or "-",
            "amount": amount,
            "n": order.receipt_number,
        }
        params = [
            order.biller.name,
            order.customer_id,
            order.token,
            order.units or "-",
            amount,
            order.receipt_number,
        ]
    else:
        body = _t("Homesika: %(what)s delivered. Paid %(amount)s. Receipt %(n)s") % {
            "what": describe(order),
            "amount": amount,
            "n": order.receipt_number,
        }
        params = [describe(order), amount, order.receipt_number]
    notify(
        to=order.phone_number,
        body=body,
        kind="bill_token" if order.token else "bill_delivered",
        user=order.user,
        wa_params=params,
    )


# ---- Refunds -----------------------------------------------------------------------------------------


def refund(order_id) -> Order:
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.status not in (Order.Status.PROCESSING, Order.Status.REFUND_PENDING) or order.needs_review:
            return order
        last = _current(order)
        if (
            order.status == Order.Status.PROCESSING
            and last
            and last["outcome"] not in (providers.FAILED, providers.REJECTED)
        ):
            return order  # never refund while a provider might still deliver
        order.status = Order.Status.REFUND_PENDING
        order.failure_reason = (last or {}).get("message", "no provider could deliver")[:255]
        order.save(update_fields=["status", "failure_reason", "updated_at"])
    try:
        ref = gateways.get(order.gateway).refund(order.gateway_reference, order.paid_amount or order.total)
    except gateways.GatewayError as exc:
        logger.error("Refund of bill %s failed (will retry): %s", order.reference, exc)
        return order
    Order.objects.filter(pk=order.pk).update(
        status=Order.Status.REFUNDED, refund_reference=ref[:80], refunded_at=timezone.now()
    )
    order.refresh_from_db()
    amount = format_money(order.paid_amount or order.total, order.currency, plain=True)
    notify(
        to=order.phone_number,
        kind="bill_refunded",
        user=order.user,
        wa_params=[describe(order), amount],
        body=_t(
            "Homesika: we couldn't deliver %(what)s, so %(amount)s is being refunded to the "
            "card or account you paid "
            "with (usually 1-5 working days)."
        )
        % {"what": describe(order), "amount": amount},
    )
    return order


# ---- Reconciliation ------------------------------------------------------------------------------------


def reconcile() -> dict:
    """Every few minutes: catch missed payment webhooks, expire unpaid orders, nudge stuck fulfilment,
    retry refunds."""
    now = timezone.now()
    paid = expired = nudged = refunds = 0
    for order in Order.objects.filter(
        status=Order.Status.AWAITING_PAYMENT, created_at__gte=now - timedelta(days=2)
    ).exclude(payment_attempts=[]):
        for a in [a for a in order.payment_attempts if a.get("ok")]:
            try:
                if confirm_payment(a["gateway"], a["reference"]):
                    paid += 1
                    break
            except gateways.GatewayError as exc:
                logger.warning("Bill payment check %s failed: %s", a["reference"], exc)
    expired = Order.objects.filter(
        status=Order.Status.AWAITING_PAYMENT, expires_at__lt=now - timedelta(minutes=30)
    ).update(status=Order.Status.EXPIRED, updated_at=now)
    stale = now - timedelta(minutes=10)
    for order in Order.objects.filter(
        status=Order.Status.PROCESSING, needs_review=False, updated_at__lt=stale
    ):
        last = _current(order)
        if not last or last["outcome"] in (providers.FAILED, providers.REJECTED):
            fulfil(order.pk)
        else:
            requery(order.pk)
        nudged += 1
    for order in Order.objects.filter(status=Order.Status.REFUND_PENDING, needs_review=False):
        refund(order.pk)
        refunds += 1
    return {"paid": paid, "expired": expired, "nudged": nudged, "refunds_retried": refunds}
