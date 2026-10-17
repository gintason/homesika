from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.estates import services
from apps.estates.models import DuesPlan, Estate, EstateMember, GatePass
from apps.leasing.models import Charge
from apps.notifications.models import PushDevice
from apps.orgs.models import Membership
from conftest import make_user

pytestmark = pytest.mark.django_db
RESIDENT_PHONE = "+2348031112222"
TOKEN = "ExponentPushToken[resident-aaaaaaaaaaaa]"


def org_url(name, org, *args):
    return reverse(f"v1:{name}", args=[org.pk, *args])


def as_(client, u):
    client.force_authenticate(u)
    return client


def staff(org, role, phone):
    u = make_user(phone=phone, first=role.title())
    Membership.objects.create(organization=org, user=u, role=role)
    return u


@pytest.fixture
def estate(org, user):
    e = services.create_estate(org=org, by=user, name="Palm Grove Estate", address="1 Palm Ave, Lekki")
    services.add_houses(e, ["A1", "A2", "B1"])
    return e


@pytest.fixture
def resident_user(db):
    return make_user(phone=RESIDENT_PHONE, first="Ngozi", last="Eze")


@pytest.fixture
def resident(estate, user, resident_user):
    m = services.join(user=resident_user, code=estate.join_code, house="a1")
    return services.approve(m, by=user)


def test_create_estate_with_houses(api_client, org, user):
    r = as_(api_client, user).post(
        org_url("estate-list", org),
        {"name": "Palm Grove", "address": "1 Palm Ave", "houses": ["A1", "A2", " A2 "]},
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["houses"] == 2 and len(r.data["join_code"]) == 6
    e = Estate.objects.get(pk=r.data["id"])
    assert e.property.kind == "compound" and e.property.organization == org
    r = api_client.post(org_url("estate-houses", org, e.pk), {"labels": ["C1"]}, format="json")
    assert r.data == {"created": 1}
    r = api_client.post(org_url("estate-regenerate-code", org, e.pk))
    assert r.data["join_code"] != e.join_code


def test_join_approve_and_dues(api_client, org, user, estate, resident_user, _sms_outbox):
    r = as_(api_client, resident_user).post(
        reverse("v1:my-estate-join"), {"code": estate.join_code.lower(), "house": "A1"}, format="json"
    )
    assert r.status_code == 201, r.data
    assert r.data["status"] == "pending" and r.data["house"] == "A1"
    # can't make passes or see announcements until approved
    r = api_client.post(
        reverse("v1:my-gate-pass-list"), {"estate": str(estate.pk), "visitor_name": "Tolu"}, format="json"
    )
    assert r.status_code == 400
    member = EstateMember.objects.get(user=resident_user)
    as_(api_client, user)
    r = api_client.get(org_url("estate-member-list", org), {"estate": str(estate.pk), "status": "pending"})
    assert [m["id"] for m in r.data["results"]] == [str(member.pk)]
    DuesPlan.objects.create(
        estate=estate, name="Security levy", amount=15_000_00, start_date=date.today().replace(day=1)
    )
    r = api_client.post(org_url("estate-member-approve", org, member.pk), {}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["status"] == "approved"
    assert any("verified resident" in t for _p, t in _sms_outbox)
    member.refresh_from_db()
    charge = Charge.objects.get(tenant=member.payer)
    assert charge.kind == "dues" and charge.amount == 15_000_00 and charge.organization == org
    # rerun is harmless
    assert services.generate_dues(estate=estate) == 0
    r = as_(api_client, resident_user).get(reverse("v1:my-estate-list"))
    assert r.data["results"][0]["dues_outstanding"] == 15_000_00


def test_join_unknown_code(api_client, resident_user):
    r = as_(api_client, resident_user).post(
        reverse("v1:my-estate-join"), {"code": "ZZZZZZ", "house": "1"}, format="json"
    )
    assert r.status_code == 404 and r.json()["error"]["code"] == "estate_code_not_found"


def test_admin_adds_member_before_signup(api_client, org, user, estate):
    unit = estate.property.units.get(label="B1")
    r = as_(api_client, user).post(
        org_url("estate-member-list", org),
        {
            "estate": str(estate.pk),
            "full_name": "Bayo Ade",
            "phone_number": "08039998888",
            "unit": str(unit.pk),
        },
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["status"] == "approved" and r.data["has_app"] is False
    u = make_user(phone="+2348039998888", first="Bayo")
    assert services.link_user(u) == 1
    r = api_client.post(
        org_url("estate-member-suspend", org, r.data["id"]), {"reason": "Moved out"}, format="json"
    )
    assert r.data["status"] == "suspended"


def test_dues_periods_and_reminders(org, user, estate, resident, _sms_outbox):
    start = date(2026, 1, 1)
    EstateMember.objects.filter(pk=resident.pk).update(
        approved_at=timezone.make_aware(timezone.datetime(2026, 2, 10))
    )
    resident.refresh_from_db()
    DuesPlan.objects.create(estate=estate, name="Service charge", amount=5_000_00, start_date=start)
    made = services.generate_dues(estate=estate, today=date(2026, 4, 26))
    # Feb (joined), Mar, Apr, and May (within 7 days)
    assert made == 4
    starts = sorted(Charge.objects.filter(tenant=resident.payer).values_list("period_start", flat=True))
    assert starts == [date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1), date(2026, 5, 1)]
    _sms_outbox.clear()
    out = services.send_dues_reminders(today=date(2026, 4, 28))  # 3 days before May
    assert out == {"sent": 1}
    assert "is due on 01 May" in _sms_outbox[-1][1]
    assert services.send_dues_reminders(today=date(2026, 4, 28)) == {"sent": 0}


def test_announcement_push_then_sms_fallback(
    api_client, org, user, estate, resident, _sms_outbox, _push_outbox
):
    other = make_user(phone="+2348031113333", first="Femi")
    m = services.join(user=other, code=estate.join_code, house="A2")
    services.approve(m, by=user)
    PushDevice.objects.create(user=resident.user, token=TOKEN, platform="android")
    _sms_outbox.clear()
    r = as_(api_client, user).post(
        org_url("announcement-list", org),
        {"estate": str(estate.pk), "title": "Water off", "body": "No water on Saturday 9am-1pm."},
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["push_sent"] == 1 and r.data["sms_sent"] == 1
    assert [p.token for p in _push_outbox] == [TOKEN]
    assert [ph for ph, _t in _sms_outbox] == ["+2348031113333"]
    r = as_(api_client, resident.user).get(reverse("v1:my-estate-announcements"), {"estate": str(estate.pk)})
    assert r.data[0]["title"] == "Water off"


def test_gate_pass_flow(api_client, org, user, estate, resident, _sms_outbox, _push_outbox):
    PushDevice.objects.create(user=resident.user, token=TOKEN, platform="ios")
    r = as_(api_client, resident.user).post(
        reverse("v1:my-gate-pass-list"),
        {"estate": str(estate.pk), "visitor_name": "Tolu", "visitor_phone": "08035551234", "hours": 4},
        format="json",
        HTTP_IDEMPOTENCY_KEY="gate-pass-key-0000001",
    )
    assert r.status_code == 201, r.data
    code = r.data["code"]
    assert len(code) == 6 and f"gate code is {code}" in _sms_outbox[-1][1]
    guard = staff(org, "security", "+2348030000009")
    as_(api_client, guard)
    r = api_client.post(
        org_url("gate-verify", org),
        {"estate": str(estate.pk), "code": f"{code[:3]} {code[3:]}"},
        format="json",
    )
    assert r.status_code == 200, r.data
    assert r.data["house"] == "A1" and r.data["host_name"] == "Ngozi Eze" and "visitor_phone" not in r.data
    r = api_client.post(org_url("gate-check-in", org, r.data["id"]), {}, format="json")
    assert r.data["status"] == "used" and r.data["uses"] == 1
    assert "Tolu has arrived" in _push_outbox[-1].body
    r = api_client.post(org_url("gate-verify", org), {"estate": str(estate.pk), "code": code}, format="json")
    assert r.status_code == 404
    # security can't manage residents
    assert api_client.get(org_url("estate-member-list", org)).status_code == 403


def test_expired_and_cancelled_pass(api_client, org, user, estate, resident):
    gp = services.create_pass(member=resident, visitor_name="Kola", hours=1)
    GatePass.objects.filter(pk=gp.pk).update(
        valid_from=timezone.now() - timedelta(hours=3), valid_to=timezone.now() - timedelta(hours=2)
    )
    with pytest.raises(services.PassInvalid):
        services.find_pass(estate, gp.code)
    gp2 = services.create_pass(member=resident, visitor_name="Kemi")
    r = as_(api_client, resident.user).post(reverse("v1:my-gate-pass-cancel", args=[gp2.pk]))
    assert r.data["status"] == "cancelled"
    r = api_client.get(reverse("v1:my-gate-pass-list"))
    assert r.data["results"] == []


def test_other_org_cannot_see_estate(api_client, estate):
    from apps.orgs.services import create_organization

    outsider = make_user(phone="+2348030000077", first="Out")
    other = create_organization(user=outsider, name="Other", kind="landlord")
    r = as_(api_client, outsider).get(org_url("estate-detail", other, estate.pk))
    assert r.status_code == 404
