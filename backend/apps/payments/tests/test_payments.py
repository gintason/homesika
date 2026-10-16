import hashlib
import hmac
import json
from datetime import date, timedelta

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.signals import user_registered
from apps.leasing import services as leasing
from apps.leasing.models import Charge, Lease
from apps.orgs.services import create_organization
from apps.payments import gateways, services
from apps.payments.gateways.mock import SECRET, MockGateway
from apps.payments.models import GatewayEvent, Payment, PaymentLink, Receipt, SettlementAccount
from apps.properties.models import Property, Unit
from conftest import make_user

pytestmark = pytest.mark.django_db
NAIRA = 100  # kobo


def url(name, org, *args):
    return reverse(f"v1:{name}", args=[org.pk, *args])


def make_lease(org, user, *, phone="+2348099999999", rent=100_000 * NAIRA, label="Flat 1"):
    prop, _ = Property.objects.get_or_create(
        organization=org, name="Palm Court", defaults={"address": "Lekki"}
    )
    unit = Unit.objects.create(property=prop, label=label)
    tenant = leasing.create_tenant(org=org, by=user, full_name="Chidi Okafor", phone_number=phone)
    start = date.today().replace(day=1) - timedelta(days=62)
    start = start.replace(day=1)
    from apps.leasing.schedule import add_months

    lease = Lease.objects.create(
        organization=org,
        unit=unit,
        tenant=tenant,
        start_date=start,
        end_date=add_months(start, 12) - timedelta(days=1),
        rent_amount=rent,
        rent_frequency="monthly",
    )
    leasing.activate_lease(lease, by=user)
    return tenant


@pytest.fixture
def tenant(org, user):
    return make_lease(org, user)


@pytest.fixture
def payout(org, user):
    return services.register_settlement_account(
        org=org, bank_code="058", bank_name="GTBank", account_number="0123456789", account_name="Obi", by=user
    )


def first_charges(tenant, n=1):
    return list(Charge.objects.filter(tenant=tenant).order_by("due_date")[:n])


# ---- Settlement accounts ---------------------------------------------------------------------------


def test_settlement_account_is_encrypted_and_owner_only(auth_client, org, user):
    resp = auth_client.post(
        url("settlement-accounts", org),
        {"bank_code": "058", "bank_name": "GTBank", "account_number": "0123456789", "account_name": "Obi"},
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    row = resp.json()[0]
    assert row["gateway"] == "mock" and row["account_last4"] == "6789" and "account_number" not in row
    assert SettlementAccount.objects.get().subaccount_code == "MOCK_SUB_6789"
    from django.db import connection

    with connection.cursor() as c:
        c.execute("SELECT account_number FROM payments_settlementaccount")
        assert "0123456789" not in c.fetchone()[0]

    # A manager can see it but not change where money settles.
    from apps.orgs.services import invite

    manager = make_user(phone="+2348011111111")
    invite(org=org, phone_number=manager.phone_number, role="manager", by=user)
    from apps.orgs.services import link_invites

    link_invites(manager)
    auth_client.force_authenticate(manager)
    assert auth_client.get(url("settlement-accounts", org)).status_code == 200
    bad = auth_client.post(
        url("settlement-accounts", org),
        {"bank_code": "058", "account_number": "0123456789"},
        format="json",
    )
    assert bad.status_code == 403


def test_new_account_replaces_old_one(org, user, payout):
    services.register_settlement_account(
        org=org, bank_code="044", bank_name="Access", account_number="9999999999", account_name="Obi", by=user
    )
    active = SettlementAccount.objects.filter(status="active")
    assert active.count() == 1 and active.get().account_last4 == "9999"


# ---- Links and checkout ---------------------------------------------------------------------------


def test_create_link_and_public_page(auth_client, api_client, org, tenant, payout):
    charges = first_charges(tenant, 2)
    resp = auth_client.post(
        url("payment-link-list", org),
        {"tenant": str(tenant.pk), "charges": [str(c.pk) for c in charges]},
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    body = resp.json()
    assert body["amount"] == "200000.00" and body["url"].endswith(f"/pay/{body['reference']}")

    public = api_client.get(reverse("v1:pay-link", args=[body["reference"]])).json()
    assert public["landlord"] == "Obi Properties" and public["tenant_first_name"] == "Chidi"
    assert public["amount"] == "200000.00" and len(public["items"]) == 2 and public["mock"] is True
    assert "phone" not in json.dumps(public)  # no tenant contact details on a public page


def test_link_rejects_paid_or_foreign_charges(auth_client, org, user, tenant):
    other = make_lease(org, user, phone="+2348077777777", label="Flat 2")
    mine, theirs = first_charges(tenant)[0], first_charges(other)[0]
    resp = auth_client.post(
        url("payment-link-list", org),
        {"tenant": str(tenant.pk), "charges": [str(mine.pk), str(theirs.pk)]},
        format="json",
    )
    assert resp.status_code == 400
    too_much = auth_client.post(
        url("payment-link-list", org),
        {"tenant": str(tenant.pk), "charges": [str(mine.pk)], "amount": "100000.01"},
        format="json",
    )
    assert too_much.status_code == 400


def test_checkout_needs_a_payout_account(api_client, org, tenant):
    link = services.create_link(org=org, tenant=tenant, charge_ids=[first_charges(tenant)[0].pk])
    resp = api_client.post(reverse("v1:pay-checkout", args=[link.reference]))
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "no_payout_account"


@override_settings(PAYMENT_GATEWAYS="paystack,mock")
def test_checkout_fails_over_to_next_gateway(org, user, tenant, monkeypatch):
    def boom(self, req):
        raise gateways.GatewayError("paystack down")

    monkeypatch.setattr(gateways.paystack.PaystackGateway, "create_subaccount", lambda self, **kw: "ACCT_x")
    monkeypatch.setattr(gateways.paystack.PaystackGateway, "initialize", boom)
    services.register_settlement_account(
        org=org, bank_code="058", bank_name="GTB", account_number="0123456789", account_name="Obi", by=user
    )
    link = services.create_link(org=org, tenant=tenant, charge_ids=[first_charges(tenant)[0].pk])
    link = services.start_checkout(link)
    assert link.gateway == "mock" and link.gateway_reference == f"{link.reference}-2"
    assert [a["ok"] for a in link.attempts] == [False, True]


@override_settings(PAYMENT_GATEWAYS="paystack")
def test_all_gateways_down_is_503(api_client, org, user, tenant, monkeypatch):
    monkeypatch.setattr(gateways.paystack.PaystackGateway, "create_subaccount", lambda self, **kw: "ACCT_x")

    def boom(self, req):
        raise gateways.GatewayError("down")

    monkeypatch.setattr(gateways.paystack.PaystackGateway, "initialize", boom)
    services.register_settlement_account(
        org=org, bank_code="058", bank_name="GTB", account_number="0123456789", account_name="Obi", by=user
    )
    link = services.create_link(org=org, tenant=tenant, charge_ids=[first_charges(tenant)[0].pk])
    resp = api_client.post(reverse("v1:pay-checkout", args=[link.reference]))
    assert resp.status_code == 503


def test_expired_or_cancelled_link_cannot_be_paid(auth_client, api_client, org, tenant, payout):
    link = services.create_link(org=org, tenant=tenant, charge_ids=[first_charges(tenant)[0].pk])
    auth_client.post(url("payment-link-cancel", org, link.pk))
    assert api_client.post(reverse("v1:pay-checkout", args=[link.reference])).status_code == 409
    link2 = services.create_link(org=org, tenant=tenant, charge_ids=[first_charges(tenant)[0].pk])
    PaymentLink.objects.filter(pk=link2.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    assert api_client.get(reverse("v1:pay-link", args=[link2.reference])).json()["status"] == "expired"


# ---- Paying, allocation, receipts ------------------------------------------------------------------


def pay_via_mock(api_client, link, **kw):
    assert api_client.post(reverse("v1:pay-checkout", args=[link.reference])).status_code == 200
    return api_client.post(reverse("v1:pay-mock-complete", args=[link.reference]), kw, format="json")


def test_full_payment_flow(api_client, org, tenant, payout, _sms_outbox):
    org.phone_number = "+2348000000001"
    org.save()
    charges = first_charges(tenant, 2)
    link = services.create_link(org=org, tenant=tenant, charge_ids=[c.pk for c in charges])
    assert pay_via_mock(api_client, link).json() == {"status": "paid"}

    payment = Payment.objects.get()
    assert payment.amount == 200_000 * NAIRA and payment.gateway == "mock" and not payment.needs_review
    assert [a.amount for a in payment.allocations.order_by("charge__due_date")] == [100_000 * NAIRA] * 2
    assert {c.status for c in Charge.objects.filter(pk__in=[c.pk for c in charges])} == {"paid"}
    assert Receipt.objects.get().number == "RCT-000001"
    link.refresh_from_db()
    assert link.status == "paid"

    assert {to for to, _ in _sms_outbox} == {tenant.phone_number, "+2348000000001"}
    assert all("RCT-000001" in text and "NGN 200,000.00" in text for _, text in _sms_outbox)

    status = api_client.get(reverse("v1:pay-status", args=[link.reference])).json()
    assert status == {"status": "paid", "receipt_number": "RCT-000001"}
    pdf = api_client.get(reverse("v1:pay-receipt", args=[link.reference]))
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_confirm_is_idempotent(api_client, org, tenant, payout):
    link = services.create_link(org=org, tenant=tenant, charge_ids=[first_charges(tenant)[0].pk])
    pay_via_mock(api_client, link)
    again = services.confirm("mock", link.reference)
    assert again == Payment.objects.get()
    assert Receipt.objects.count() == 1
    assert Charge.objects.get(pk=first_charges(tenant)[0].pk).amount_paid == 100_000 * NAIRA


def test_failed_payment_records_nothing(api_client, org, tenant, payout):
    link = services.create_link(org=org, tenant=tenant, charge_ids=[first_charges(tenant)[0].pk])
    assert pay_via_mock(api_client, link, success=False).json() == {"status": "failed"}
    assert Payment.objects.count() == 0
    assert api_client.get(reverse("v1:pay-status", args=[link.reference])).json()["status"] == "pending"


def test_partial_payment_and_overpayment(org, tenant, payout):
    first, second = first_charges(tenant, 2)
    link = services.create_link(org=org, tenant=tenant, charge_ids=[first.pk], amount=40_000 * NAIRA)
    link = services.start_checkout(link)
    MockGateway.complete(link.gateway_reference)
    services.confirm("mock", link.gateway_reference)
    first.refresh_from_db()
    assert first.status == "part_paid" and first.balance == 60_000 * NAIRA

    # The payer sends more than the link asked for: the rest pays the next charge, then is flagged.
    link2 = services.start_checkout(services.create_link(org=org, tenant=tenant, charge_ids=[first.pk]))
    total_owed = sum(c.balance for c in Charge.objects.filter(tenant=tenant, status__in=Charge.OUTSTANDING))
    MockGateway.complete(link2.gateway_reference, amount=total_owed + 5_000 * NAIRA)
    payment = services.confirm("mock", link2.gateway_reference)
    assert payment.needs_review and payment.unallocated_amount == 5_000 * NAIRA
    assert "overpayment" in payment.review_reason
    second.refresh_from_db()
    assert second.status == "paid"
    assert not Charge.objects.filter(tenant=tenant, status__in=Charge.OUTSTANDING).exists()


def test_manual_payment(auth_client, org, tenant):
    charge = first_charges(tenant)[0]
    resp = auth_client.post(
        url("payment-manual", org),
        {"tenant": str(tenant.pk), "amount": "100000", "channel": "cash", "charges": [str(charge.pk)]},
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    body = resp.json()
    assert body["receipt_number"] == "RCT-000001" and body["gateway"] == "manual"
    assert body["applied_to"][0]["amount"] == "100000.00"
    charge.refresh_from_db()
    assert charge.status == "paid"
    pdf = auth_client.get(url("payment-receipt", org, body["id"]))
    assert pdf.content.startswith(b"%PDF")
    future = auth_client.post(
        url("payment-manual", org),
        {
            "tenant": str(tenant.pk),
            "amount": "1",
            "channel": "cash",
            "paid_at": (timezone.now() + timedelta(days=2)).isoformat(),
        },
        format="json",
    )
    assert future.status_code == 400


def test_receipt_numbers_are_per_org(api_client, org, user, tenant, payout):
    services.record_manual_payment(
        org=org, tenant=tenant, amount=NAIRA, channel="cash", paid_at=timezone.now(), by=user
    )
    owner2 = make_user(phone="+2348022222222")
    org2 = create_organization(user=owner2, name="Other Estates", kind="landlord")
    t2 = make_lease(org2, owner2, phone="+2348033333333")
    p2 = services.record_manual_payment(
        org=org2, tenant=t2, amount=NAIRA, channel="cash", paid_at=timezone.now(), by=owner2
    )
    assert p2.receipt.number == "RCT-000001"


def test_viewer_cannot_record_payments(auth_client, org, user, tenant):
    from apps.orgs.services import invite, link_invites

    viewer = make_user(phone="+2348044444444")
    invite(org=org, phone_number=viewer.phone_number, role="viewer", by=user)
    link_invites(viewer)
    auth_client.force_authenticate(viewer)
    assert auth_client.get(url("payment-list", org)).status_code == 200
    resp = auth_client.post(
        url("payment-manual", org),
        {"tenant": str(tenant.pk), "amount": "1", "channel": "cash"},
        format="json",
    )
    assert resp.status_code == 403


def test_other_org_cannot_see_payments(api_client, org, user, tenant):
    p = services.record_manual_payment(
        org=org, tenant=tenant, amount=NAIRA, channel="cash", paid_at=timezone.now(), by=user
    )
    stranger = make_user(phone="+2348055555555")
    api_client.force_authenticate(stranger)
    assert api_client.get(url("payment-list", org)).status_code == 404
    assert api_client.get(url("payment-receipt", org, p.pk)).status_code == 404
    assert api_client.get(reverse("v1:my-receipt", args=[p.pk])).status_code == 404


# ---- Tenant in the app ------------------------------------------------------------------------------


def test_tenant_pays_in_app(api_client, org, tenant, payout):
    me = make_user(phone=tenant.phone_number, first="Chidi")
    user_registered.send(sender=None, user=me)
    api_client.force_authenticate(me)
    charge = first_charges(tenant)[0]
    resp = api_client.post(reverse("v1:my-pay"), {"charges": [str(charge.pk)]}, format="json")
    assert resp.status_code == 201, resp.json()
    assert resp.json()["gateway"] == "mock" and "/mock-checkout" in resp.json()["checkout_url"]
    link = PaymentLink.objects.get(reference=resp.json()["reference"])
    MockGateway.complete(link.gateway_reference)
    services.confirm("mock", link.gateway_reference)
    mine = api_client.get(reverse("v1:my-payments")).json()["results"]
    assert mine[0]["receipt_number"] == "RCT-000001"
    assert api_client.get(reverse("v1:my-receipt", args=[mine[0]["id"]])).content.startswith(b"%PDF")

    # Someone else's charge is refused.
    other = make_lease(org, make_user(phone="+2348066666666"), phone="+2348088888888", label="Flat 9")
    bad = api_client.post(reverse("v1:my-pay"), {"charges": [str(first_charges(other)[0].pk)]}, format="json")
    assert bad.status_code == 400


# ---- Webhooks and reconciliation --------------------------------------------------------------------


def signed(body: dict) -> tuple[bytes, str]:
    raw = json.dumps(body).encode()
    return raw, hmac.new(SECRET, raw, hashlib.sha256).hexdigest()


def test_webhook_signature_and_idempotency(client, org, tenant, payout):
    link = services.start_checkout(
        services.create_link(org=org, tenant=tenant, charge_ids=[first_charges(tenant)[0].pk])
    )
    MockGateway.complete(link.gateway_reference)
    raw, sig = signed({"event": "charge.success", "data": {"reference": link.gateway_reference}})
    hook = reverse("payment-webhook", args=["mock"])

    assert (
        client.post(hook, raw, content_type="application/json", HTTP_X_MOCK_SIGNATURE="bad").status_code
        == 401
    )
    assert Payment.objects.count() == 0
    for _ in range(2):
        resp = client.post(hook, raw, content_type="application/json", HTTP_X_MOCK_SIGNATURE=sig)
        assert resp.status_code == 200
    assert GatewayEvent.objects.get().status == "processed"
    assert Payment.objects.count() == 1
    assert (
        client.post(
            reverse("payment-webhook", args=["paystack"]), raw, content_type="application/json"
        ).status_code
        == 404
    )  # not enabled


def test_reconciliation_recovers_missed_webhook(org, tenant, payout):
    link = services.start_checkout(
        services.create_link(org=org, tenant=tenant, charge_ids=[first_charges(tenant)[0].pk])
    )
    MockGateway.complete(link.gateway_reference)  # paid, but the webhook never arrived
    stale = services.create_link(org=org, tenant=tenant, charge_ids=[first_charges(tenant, 2)[1].pk])
    PaymentLink.objects.filter(pk=stale.pk).update(expires_at=timezone.now() - timedelta(hours=1))
    result = services.check_pending_links()
    assert result == {"recovered": 1, "expired": 1}
    assert Payment.objects.count() == 1


def test_daily_reconciliation_flags_reversed_payment(org, tenant, payout):
    link = services.start_checkout(
        services.create_link(org=org, tenant=tenant, charge_ids=[first_charges(tenant)[0].pk])
    )
    MockGateway.complete(link.gateway_reference)
    payment = services.confirm("mock", link.gateway_reference)
    MockGateway.complete(link.gateway_reference, success=False)  # gateway later reports a reversal
    summary = services.daily_reconciliation(day=payment.paid_at.date())
    assert summary["flagged"] == 1
    payment.refresh_from_db()
    assert payment.needs_review and "reconciliation" in payment.review_reason


def test_platform_fee():
    with override_settings(PLATFORM_FEE_PERCENT="1.5", PLATFORM_FEE_CAP=200_000):
        assert services.platform_fee(100_000) == 1_500
        assert services.platform_fee(100_000_000) == 200_000
    assert services.platform_fee(100_000) == 0
