import json

import pytest
import responses
from django.core.cache import cache
from django.urls import reverse

from apps.bills import services
from apps.bills.models import Order
from apps.bills.providers.reloadly import ACCEPT, AUTH_URL, SANDBOX, Reloadly
from apps.bills.tests.test_bills import pay
from conftest import make_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def buyer(api_client):
    u = make_user(phone="+2348031110001", first="Chidi")
    api_client.force_authenticate(u)
    return u


def test_countries_lookup_and_order_delivered(api_client, buyer, _sms_outbox):
    countries = api_client.get(reverse("v1:bills-intl-countries")).json()
    assert {c["code"] for c in countries} == {"GH", "KE", "GB"}
    r = api_client.post(
        reverse("v1:bills-intl-lookup"), {"country": "GH", "phone": "024 123 4567"}, format="json"
    )
    assert r.status_code == 200, r.json()
    assert r.json()["phone"] == "+233241234567"
    op = r.json()["operator"]
    assert op["name"] == "MTN Ghana (sample)" and op["sample"] is True and op["min_amount"] == "500.00"

    r = api_client.post(
        reverse("v1:bills-intl-orders"),
        {"country": "GH", "phone": "+233241234567", "amount": "5000"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="intl-key-000000001",
    )
    assert r.status_code == 201, r.json()
    body = r.json()
    assert body["category"] == "intl_airtime" and body["total"] == "5000.00" and body["fee"] == "0.00"
    assert body["customer_id"] == "+233241234567" and body["checkout_url"]
    order = Order.objects.get()
    assert order.intl["operator_id"] == "900001" and order.intl["country"] == "GH"
    pay(order)
    order.refresh_from_db()
    assert order.status == "delivered"
    assert any("MTN Ghana (sample) airtime" in t for p, t in _sms_outbox if p == buyer.phone_number)


@pytest.mark.parametrize(
    "body,field",
    [
        ({"country": "NG", "phone": "08031110001", "amount": "1000"}, "country"),
        ({"country": "GH", "phone": "+2348031110001", "amount": "1000"}, "phone"),
        ({"country": "GH", "phone": "+254712345678", "amount": "1000"}, "phone"),
        ({"country": "GH", "phone": "+233241234567", "amount": "100"}, "amount"),  # below the minimum
        ({"country": "GH", "phone": "+233241234567", "amount": "60000"}, "amount"),  # above the maximum
        ({"country": "GB", "phone": "+447700900123", "amount": "7000"}, "amount"),  # not a fixed amount
    ],
)
def test_validation(api_client, buyer, body, field):
    r = api_client.post(reverse("v1:bills-intl-orders"), body, format="json")
    assert r.status_code == 400, r.json()
    assert field in r.json()["error"]["details"]
    assert not Order.objects.exists()


def test_switched_off(api_client, buyer, settings):
    settings.INTL_TOPUP_ENABLED = False
    r = api_client.get(reverse("v1:bills-intl-countries"))
    assert r.status_code == 503 and r.json()["error"]["code"] == "intl_unavailable"


# ---- Reloadly adapter (HTTP mocked; request shapes from Reloadly's official SDK) ----------------------


@pytest.fixture
def reloadly(settings):
    settings.RELOADLY_CLIENT_ID, settings.RELOADLY_CLIENT_SECRET, settings.RELOADLY_LIVE = (
        "cid",
        "secret",
        False,
    )
    cache.clear()
    return Reloadly()


def intl_order(buyer):
    biller = services.intl_biller()
    return Order.objects.create(
        user=buyer,
        phone_number=buyer.phone_number,
        category="intl_airtime",
        biller=biller,
        customer_id="+233241234567",
        amount=5000_00,
        fee=0,
        total=5000_00,
        expires_at="2099-01-01T00:00:00Z",
        intl={"country": "GH", "operator_id": "643"},
    )


@responses.activate
def test_reloadly_auth_and_topup(reloadly, buyer):
    responses.post(AUTH_URL, json={"access_token": "tok", "expires_in": 3600})
    responses.post(
        f"{SANDBOX}/topups",
        json={
            "transactionId": 4521,
            "status": "SUCCESSFUL",
            "requestedAmount": 5000,
            "requestedAmountCurrencyCode": "NGN",
            "deliveredAmount": 37.5,
            "deliveredAmountCurrencyCode": "GHS",
            "customIdentifier": "req-1",
        },
    )
    result = reloadly.purchase(intl_order(buyer), "req-1")
    assert result.outcome == "delivered" and result.reference == "4521" and result.units == "37.5 GHS"
    assert result.cost == 5000_00
    auth = json.loads(responses.calls[0].request.body)
    assert auth == {
        "client_id": "cid",
        "client_secret": "secret",
        "grant_type": "client_credentials",
        "audience": SANDBOX,
    }
    sent = responses.calls[1].request
    assert sent.headers["Accept"] == ACCEPT and sent.headers["Authorization"] == "Bearer tok"
    assert json.loads(sent.body) == {
        "operatorId": 643,
        "amount": 5000.0,
        "useLocalAmount": False,
        "customIdentifier": "req-1",
        "recipientPhone": {"countryCode": "GH", "number": "+233241234567"},
    }


@responses.activate
def test_reloadly_errors_never_double_buy(reloadly, buyer):
    responses.post(AUTH_URL, json={"access_token": "tok"})
    responses.post(
        f"{SANDBOX}/topups", status=400, json={"errorCode": "INSUFFICIENT_BALANCE", "message": "low"}
    )
    order = intl_order(buyer)
    assert reloadly.purchase(order, "req-2").outcome == "rejected"  # never created: safe to refund
    responses.replace(responses.POST, f"{SANDBOX}/topups", status=503, json={})
    assert reloadly.purchase(order, "req-3").outcome == "unknown"  # may exist: requery, never refund
    responses.get(
        f"{SANDBOX}/topups/reports/transaction",
        json={
            "content": [
                {
                    "customIdentifier": "req-3",
                    "transactionId": 77,
                    "status": "SUCCESSFUL",
                    "deliveredAmount": 37.5,
                    "deliveredAmountCurrencyCode": "GHS",
                }
            ]
        },
    )
    found = reloadly.requery(order, "req-3")
    assert found.outcome == "delivered" and found.reference == "77"
    assert responses.calls[-1].request.params == {"customIdentifier": "req-3"}


@responses.activate
def test_reloadly_refreshes_an_expired_token(reloadly, buyer):
    cache.set("reloadly:token", "old", 600)
    responses.get(f"{SANDBOX}/countries", status=401, json={"message": "expired"})
    responses.post(AUTH_URL, json={"access_token": "new"})
    responses.get(f"{SANDBOX}/countries", json=[{"isoName": "GH", "name": "Ghana"}])
    assert reloadly.countries() == [{"isoName": "GH", "name": "Ghana"}]
    assert responses.calls[-1].request.headers["Authorization"] == "Bearer new"


def test_no_keys_means_not_supported(settings):
    settings.RELOADLY_CLIENT_ID = ""
    assert Reloadly().supports(services.intl_biller(), None) is False
