"""
Rent and dues payments. Money settles straight to the landlord's bank via a gateway subaccount;
Homesika records it but never holds it (ADR-0002).

    staff or tenant: create_link(charges) -> payer opens it -> start_checkout (gateway failover)
    -> webhook/return -> confirm(): re-verify with the gateway API, record once, allocate to charges
       (oldest first), issue a receipt, notify. Daily reconciliation catches anything missed.
"""

import logging
import math
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext as _t
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers, status

from apps.core import audit
from apps.core.exceptions import HomesikaAPIException
from apps.core.money import format_money
from apps.leasing.models import Charge, TenantProfile
from apps.notifications.services import notify

from . import gateways
from .models import Allocation, Payment, PaymentLink, Receipt, ReceiptCounter, SettlementAccount

logger = logging.getLogger(__name__)


class NoPayoutAccount(HomesikaAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = _("Online payment isn't set up yet: the landlord needs to add a payout bank account.")
    default_code = "no_payout_account"


class GatewaysUnavailable(HomesikaAPIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = _("Payments are temporarily unavailable. Please try again in a few minutes.")
    default_code = "gateways_unavailable"


class LinkNotPayable(HomesikaAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = _("This payment link is no longer active.")
    default_code = "link_not_payable"


# ---- Settlement accounts ---------------------------------------------------------------------


def register_settlement_account(*, org, bank_code, bank_name, account_number, account_name, by, request=None):
    """Create the landlord's subaccount on every enabled gateway (both are needed for failover)."""
    results = []
    for name in gateways.enabled():
        gw = gateways.get(name)
        row = SettlementAccount(
            organization=org,
            gateway=name,
            bank_code=bank_code,
            bank_name=bank_name,
            account_number=account_number,
            account_last4=account_number[-4:],
            account_name=account_name,
        )
        try:
            row.subaccount_code = gw.create_subaccount(
                business_name=org.name, bank_code=bank_code, account_number=account_number
            )
            row.status = SettlementAccount.Status.ACTIVE
            SettlementAccount.objects.filter(
                organization=org, gateway=name, status=SettlementAccount.Status.ACTIVE
            ).update(status=SettlementAccount.Status.DISABLED)
        except gateways.GatewayError as exc:
            row.status, row.failure_reason = SettlementAccount.Status.FAILED, str(exc)[:255]
        row.save()
        results.append(row)
    audit.record(
        "payments.settlement_account_added",
        actor=by,
        organization=org,
        changes={
            "bank": bank_name,
            "last4": account_number[-4:],
            "gateways": {r.gateway: r.status for r in results},
        },
        request=request,
    )
    return results


# ---- Payment links ------------------------------------------------------------------------------


def platform_fee(amount: int) -> int:
    pct = Decimal(settings.PLATFORM_FEE_PERCENT)
    if not pct:
        return 0
    fee = math.ceil(Decimal(amount) * pct / 100)
    return min(fee, settings.PLATFORM_FEE_CAP) if settings.PLATFORM_FEE_CAP else fee


@transaction.atomic
def create_link(
    *, org, tenant: TenantProfile, charge_ids, amount: int | None = None, by=None, description: str = ""
) -> PaymentLink:
    charges = list(
        Charge.objects.select_for_update()
        .filter(organization=org, tenant=tenant, pk__in=charge_ids, status__in=Charge.OUTSTANDING)
        .order_by("due_date")
    )
    if not charges or len(charges) != len(set(charge_ids)):
        raise serializers.ValidationError({"charges": [_("Choose unpaid charges of this tenant.")]})
    balance = sum(c.balance for c in charges)
    amount = balance if amount is None else amount
    if amount <= 0 or amount > balance:
        raise serializers.ValidationError(
            {"amount": [_("Amount must be more than zero and at most what is owed.")]}
        )
    link = PaymentLink.objects.create(
        organization=org,
        tenant=tenant,
        amount=amount,
        currency=charges[0].currency,
        description=description or ", ".join(c.description or c.get_kind_display() for c in charges)[:200],
        expires_at=timezone.now() + timedelta(hours=settings.PAYMENT_LINK_TTL_HOURS),
        created_by=by,
    )
    link.charges.set(charges)
    return link


def pay_url(link: PaymentLink) -> str:
    return f"{settings.WEB_APP_URL.rstrip('/')}/pay/{link.reference}"


def _payer_email(tenant: TenantProfile) -> str:
    # Paystack requires an email. Tenants without one get a non-deliverable placeholder on our domain.
    # TODO(verify) with Paystack that this is acceptable for tenants who have no email address.
    email = tenant.email or (tenant.user.email if tenant.user_id and tenant.user.email else "")
    return email or f"{tenant.phone_number.lstrip('+')}@pay.homesika.com"


def start_checkout(link: PaymentLink) -> PaymentLink:
    """Open a gateway session, trying gateways in order (failover). Each attempt gets its own reference."""
    link = PaymentLink.objects.select_related("organization", "tenant__user").get(pk=link.pk)
    if link.status != PaymentLink.Status.PENDING or link.expires_at <= timezone.now():
        raise LinkNotPayable()
    accounts = {
        a.gateway: a
        for a in SettlementAccount.objects.filter(
            organization=link.organization, status=SettlementAccount.Status.ACTIVE
        )
    }
    candidates = [g for g in gateways.enabled() if g in accounts]
    if not candidates:
        raise NoPayoutAccount()
    attempts = list(link.attempts)
    for name in candidates:
        reference = link.reference if not attempts else f"{link.reference}-{len(attempts) + 1}"
        req = gateways.CheckoutRequest(
            reference=reference,
            amount=link.amount,
            currency=link.currency,
            email=_payer_email(link.tenant),
            phone=link.tenant.phone_number,
            name=link.tenant.full_name,
            callback_url=f"{pay_url(link)}/done",
            subaccount_code=accounts[name].subaccount_code,
            platform_fee=platform_fee(link.amount),
            description=link.description,
            metadata={"payment_link": link.reference, "organization": str(link.organization_id)},
        )
        try:
            checkout = gateways.get(name).initialize(req)
        except gateways.GatewayError as exc:
            attempts.append(
                {
                    "gateway": name,
                    "reference": reference,
                    "ok": False,
                    "error": str(exc)[:200],
                    "at": timezone.now().isoformat(),
                }
            )
            logger.warning("Checkout via %s failed for %s; trying next gateway", name, link.reference)
            continue
        attempts.append(
            {
                "gateway": name,
                "reference": checkout.gateway_reference,
                "ok": True,
                "at": timezone.now().isoformat(),
            }
        )
        PaymentLink.objects.filter(pk=link.pk).update(
            gateway=name,
            gateway_reference=checkout.gateway_reference,
            checkout_url=checkout.url,
            attempts=attempts,
            updated_at=timezone.now(),
        )
        link.refresh_from_db()
        return link
    PaymentLink.objects.filter(pk=link.pk).update(attempts=attempts, updated_at=timezone.now())
    raise GatewaysUnavailable()


# ---- Confirmation, allocation, receipts --------------------------------------------------------


def _link_for_reference(reference: str) -> PaymentLink | None:
    base = reference.split("-")[0]
    return PaymentLink.objects.filter(reference=base).first()


def confirm(gateway_name: str, reference: str) -> Payment | None:
    """Re-verify with the gateway API (never trust a webhook or redirect alone), then record exactly once."""
    existing = Payment.objects.filter(gateway=gateway_name, gateway_reference=reference).first()
    if existing:
        return existing
    tx = gateways.get(gateway_name).verify(reference)
    if tx.status != "success":
        return None
    link = _link_for_reference(reference)
    if link is None:
        logger.error("Verified %s payment %s has no payment link", gateway_name, reference)
        return None
    try:
        with transaction.atomic():
            link = PaymentLink.objects.select_for_update().get(pk=link.pk)
            payment = Payment.objects.create(
                organization_id=link.organization_id,
                tenant_id=link.tenant_id,
                payment_link=link,
                gateway=gateway_name,
                gateway_reference=reference,
                channel=tx.channel,
                amount=tx.amount,
                platform_fee_amount=platform_fee(tx.amount),
                gateway_fee_amount=tx.gateway_fee,
                currency=tx.currency or link.currency,
                paid_at=tx.paid_at or timezone.now(),
                verified_payload=tx.raw,
            )
            if payment.currency != link.currency:
                payment.needs_review, payment.review_reason = (
                    True,
                    f"currency {payment.currency} != {link.currency}",
                )
                payment.save(update_fields=["needs_review", "review_reason"])
            else:
                if tx.amount != link.amount:
                    payment.needs_review = True
                    payment.review_reason = f"paid {tx.amount} but link was for {link.amount}"
                    payment.save(update_fields=["needs_review", "review_reason"])
                _allocate(payment, preferred=list(link.charges.order_by("due_date")))
            link.status = PaymentLink.Status.PAID
            link.save(update_fields=["status", "updated_at"])
            receipt = issue_receipt(payment)
    except IntegrityError:
        return Payment.objects.get(gateway=gateway_name, gateway_reference=reference)  # a concurrent call won
    audit.record(
        "payments.received",
        organization=payment.organization,
        obj=payment,
        changes={"amount": payment.amount, "gateway": gateway_name},
    )
    _notify_paid(payment, receipt)
    _qualify_referral(payment)
    return payment


def _qualify_referral(payment: Payment) -> None:
    """An online rent or dues payment is a real first purchase for referrals."""
    from apps.referrals import services as referrals

    try:
        referrals.qualify(payment.tenant.user, by="rent_payment")
    except Exception:  # noqa: BLE001 - never let a reward break a recorded payment
        logger.exception("Referral check failed for payment %s", payment.pk)


def _allocate(payment: Payment, preferred: list[Charge]) -> None:
    """Pay the chosen charges first (oldest due first), then this tenant's other debts with the landlord;
    anything left is an overpayment flagged for the landlord (we hold no balance)."""
    remaining = payment.amount
    others = Charge.objects.filter(
        organization_id=payment.organization_id, tenant_id=payment.tenant_id, status__in=Charge.OUTSTANDING
    ).exclude(pk__in=[c.pk for c in preferred])
    queue = [*preferred, *others.order_by("due_date")]
    # Lock every affected charge once, in primary-key order (no deadlocks between concurrent payments).
    locked = {
        c.pk: c
        for c in Charge.objects.select_for_update().filter(pk__in=[c.pk for c in queue]).order_by("pk")
    }
    for c in queue:
        charge = locked[c.pk]
        if remaining <= 0 or charge.status not in Charge.OUTSTANDING:
            continue
        portion = min(remaining, charge.amount - charge.amount_paid)
        Allocation.objects.create(payment=payment, charge=charge, amount=portion)
        charge.amount_paid += portion
        charge.refresh_status()
        charge.save(update_fields=["amount_paid", "status", "updated_at"])
        remaining -= portion
    if remaining:
        payment.unallocated_amount, payment.needs_review = remaining, True
        payment.review_reason = (
            payment.review_reason + "; " if payment.review_reason else ""
        ) + "overpayment"
        payment.save(update_fields=["unallocated_amount", "needs_review", "review_reason"])


def issue_receipt(payment: Payment) -> Receipt:
    counter, _created = ReceiptCounter.objects.select_for_update().get_or_create(
        organization_id=payment.organization_id
    )
    counter.last += 1
    counter.save(update_fields=["last"])
    return Receipt.objects.create(
        payment=payment, organization_id=payment.organization_id, number=f"RCT-{counter.last:06d}"
    )


def receipt_url(payment: Payment) -> str:
    link = payment.payment_link
    if link:
        return f"{pay_url(link)}/receipt"
    return f"{settings.WEB_APP_URL.rstrip('/')}/receipts/{payment.receipt.public_token}"


def _notify_paid(payment: Payment, receipt: Receipt) -> None:
    tenant = payment.tenant
    amount = format_money(payment.amount, payment.currency, plain=True)
    notify(
        to=tenant.phone_number,
        kind="receipt",
        user=tenant.user,
        organization=payment.organization,
        wa_params=[amount, payment.organization.name, receipt.number, receipt_url(payment)],
        body=_t("Payment of %(amount)s received by %(org)s. Receipt %(number)s: %(url)s")
        % {
            "amount": amount,
            "org": payment.organization.name,
            "number": receipt.number,
            "url": receipt_url(payment),
        },
    )
    owner_phone = payment.organization.phone_number
    if owner_phone:
        notify(
            to=owner_phone,
            kind="payment_received",
            organization=payment.organization,
            wa_params=[tenant.full_name, amount, receipt.number],
            body=_t("Homesika: %(tenant)s paid %(amount)s. Receipt %(number)s.")
            % {"tenant": tenant.full_name, "amount": amount, "number": receipt.number},
        )
    Receipt.objects.filter(pk=receipt.pk).update(sent_at=timezone.now())


@transaction.atomic
def record_manual_payment(
    *,
    org,
    tenant: TenantProfile,
    amount: int,
    channel: str,
    paid_at,
    note: str = "",
    charge_ids=None,
    by,
    request=None,
) -> Payment:
    """Cash or a transfer straight to the landlord: recorded for arrears tracking and a receipt."""
    payment = Payment.objects.create(
        organization=org,
        tenant=tenant,
        gateway="manual",
        gateway_reference=f"MAN-{timezone.now():%Y%m%d%H%M%S%f}",
        channel=channel,
        amount=amount,
        currency=org.currency,
        paid_at=paid_at,
        note=note,
        recorded_by=by,
    )
    preferred = list(
        Charge.objects.filter(organization=org, tenant=tenant, pk__in=charge_ids or []).order_by("due_date")
    )
    _allocate(payment, preferred=preferred)
    receipt = issue_receipt(payment)
    audit.record(
        "payments.manual_recorded",
        actor=by,
        organization=org,
        obj=payment,
        changes={"amount": amount, "channel": channel},
        request=request,
    )
    transaction.on_commit(lambda: _notify_paid(payment, receipt))
    return payment


# ---- Reconciliation ------------------------------------------------------------------------------


def check_pending_links(max_age_hours: int = 72) -> dict:
    """Verify every attempted checkout of recent pending links (catches missed webhooks); expire old links."""
    now = timezone.now()
    found = expired = 0
    for link in PaymentLink.objects.filter(
        status=PaymentLink.Status.PENDING, created_at__gte=now - timedelta(hours=max_age_hours)
    ).exclude(attempts=[]):
        for attempt in [a for a in link.attempts if a.get("ok")]:
            try:
                if confirm(attempt["gateway"], attempt["reference"]):
                    found += 1
                    break
            except gateways.GatewayError as exc:
                logger.warning(
                    "Reconcile %s via %s failed: %s", attempt["reference"], attempt["gateway"], exc
                )
    expired = PaymentLink.objects.filter(status=PaymentLink.Status.PENDING, expires_at__lt=now).update(
        status=PaymentLink.Status.EXPIRED, updated_at=now
    )
    return {"recovered": found, "expired": expired}


def daily_reconciliation(day=None) -> dict:
    """Yesterday's gateway payments are re-verified; anything no longer 'success' is flagged for review."""
    day = day or (timezone.localdate() - timedelta(days=1))
    flagged = 0
    qs = Payment.objects.filter(paid_at__date=day, status=Payment.Status.SUCCEEDED).exclude(gateway="manual")
    for payment in qs:
        try:
            tx = gateways.get(payment.gateway).verify(payment.gateway_reference)
        except gateways.GatewayError as exc:
            logger.warning("Daily reconciliation: verify %s failed: %s", payment.gateway_reference, exc)
            continue
        if tx.status != "success" or tx.amount != payment.amount:
            Payment.objects.filter(pk=payment.pk).update(
                needs_review=True, review_reason=f"reconciliation: gateway now says {tx.status} / {tx.amount}"
            )
            flagged += 1
    total = qs.aggregate(s=Sum("amount"))["s"] or 0
    summary = {
        "day": day.isoformat(),
        "payments": qs.count(),
        "amount": total,
        "flagged": flagged,
        **check_pending_links(),
    }
    logger.info("Daily reconciliation %s", summary)
    return summary
