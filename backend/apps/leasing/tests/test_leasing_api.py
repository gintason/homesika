from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.core.models import AuditLog
from apps.leasing.models import Charge, Lease, TenantProfile
from apps.leasing.schedule import add_months
from apps.orgs.models import Membership
from apps.orgs.services import create_organization
from apps.properties.models import Unit
from conftest import make_user

pytestmark = pytest.mark.django_db


def url(name, org, *args):
    return reverse(f"v1:{name}", args=[org.pk, *args])


@pytest.fixture
def unit(auth_client, org):
    prop = auth_client.post(
        url("property-list", org), {"name": "Palm Court", "address": "12 Admiralty Way, Lekki"}, format="json"
    ).json()
    resp = auth_client.post(
        reverse("v1:property-unit-list", args=[org.pk, prop["id"]]),
        {"label": "Flat 2B", "bedrooms": 2, "default_rent_amount": "1500000"},
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()


@pytest.fixture
def tenant(auth_client, org):
    resp = auth_client.post(
        url("tenant-list", org),
        {"full_name": "Chidi Okafor", "phone_number": "08099999999", "next_of_kin": "Ngozi Okafor 0803..."},
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()


def lease_body(unit, tenant, **kw):
    return {
        "unit": unit["id"],
        "tenant": tenant["id"],
        "start_date": "2026-11-01",
        "end_date": "2027-10-31",
        "rent_amount": "1500000.00",
        "rent_frequency": "annual",
        "service_charge_amount": "120000",
        "deposit_amount": "200000",
        **kw,
    }


def test_property_and_unit_flow(auth_client, org, unit):
    props = auth_client.get(url("property-list", org)).json()
    assert props[0]["unit_count"] == 1 and props[0]["occupied_count"] == 0
    assert unit["default_rent_amount"] == "1500000.00"
    dup = auth_client.post(
        reverse("v1:property-unit-list", args=[org.pk, unit["property"]]), {"label": "flat 2b"}, format="json"
    )
    assert dup.status_code == 400


def test_tenant_is_encrypted_and_links_to_app_user(auth_client, org, tenant):
    row = TenantProfile.objects.get()
    from django.db import connection

    with connection.cursor() as c:
        c.execute("SELECT next_of_kin FROM leasing_tenantprofile")
        assert "Ngozi" not in c.fetchone()[0]  # encrypted at rest
    assert row.next_of_kin.startswith("Ngozi") and tenant["has_app"] is False
    # Tenant signs up later with the same phone: profile is linked, they see their lease data.
    from apps.accounts.models import User
    from apps.accounts.signals import user_registered

    chidi = User.objects.create_user(phone_number="+2348099999999")
    user_registered.send(sender=User, user=chidi)
    row.refresh_from_db()
    assert row.user == chidi


def test_activate_generates_schedule_and_occupies_unit(auth_client, org, unit, tenant):
    resp = auth_client.post(url("lease-list", org), lease_body(unit, tenant, activate=True), format="json")
    assert resp.status_code == 201, resp.json()
    lease = resp.json()
    assert lease["status"] == "active" and lease["balance"] == "1820000.00"
    charges = Charge.objects.filter(lease_id=lease["id"]).order_by("kind")
    assert sorted((c.kind, c.amount) for c in charges) == [
        ("deposit", 200_000_00),
        ("rent", 1_500_000_00),
        ("service_charge", 120_000_00),
    ]
    assert Unit.objects.get(pk=unit["id"]).status == "occupied"
    assert AuditLog.objects.filter(action="lease.activated").exists()

    second = auth_client.post(url("lease-list", org), lease_body(unit, tenant, activate=True), format="json")
    assert second.status_code == 400  # one active lease per unit
    locked = auth_client.patch(url("lease-detail", org, lease["id"]), {"rent_amount": "1"}, format="json")
    assert locked.status_code == 400


def test_monthly_lease_end_voids_future_unpaid(auth_client, org, unit, tenant):
    body = lease_body(
        unit,
        tenant,
        rent_frequency="monthly",
        rent_amount="150000",
        service_charge_amount="0",
        deposit_amount="0",
        start_date="2026-01-01",
        end_date="2026-12-31",
        activate=True,
    )
    lease = auth_client.post(url("lease-list", org), body, format="json").json()
    assert Charge.objects.filter(lease_id=lease["id"]).count() == 12
    ended = auth_client.post(url("lease-end", org, lease["id"]), {"ended_on": "2026-03-31"}, format="json")
    assert ended.json()["status"] == "ended"
    statuses = list(
        Charge.objects.filter(lease_id=lease["id"]).order_by("due_date").values_list("status", flat=True)
    )
    assert statuses[:3] == ["open"] * 3 and set(statuses[3:]) == {"void"}
    assert Unit.objects.get(pk=unit["id"]).status == "vacant"


def test_arrears_waive_and_one_off_charge(auth_client, org, unit, tenant):
    start = date.today() - timedelta(days=40)
    past = start.isoformat()
    full_year_end = (add_months(start, 12) - timedelta(days=1)).isoformat()
    body = lease_body(
        unit,
        tenant,
        start_date=past,
        end_date=full_year_end,
        deposit_amount="0",
        service_charge_amount="0",
        activate=True,
    )
    lease = auth_client.post(url("lease-list", org), body, format="json").json()
    arrears = auth_client.get(url("arrears", org)).json()
    assert arrears["total_owed"] == "1500000.00"
    row = arrears["results"][0]
    assert (row["tenant_name"], row["unit"], row["days_overdue"]) == ("Chidi Okafor", "Flat 2B", 40)
    dash = auth_client.get(url("dashboard", org)).json()
    assert (dash["overdue_amount"], dash["units"], dash["occupied_units"]) == ("1500000.00", 1, 1)

    extra = auth_client.post(
        url("charge-list", org),
        {
            "lease": lease["id"],
            "kind": "other",
            "description": "Broken window",
            "due_date": past,
            "amount": "25000",
        },
        format="json",
    )
    assert extra.status_code == 201, extra.json()
    rent_not_allowed = auth_client.post(
        url("charge-list", org),
        {"lease": lease["id"], "kind": "rent", "due_date": past, "amount": "1"},
        format="json",
    )
    assert rent_not_allowed.status_code == 400
    waived = auth_client.post(
        url("charge-waive", org, extra.json()["id"]), {"reason": "Fixed by landlord"}, format="json"
    )
    assert waived.json()["status"] == "waived"
    overdue = auth_client.get(url("charge-list", org) + "?overdue=1").json()["results"]
    assert [c["kind"] for c in overdue] == ["rent"]


def test_tenant_sees_only_own_charges(api_client, auth_client, org, unit, tenant):
    auth_client.post(url("lease-list", org), lease_body(unit, tenant, activate=True), format="json")
    chidi = make_user(phone="+2348099999999", first="Chidi")
    TenantProfile.objects.filter(phone_number="+2348099999999").update(user=chidi)
    stranger = make_user(phone="+2348011111111")

    api_client.force_authenticate(chidi)
    mine = api_client.get(reverse("v1:my-charges")).json()["results"]
    assert len(mine) == 3 and {c["property_name"] for c in mine} == {"Palm Court"}
    leases = api_client.get(reverse("v1:my-leases")).json()
    assert leases[0]["landlord"] == "Obi Properties" and leases[0]["rent_amount"] == "1500000.00"
    # Tenants are not org members: they can't open the landlord's org endpoints.
    assert api_client.get(url("charge-list", org)).status_code == 404

    api_client.force_authenticate(stranger)
    assert api_client.get(reverse("v1:my-charges")).json()["results"] == []
    assert api_client.get(reverse("v1:my-charge", args=[mine[0]["id"]])).status_code == 404


def test_other_orgs_units_and_tenants_are_invisible(auth_client, org, unit, tenant):
    other_owner = make_user(phone="+2348022222222")
    other = create_organization(user=other_owner, name="Rival Homes")
    auth_client.force_authenticate(other_owner)
    assert auth_client.get(url("unit-list", other)).json() == []
    # Using org A's unit/tenant ids inside org B is rejected.
    resp = auth_client.post(url("lease-list", other), lease_body(unit, tenant), format="json")
    assert resp.status_code == 400 and {"unit", "tenant"} <= resp.json()["error"]["details"].keys()
    assert auth_client.get(url("tenant-detail", org, tenant["id"])).status_code == 404


def test_viewer_role_is_read_only(api_client, org, unit):
    viewer = make_user(phone="+2348033333333")
    Membership.objects.create(organization=org, user=viewer, role="viewer")
    api_client.force_authenticate(viewer)
    assert api_client.get(url("property-list", org)).status_code == 200
    assert (
        api_client.post(url("property-list", org), {"name": "X", "address": "Y"}, format="json").status_code
        == 403
    )
    assert (
        api_client.post(
            url("tenant-list", org), {"full_name": "Z", "phone_number": "08012340000"}, format="json"
        ).status_code
        == 403
    )
    assert Lease.objects.count() == 0
