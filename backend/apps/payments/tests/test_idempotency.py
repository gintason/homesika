import pytest
from django.urls import reverse

from apps.payments.models import Payment
from apps.payments.tests.test_payments import make_lease

pytestmark = pytest.mark.django_db
KEY = "manual-pay-0001-abcdef"


def test_manual_payment_retry_is_not_recorded_twice(auth_client, org, user):
    tenant = make_lease(org, user)
    url = reverse("v1:payment-manual", args=[org.pk])
    body = {"tenant": str(tenant.pk), "amount": "5000", "channel": "cash"}
    first = auth_client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=KEY)
    retry = auth_client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=KEY)
    assert first.status_code == retry.status_code == 201
    assert retry["Idempotent-Replayed"] == "true" and retry.json() == first.json()
    assert Payment.objects.count() == 1

    other = auth_client.post(url, {**body, "amount": "6000"}, format="json", HTTP_IDEMPOTENCY_KEY=KEY)
    assert other.status_code == 422
    assert auth_client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY="short").status_code == 400
    # Without a key, each request is new.
    auth_client.post(url, body, format="json")
    assert Payment.objects.count() == 2


def test_keys_are_per_user(auth_client, api_client, org, user):
    from conftest import make_user

    tenant = make_lease(org, user)
    url = reverse("v1:payment-manual", args=[org.pk])
    body = {"tenant": str(tenant.pk), "amount": "5000", "channel": "cash"}
    auth_client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=KEY)
    stranger = make_user(phone="+2348055555555")
    api_client.force_authenticate(stranger)
    assert api_client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=KEY).status_code == 404
