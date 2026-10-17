from datetime import timedelta

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.test_auth import sign_up
from apps.bills import services as bills
from apps.bills.models import Order
from apps.bills.tests.test_bills import buy, ikeja, mtn, pay, prepaid
from apps.referrals import services
from apps.referrals.models import FeeWaiver, Referral
from conftest import make_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def ada(db):
    return make_user(phone="+2348031110001", first="Ada")


def electricity(api_client, key="bill-key-0000000001"):
    return buy(
        api_client,
        biller=str(ikeja().pk),
        plan=str(prepaid().pk),
        customer_id="45123456789",
        amount="5000",
        key=key,
    )


def test_sign_up_with_code_gives_free_fees_and_rewards_the_referrer_after_first_purchase(
    api_client, ada, _sms_outbox
):
    code = services.code_for(ada).code
    bad = api_client.post(
        reverse("v1:register"),
        {
            "first_name": "B",
            "last_name": "C",
            "phone_number": "08099999998",
            "accept_terms": True,
            "referral_code": "NOPE123",
        },
        format="json",
    )
    assert bad.status_code == 400 and "referral_code" in bad.json()["error"]["details"]

    sign_up(api_client, _sms_outbox, referral_code=code.lower())
    chidi = User.objects.get(phone_number="+2348099999999")
    ref = Referral.objects.get(referred=chidi)
    assert ref.referrer == ada and ref.status == "pending"
    assert services.available(chidi).count() == 3 and services.available(ada).count() == 0

    api_client.force_authenticate(chidi)
    r = electricity(api_client)
    assert r.status_code == 201, r.json()
    assert r.json()["fee"] == "0.00" and r.json()["fee_waived"] == "100.00" and r.json()["total"] == "5000.00"
    order = Order.objects.get()
    pay(order)
    order.refresh_from_db()
    assert order.status == "delivered" and order.paid_amount == 5000_00
    ref.refresh_from_db()
    assert ref.status == "qualified" and ref.qualified_by == "bill"
    assert services.available(ada).count() == 3 and services.available(chidi).count() == 2
    assert any("thanks for inviting" in t for p, t in _sms_outbox if p == ada.phone_number)

    summary = api_client.get(reverse("v1:my-referral")).json()
    assert summary["waivers_available"] == 2 and summary["can_redeem"] is False
    assert summary["code"] in summary["share_message"]


def test_no_waiver_on_fee_free_bills_and_released_when_unpaid_or_refunded(api_client, ada):
    services._grant(ada, 1, FeeWaiver.Reason.GOODWILL)
    api_client.force_authenticate(ada)
    airtime = buy(api_client, biller=str(mtn().pk), customer_id="08031110001", amount="1000").json()
    assert airtime["fee_waived"] == "0.00"  # airtime has no fee: the waiver is kept
    assert services.available(ada).count() == 1

    electricity(api_client, key="bill-key-0000000002")
    order = Order.objects.get(category="electricity")
    assert services.available(ada).count() == 0
    Order.objects.filter(pk=order.pk).update(expires_at=timezone.now() - timedelta(hours=2))
    bills.reconcile()
    assert services.available(ada).count() == 1  # the unpaid order gave it back

    # paid but undeliverable, so refunded: the waiver is given back too
    buy(
        api_client,
        biller=str(ikeja().pk),
        plan=str(prepaid().pk),
        customer_id="45123451111",
        amount="5000",
        key="bill-key-0000000003",
    )
    order = Order.objects.get(status="awaiting_payment", category="electricity")
    assert order.fee_waived == 100_00 and services.available(ada).count() == 0
    pay(order)
    order.refresh_from_db()
    assert order.status == "refunded"
    assert services.available(ada).count() == 1


def test_rules(api_client, ada):
    chidi = make_user(phone="+2348031110002", first="Chidi")
    with pytest.raises(Exception, match="own code"):
        services.attribute(ada, services.code_for(ada).code)
    services.attribute(chidi, services.code_for(ada).code)
    with pytest.raises(Exception, match="already used"):
        services.attribute(chidi, services.code_for(ada).code)
    old = make_user(phone="+2348031110003", first="Old")
    User.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=30))
    old.refresh_from_db()
    with pytest.raises(Exception, match="new accounts"):
        services.attribute(old, services.code_for(ada).code)
    # expired waivers don't count
    FeeWaiver.objects.filter(user=chidi).update(expires_at=timezone.now() - timedelta(days=1))
    assert services.available(chidi).count() == 0


@override_settings(REFERRAL_MONTHLY_CAP=1)
def test_monthly_cap(ada):
    for i, phone in enumerate(["+2348031110005", "+2348031110006"]):
        u = make_user(phone=phone, first=f"U{i}")
        services.attribute(u, services.code_for(ada).code)
        services.qualify(u, by="bill")
    assert list(Referral.objects.order_by("created_at").values_list("status", flat=True)) == [
        "qualified",
        "capped",
    ]
    assert services.available(ada).count() == 3


def test_redeem_later_endpoint(api_client, ada):
    chidi = make_user(phone="+2348031110002", first="Chidi")
    api_client.force_authenticate(chidi)
    assert api_client.get(reverse("v1:my-referral")).json()["can_redeem"] is True
    r = api_client.post(
        reverse("v1:my-referral-redeem"), {"code": services.code_for(ada).code}, format="json"
    )
    assert r.status_code == 200 and r.json()["waivers_available"] == 3 and r.json()["can_redeem"] is False


def test_online_rent_payment_qualifies(org, user, ada):
    from apps.payments import services as payments
    from apps.payments.gateways import MockGateway
    from apps.payments.tests.test_payments import make_lease

    tenant = make_lease(org, user, phone="+2348031110009")
    chidi = make_user(phone="+2348031110009", first="Chidi")
    tenant.user = chidi
    tenant.save()
    services.attribute(chidi, services.code_for(ada).code)
    payments.register_settlement_account(
        org=org, bank_code="058", bank_name="GTB", account_number="0123456789", account_name="Obi", by=user
    )
    from apps.leasing.models import Charge

    charge = Charge.objects.filter(tenant=tenant, status__in=Charge.OUTSTANDING).first()
    link = payments.start_checkout(payments.create_link(org=org, tenant=tenant, charge_ids=[charge.pk]))
    MockGateway.complete(link.gateway_reference)
    payments.confirm("mock", link.gateway_reference)
    assert Referral.objects.get(referred=chidi).status == "qualified"
