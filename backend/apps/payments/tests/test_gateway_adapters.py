"""Adapter tests with mocked HTTP. They check OUR request building and response parsing against the
field names we assumed (several are TODO(verify)); they cannot prove the providers' real behaviour."""

import hashlib
import hmac
import json

import pytest
import responses

from apps.payments.gateways import CheckoutRequest, GatewayError
from apps.payments.gateways.flutterwave import FlutterwaveGateway
from apps.payments.gateways.paystack import PaystackGateway

REQ = CheckoutRequest(
    reference="HSKABC",
    amount=10_000_000,
    currency="NGN",
    email="t@example.com",
    phone="+2348099999999",
    name="Chidi Okafor",
    callback_url="https://app.example/pay/HSKABC/done",
    subaccount_code="ACCT_1",
    platform_fee=50_000,
    description="Rent",
)


class TestPaystack:
    @pytest.fixture(autouse=True)
    def _keys(self, settings):
        settings.PAYSTACK_SECRET_KEY, settings.PAYSTACK_BASE_URL = "sk_test_x", "https://ps.test"

    @responses.activate
    def test_initialize_sends_split_and_kobo(self):
        responses.post(
            "https://ps.test/transaction/initialize",
            json={"status": True, "data": {"authorization_url": "https://checkout/x", "reference": "HSKABC"}},
        )
        checkout = PaystackGateway().initialize(REQ)
        sent = json.loads(responses.calls[0].request.body)
        assert responses.calls[0].request.headers["Authorization"] == "Bearer sk_test_x"
        assert sent["amount"] == 10_000_000 and sent["subaccount"] == "ACCT_1"
        assert sent["transaction_charge"] == 50_000 and sent["bearer"] == "subaccount"
        assert checkout.url == "https://checkout/x" and checkout.gateway_reference == "HSKABC"

    @responses.activate
    def test_verify_maps_status_amount_and_fee(self):
        responses.get(
            "https://ps.test/transaction/verify/HSKABC",
            json={
                "status": True,
                "data": {
                    "status": "success",
                    "reference": "HSKABC",
                    "amount": 10_000_000,
                    "currency": "NGN",
                    "channel": "bank_transfer",
                    "fees": 20_000,
                    "paid_at": "2026-10-16T09:00:00.000Z",
                    "authorization": {"bin": "should-not-be-stored"},
                },
            },
        )
        tx = PaystackGateway().verify("HSKABC")
        assert (tx.status, tx.amount, tx.gateway_fee, tx.channel) == (
            "success",
            10_000_000,
            20_000,
            "bank_transfer",
        )
        assert tx.paid_at.year == 2026 and "authorization" not in tx.raw

    @responses.activate
    def test_abandoned_is_failed_and_http_errors_raise(self):
        responses.get("https://ps.test/transaction/verify/A", json={"data": {"status": "abandoned"}})
        assert PaystackGateway().verify("A").status == "failed"
        responses.get("https://ps.test/transaction/verify/B", status=500, json={"message": "down"})
        with pytest.raises(GatewayError):
            PaystackGateway().verify("B")

    def test_signature(self):
        raw = b'{"event":"charge.success"}'
        good = hmac.new(b"sk_test_x", raw, hashlib.sha512).hexdigest()
        assert PaystackGateway().verify_signature(raw, {"x-paystack-signature": good})
        assert not PaystackGateway().verify_signature(raw, {"x-paystack-signature": "nope"})

    def test_parse_webhook(self):
        ev = PaystackGateway().parse_webhook({"event": "charge.success", "data": {"id": 9, "reference": "R"}})
        assert (ev.event_id, ev.reference) == ("charge.success:9", "R")
        assert PaystackGateway().parse_webhook({"event": "transfer.success", "data": {}}) is None


class TestFlutterwave:
    @pytest.fixture(autouse=True)
    def _keys(self, settings):
        settings.FLUTTERWAVE_SECRET_KEY = "FLWSECK_TEST-x"
        settings.FLUTTERWAVE_WEBHOOK_HASH = "hash123"
        settings.FLUTTERWAVE_BASE_URL = "https://fw.test"

    @responses.activate
    def test_initialize_uses_major_units(self):
        responses.post(
            "https://fw.test/payments", json={"status": "success", "data": {"link": "https://fw/c"}}
        )
        checkout = FlutterwaveGateway().initialize(REQ)
        sent = json.loads(responses.calls[0].request.body)
        assert sent["amount"] == "100000.00" and sent["tx_ref"] == "HSKABC"
        assert sent["subaccounts"][0] == {
            "id": "ACCT_1",
            "transaction_charge_type": "flat_subaccount",
            "transaction_charge": "99500.00",
        }
        assert checkout.url == "https://fw/c"

    @responses.activate
    def test_verify_converts_to_kobo(self):
        responses.get(
            "https://fw.test/transactions/verify_by_reference",
            json={
                "data": {
                    "status": "successful",
                    "tx_ref": "HSKABC",
                    "amount": 100000,
                    "currency": "NGN",
                    "app_fee": 1400.5,
                    "payment_type": "card",
                }
            },
        )
        tx = FlutterwaveGateway().verify("HSKABC")
        assert (tx.status, tx.amount, tx.gateway_fee) == ("success", 10_000_000, 140_050)
        assert responses.calls[0].request.params == {"tx_ref": "HSKABC"}

    def test_signature_is_the_dashboard_hash(self):
        assert FlutterwaveGateway().verify_signature(b"{}", {"verif-hash": "hash123"})
        assert not FlutterwaveGateway().verify_signature(b"{}", {"verif-hash": "other"})

    @responses.activate
    def test_missing_link_raises(self):
        responses.post("https://fw.test/payments", json={"status": "error", "data": None})
        with pytest.raises(GatewayError):
            FlutterwaveGateway().initialize(REQ)
