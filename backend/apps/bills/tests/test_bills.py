import hashlib
import hmac
import json
from datetime import timedelta

import pytest
import responses
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.bills import catalogue, providers, services
from apps.bills.models import Biller, Order, Plan
from apps.bills.providers import base as pbase
from apps.bills.providers.mock import MockVtu
from apps.bills.providers.vtung import VtuNg
from apps.payments.gateways.mock import MockGateway
from conftest import make_user

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _reset():
    MockVtu.calls.clear()
    yield


def biller(category, code):
    return Biller.objects.get(category=category, code=code)


def mtn():
    return biller("airtime", "mtn")


def ikeja():
    return biller("electricity", "ikeja-electric")


def prepaid():
    return Plan.objects.get(biller=ikeja(), code="prepaid")


def buy(api_client, **body):
    return api_client.post(
        reverse("v1:bills-orders"),
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY=body.pop("key", None) or "bill-key-0000000001",
    )


def pay(order: Order, amount=None):
    """The person completes the (mock) checkout; the gateway webhook / status poll confirms it."""
    MockGateway.complete(order.gateway_reference, amount=amount)
    return services.confirm_payment("mock", order.gateway_reference)


@pytest.fixture
def buyer(api_client):
    u = make_user(phone="+2348031110001", first="Chidi")
    api_client.force_authenticate(u)
    return u


# ---- Catalogue and rules -----------------------------------------------------------------------------


def test_catalogue_is_seeded_and_samples_load(api_client):
    cats = {b["category"] for b in api_client.get(reverse("v1:bills-catalogue")).json()}
    assert cats == {"airtime", "data", "cable_tv", "electricity"}
    assert Biller.objects.filter(category="electricity").count() == 12
    assert [p.code for p in ikeja().plans.all()] == ["prepaid", "postpaid"]
    assert catalogue.load_samples() > 0
    dstv = api_client.get(reverse("v1:bills-catalogue"), {"category": "cable_tv"}).json()[0]
    assert dstv["plans"][0]["price"] == "4000.00" and "sample" in dstv["plans"][0]["name"]
    # default fees: NGN 100 on electricity and cable TV, nothing on airtime or data
    fees = {b["category"]: b["fee"] for b in api_client.get(reverse("v1:bills-catalogue")).json()}
    assert fees == {"airtime": "0.00", "data": "0.00", "cable_tv": "100.00", "electricity": "100.00"}
    with override_settings(BILLS_FEES={}):
        disco = api_client.get(reverse("v1:bills-catalogue"), {"category": "electricity"}).json()[0]
    assert disco["fee"] == "0.00"


def test_quote_rules():
    assert services.quote(mtn(), None, 1_000_00) == (1_000_00, 0, 1_000_00)
    with pytest.raises(Exception, match="whole naira"):
        services.quote(mtn(), None, 1_000_50)
    with pytest.raises(Exception, match="minimum"):
        services.quote(mtn(), None, 50_00)
    with pytest.raises(Exception, match="maximum"):
        services.quote(mtn(), None, 60_000_00)
    with pytest.raises(Exception, match="plan"):
        services.quote(ikeja(), None, 5_000_00)
    with override_settings(BILLS_FEES={"electricity": 100_00}):
        assert services.quote(ikeja(), prepaid(), 5_000_00) == (5_000_00, 100_00, 5_100_00)
    assert services.normalise_customer(mtn(), "+234 803 111 0001") == "08031110001"


def test_verify_meter(api_client, buyer):
    ok = api_client.post(
        reverse("v1:bills-verify"),
        {"biller": str(ikeja().pk), "plan": str(prepaid().pk), "customer_id": "4512 3456 789"},
        format="json",
    )
    assert (
        ok.status_code == 200
        and ok.json()["name"] == "MOCK CUSTOMER"
        and ok.json()["customer_id"] == "45123456789"
    )
    bad = api_client.post(
        reverse("v1:bills-verify"),
        {"biller": str(ikeja().pk), "plan": str(prepaid().pk), "customer_id": "1234560000"},
        format="json",
    )
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "customer_not_found"


# ---- The happy path -----------------------------------------------------------------------------------


def test_electricity_paid_delivered_with_token_and_receipt(api_client, buyer, _sms_outbox):
    resp = buy(
        api_client, biller=str(ikeja().pk), plan=str(prepaid().pk), customer_id="45123456789", amount="5000"
    )
    assert resp.status_code == 201, resp.json()
    data = resp.json()
    assert (
        data["status"] == "awaiting_payment"
        and data["customer_name"] == "MOCK CUSTOMER"
        and data["checkout_url"]
    )
    assert MockVtu.calls == []  # nothing is bought before payment
    again = buy(
        api_client, biller=str(ikeja().pk), plan=str(prepaid().pk), customer_id="45123456789", amount="5000"
    )
    assert again.json()["id"] == data["id"]  # same Idempotency-Key: no second order

    order = Order.objects.get()
    pay(order)
    order.refresh_from_db()
    assert (
        order.status == "delivered"
        and order.token == "1234-5678-9012-3456-7890"
        and order.receipt_number == "BIL-000001"
    )
    assert [c[0] for c in MockVtu.calls] == ["purchase"]
    assert any("1234-5678-9012-3456-7890" in text for to, text in _sms_outbox if to == "+2348031110001")

    detail = api_client.get(reverse("v1:bills-order", args=[order.pk])).json()
    assert detail["token"] == "1234-5678-9012-3456-7890"
    pdf = api_client.get(reverse("v1:bills-receipt", args=[order.pk]))
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    public = api_client.get(reverse("v1:bills-public-status", args=[order.reference])).json()
    assert public == {"status": "delivered", "receipt_number": "BIL-000001"}  # never the token


def test_status_poll_confirms_payment_without_webhook(api_client, buyer):
    resp = buy(api_client, biller=str(mtn().pk), customer_id="08031110001", amount="1000")
    order = Order.objects.get()
    MockGateway.complete(order.gateway_reference)
    assert api_client.get(reverse("v1:bills-order", args=[order.pk])).json()["status"] == "delivered"
    assert resp.json()["total"] == "1000.00"


def test_payment_webhook_is_routed_to_bills(client, api_client, buyer):
    buy(api_client, biller=str(mtn().pk), customer_id="08031110001", amount="1000")
    order = Order.objects.get()
    MockGateway.complete(order.gateway_reference)
    from apps.payments.gateways.mock import SECRET

    raw = json.dumps({"event": "charge.success", "data": {"reference": order.gateway_reference}}).encode()
    sig = hmac.new(SECRET, raw, hashlib.sha256).hexdigest()
    assert (
        client.post(
            reverse("payment-webhook", args=["mock"]),
            raw,
            content_type="application/json",
            HTTP_X_MOCK_SIGNATURE=sig,
        ).status_code
        == 200
    )
    order.refresh_from_db()
    assert order.status == "delivered"


def test_wrong_amount_paid_is_held_for_review(api_client, buyer):
    buy(api_client, biller=str(mtn().pk), customer_id="08031110001", amount="1000")
    order = Order.objects.get()
    pay(order, amount=500_00)
    order.refresh_from_db()
    assert order.needs_review and order.status == "processing" and MockVtu.calls == []


def test_unpaid_order_cannot_be_fulfilled_and_expires(api_client, buyer):
    buy(api_client, biller=str(mtn().pk), customer_id="08031110001", amount="1000")
    order = Order.objects.get()
    assert services.fulfil(order.pk).status == "awaiting_payment" and MockVtu.calls == []
    Order.objects.filter(pk=order.pk).update(expires_at=timezone.now() - timedelta(hours=2))
    services.reconcile()
    order.refresh_from_db()
    assert order.status == "expired"


# ---- Failure handling ---------------------------------------------------------------------------------


class RejectingVtu(MockVtu):
    name = "down"

    def purchase(self, order, request_id):
        MockVtu.calls.append(("down", request_id))
        return pbase.Result(outcome=pbase.REJECTED, message="float empty")


@pytest.fixture
def two_providers(monkeypatch, settings):
    monkeypatch.setitem(providers._REGISTRY, "down", RejectingVtu)
    settings.BILLS_PROVIDERS = "down,mock"


def test_failover_when_first_provider_rejects(api_client, buyer, two_providers):
    buy(api_client, biller=str(mtn().pk), customer_id="08031110001", amount="1000")
    order = pay(Order.objects.get())
    order.refresh_from_db()
    assert order.status == "delivered" and [a["provider"] for a in order.attempts] == ["down", "mock"]
    assert order.attempts[0]["request_id"] != order.attempts[1]["request_id"]


def test_definite_failure_everywhere_is_refunded(api_client, buyer, _sms_outbox):
    buy(api_client, biller=str(mtn().pk), customer_id="08031111111", amount="1000")
    order = pay(Order.objects.get())
    order.refresh_from_db()
    assert order.status == "refunded" and order.refund_reference.startswith("MOCKREFUND-")
    assert any("refunded" in text for _, text in _sms_outbox)


def test_unknown_outcome_is_never_failed_over_or_refunded_until_known(
    api_client, buyer, two_providers, settings
):
    settings.BILLS_PROVIDERS = "mock,down"
    buy(api_client, biller=str(mtn().pk), customer_id="08031113333", amount="1000")
    order = Order.objects.get()
    MockGateway.complete(order.gateway_reference)
    services.confirm_payment(
        "mock", order.gateway_reference
    )  # purchase timed out; requery #1 (not found) is eager
    order.refresh_from_db()
    # Eager Celery ran the follow-up requeries; only after "not found" twice did it move on.
    assert [c[0] for c in MockVtu.calls[:3]] == ["purchase", "requery", "requery"]
    assert order.status == "refunded"  # the second provider ("down") rejected too, so the money went back
    assert [a["outcome"] for a in order.attempts] == ["rejected", "rejected"]


def test_processing_then_delivered_on_requery(api_client, buyer):
    buy(api_client, biller=str(mtn().pk), customer_id="08031112222", amount="1000")
    order = pay(Order.objects.get())
    order.refresh_from_db()
    assert order.status == "delivered" and [c[0] for c in MockVtu.calls] == ["purchase", "requery"]


def test_stuck_order_goes_to_review(api_client, buyer, monkeypatch, settings):
    settings.BILLS_MAX_STATUS_CHECKS = 2
    monkeypatch.setattr(MockVtu, "requery", lambda self, order, rid: pbase.Result(outcome=pbase.PROCESSING))
    buy(api_client, biller=str(mtn().pk), customer_id="08031112222", amount="1000")
    order = pay(Order.objects.get())
    order.refresh_from_db()
    assert order.needs_review and order.status == "processing" and "no final status" in order.review_reason


def test_refund_failure_is_retried_by_reconciliation(api_client, buyer, monkeypatch):
    from apps.payments.gateways import GatewayError

    def down(self, ref, amount):
        raise GatewayError("refund API down")

    monkeypatch.setattr(MockGateway, "refund", down)
    buy(api_client, biller=str(mtn().pk), customer_id="08031111111", amount="1000")
    order = pay(Order.objects.get())
    order.refresh_from_db()
    assert order.status == "refund_pending"
    monkeypatch.undo()
    services.reconcile()
    order.refresh_from_db()
    assert order.status == "refunded"


def test_no_daily_limit_by_default(api_client, buyer, settings):
    assert settings.BILLS_DAILY_LIMIT == 0
    for n in range(5):  # NGN 250,000 in a day, above the old NGN 200,000 default
        r = buy(
            api_client,
            biller=str(mtn().pk),
            customer_id="08031110001",
            amount="50000",
            key=f"bill-key-nolimit-{n:04d}",
        )
        assert r.status_code == 201


def test_daily_limit(api_client, buyer, settings):
    settings.BILLS_DAILY_LIMIT = 1_500_00
    assert buy(api_client, biller=str(mtn().pk), customer_id="08031110001", amount="1000").status_code == 201
    over = buy(
        api_client, biller=str(mtn().pk), customer_id="08031110001", amount="1000", key="bill-key-0000000002"
    )
    assert over.status_code == 409 and over.json()["error"]["code"] == "bills_daily_limit"


def test_unit_must_be_the_tenants(api_client, buyer, org, user):
    from apps.payments.tests.test_payments import make_lease

    tenant = make_lease(org, user, phone="+2348031110001")
    unit = tenant.leases.get().unit
    ok = buy(
        api_client,
        biller=str(ikeja().pk),
        plan=str(prepaid().pk),
        customer_id="45123456789",
        amount="5000",
        unit=str(unit.pk),
    )
    assert ok.status_code == 201
    other = make_lease(org, user, phone="+2348077777777", label="Flat 9").leases.get().unit
    bad = buy(
        api_client,
        biller=str(ikeja().pk),
        plan=str(prepaid().pk),
        customer_id="45123456789",
        amount="5000",
        unit=str(other.pk),
        key="bill-key-0000000003",
    )
    assert bad.status_code == 400


def test_orders_are_private(api_client, buyer):
    buy(api_client, biller=str(mtn().pk), customer_id="08031110001", amount="1000")
    order = Order.objects.get()
    api_client.force_authenticate(make_user(phone="+2348055555555"))
    assert api_client.get(reverse("v1:bills-order", args=[order.pk])).status_code == 404
    assert api_client.get(reverse("v1:bills-orders")).json()["results"] == []


# ---- VTU.ng adapter (mocked HTTP) and webhook --------------------------------------------------------


@pytest.fixture
def vtung_settings(settings):
    settings.VTUNG_BASE_URL, settings.VTUNG_USERNAME, settings.VTUNG_PASSWORD = (
        "https://vtu.test/wp-json",
        "u",
        "p",
    )
    settings.VTUNG_USER_PIN = "1234"


def _order(category="airtime", customer="08031110001", amount=1_000_00):
    b = mtn() if category == "airtime" else ikeja()
    return Order(
        reference="BILTEST",
        category=category,
        biller=b,
        plan=None if category == "airtime" else prepaid(),
        customer_id=customer,
        amount=amount,
        total=amount,
        expires_at=timezone.now(),
    )


@responses.activate
def test_vtung_purchase_maps_outcomes(vtung_settings):
    responses.post("https://vtu.test/wp-json/jwt-auth/v1/token", json={"token": "jwt"})
    responses.post(
        "https://vtu.test/wp-json/api/v2/airtime",
        json={
            "code": "success",
            "data": {"order_id": 77, "status": "completed-api", "amount_charged": "980"},
        },
    )
    r = VtuNg().purchase(_order(), "HSKABC-1")
    sent = json.loads(responses.calls[1].request.body)
    assert sent == {"request_id": "HSKABC-1", "phone": "08031110001", "service_id": "mtn", "amount": 1000}
    assert responses.calls[1].request.headers["Authorization"] == "Bearer jwt"
    assert (r.outcome, r.reference, r.cost) == ("delivered", "77", 98_000)


@responses.activate
def test_vtung_errors_classified(vtung_settings):
    responses.post("https://vtu.test/wp-json/jwt-auth/v1/token", json={"token": "jwt"})
    responses.post("https://vtu.test/wp-json/api/v2/airtime", status=402, json={"code": "insufficient_funds"})
    assert VtuNg().purchase(_order(), "HSKABC-1").outcome == "rejected"
    responses.replace(responses.POST, "https://vtu.test/wp-json/api/v2/airtime", status=503, json={})
    assert VtuNg().purchase(_order(), "HSKABC-1").outcome == "unknown"
    responses.post("https://vtu.test/wp-json/api/v2/requery", status=404, json={"code": "order_not_found"})
    assert VtuNg().requery(_order(), "HSKABC-1").outcome == "not_found"


@responses.activate
def test_vtung_electricity_token(vtung_settings):
    responses.post("https://vtu.test/wp-json/jwt-auth/v1/token", json={"token": "jwt"})
    responses.post(
        "https://vtu.test/wp-json/api/v2/electricity",
        json={
            "code": "success",
            "data": {"order_id": 9, "status": "completed-api", "token": "1111-2222", "units": "30kWh"},
        },
    )
    r = VtuNg().purchase(_order("electricity", "45123456789", 5_000_00), "HSKABC-1")
    assert json.loads(responses.calls[1].request.body)["variation_id"] == "prepaid"
    assert (r.outcome, r.token, r.units) == ("delivered", "1111-2222", "30kWh") and "token" not in r.raw


def test_vtung_webhook_signature(client, vtung_settings, api_client, buyer):
    raw = json.dumps({"order_id": 77, "status": "completed-api", "request_id": "HSKX-1"}).encode()
    url = reverse("vtung-webhook")
    assert client.post(url, raw, content_type="application/json", HTTP_X_SIGNATURE="bad").status_code == 401
    good = hmac.new(b"1234", raw, hashlib.sha256).hexdigest()
    assert client.post(url, raw, content_type="application/json", HTTP_X_SIGNATURE=good).status_code == 200
    assert (
        client.post(url, raw, content_type="application/json", HTTP_X_SIGNATURE=good).status_code == 200
    )  # dup
    from apps.bills.models import ProviderEvent

    assert ProviderEvent.objects.count() == 1


# ---- WhatsApp buy command -----------------------------------------------------------------------------


def test_assistant_buys_airtime_after_yes(monkeypatch):
    from apps.assistant import llm
    from apps.assistant import services as assistant
    from apps.assistant.principal import for_contact
    from apps.assistant.tests.test_assistant import FakeLlm, text_resp, tool_resp
    from apps.messaging import services as messaging

    fake = FakeLlm(
        tool_resp(
            "buy_bill",
            {
                "category": "airtime",
                "biller_code": "mtn",
                "plan_code": None,
                "number": "08031119999",
                "amount": "1000",
            },
        ),
        text_resp("I'll buy MTN airtime ₦1,000 for 08031119999. Reply YES to confirm."),
    )
    monkeypatch.setattr(llm, "client", lambda: fake)
    convo = messaging.open_conversation(messaging.get_contact("2348031119999", "Kemi"))
    p = for_contact(convo.contact)
    reply = assistant.handle_message(convo, p, "Buy 1000 MTN airtime for 08031119999")
    assert reply.pending_action.tool == "buy_bill" and Order.objects.count() == 0
    done = assistant.handle_message(convo, p, "yes")
    order = Order.objects.get()
    assert (
        order.status == "awaiting_payment"
        and order.channel == "whatsapp"
        and order.phone_number == "+2348031119999"
    )
    assert order.checkout_url in done.text and "1,000" in done.text


@override_settings()
def test_production_refuses_mock_bills(monkeypatch):
    import importlib
    import os

    from django.core.exceptions import ImproperlyConfigured

    env = {
        "DJANGO_SECRET_KEY": "x" * 60,
        "DATABASE_URL": "sqlite:///:memory:",
        "ENVIRONMENT": "production",
        "PAYMENT_GATEWAYS": "paystack",
        "ASSISTANT_PROVIDER": "anthropic",
        "WHATSAPP_PROVIDER": "off",
        "BILLS_PROVIDERS": "vtung,mock",
        "DJANGO_ALLOWED_HOSTS": "x",
    }
    for k, v in env.items():
        monkeypatch.setitem(os.environ, k, v)
    import sys

    import config.settings.base as base

    importlib.reload(base)  # re-read the patched environment
    monkeypatch.delitem(sys.modules, "config.settings.production", raising=False)
    with pytest.raises(ImproperlyConfigured, match="BILLS_PROVIDERS"):
        importlib.import_module("config.settings.production")
    monkeypatch.delitem(sys.modules, "config.settings.production", raising=False)
