from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounting.models import Expense
from apps.leasing.models import Charge
from apps.orgs.services import invite, link_invites
from apps.payments import services
from apps.payments.tests.test_payments import make_lease
from apps.properties.models import Property
from conftest import make_user

pytestmark = pytest.mark.django_db


def url(name, org, *args):
    return reverse(f"v1:{name}", args=[org.pk, *args])


def test_expense_crud_and_permissions(auth_client, org, user):
    prop = Property.objects.create(organization=org, name="Palm Court", address="Lekki")
    today = timezone.localdate()
    resp = auth_client.post(
        url("expense-list", org),
        {"property": str(prop.pk), "category": "repairs", "amount": "45000.50", "spent_on": str(today)},
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    assert resp.json()["amount"] == "45000.50" and resp.json()["property_name"] == "Palm Court"
    assert Expense.objects.get().amount == 4_500_050

    future = auth_client.post(
        url("expense-list", org),
        {"amount": "1", "spent_on": str(today + timedelta(days=1))},
        format="json",
    )
    assert future.status_code == 400

    viewer = make_user(phone="+2348044444444")
    invite(org=org, phone_number=viewer.phone_number, role="viewer", by=user)
    link_invites(viewer)
    auth_client.force_authenticate(viewer)
    assert auth_client.get(url("expense-list", org)).status_code == 200
    assert auth_client.post(url("expense-list", org), {"amount": "1"}, format="json").status_code == 403

    stranger = make_user(phone="+2348055555555")
    auth_client.force_authenticate(stranger)
    assert auth_client.get(url("expense-list", org)).status_code == 404


def test_monthly_statement(auth_client, org, user):
    tenant = make_lease(org, user)
    charge = Charge.objects.filter(tenant=tenant).order_by("due_date").first()
    paid_at = timezone.now()
    services.record_manual_payment(
        org=org,
        tenant=tenant,
        amount=charge.amount + 10_000,  # NGN 100 more than owed on this charge -> next charge part-paid
        channel="bank_transfer",
        paid_at=paid_at,
        charge_ids=[charge.pk],
        by=user,
    )
    prop = Property.objects.get(organization=org)
    Expense.objects.create(
        organization=org, property=prop, category="repairs", amount=2_000_000, spent_on=timezone.localdate()
    )
    month = f"{timezone.localdate():%Y-%m}"
    data = auth_client.get(url("statement", org), {"month": month}).json()
    assert data["totals"]["collected"] == "100100.00"
    assert data["totals"]["expenses"] == "20000.00"
    assert data["totals"]["net"] == "80100.00"
    assert data["by_property"][0]["property"] == "Palm Court"
    assert data["expenses_by_category"] == {"repairs": "20000.00"}
    assert len(data["collections"]) == 2 and data["collections"][0]["receipt"] == "RCT-000001"

    csv_resp = auth_client.get(url("statement", org), {"month": month, "export": "csv"})
    assert csv_resp["Content-Type"].startswith("text/csv")
    body = csv_resp.content.decode()
    assert "Collections" in body and "Chidi Okafor" in body and "Net,80100.00" in body

    assert auth_client.get(url("statement", org), {"month": "2026-13"}).status_code == 400
