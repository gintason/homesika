"""The scenarios must match docs/ASSISTANT.md §6 exactly (the eval items rely on those figures), and the
runner + scorer must work end to end (with the mock model)."""

import json
from types import SimpleNamespace

import pytest

from apps.assistant import tools
from apps.assistant.evals import runner, scenarios
from apps.assistant.principal import for_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def world():
    return scenarios.build_all()


def ctx():
    return SimpleNamespace(
        language="en",
        org_ids=[],
        channel_source="whatsapp",
        remember=lambda **k: None,
        propose=lambda tool, args, summary: {"status": "needs_confirmation", "summary": summary},
    )


def test_tenant_overdue_matches_spec(world):
    with scenarios.frozen_now():
        s = tools.get_my_rent_summary(for_user(world.users["chidi"]), ctx())
    obi = s["landlords"][0]
    assert s["today"] == "2026-10-15" and obi["landlord"] == "Obi Properties"
    assert obi["owed_now"] == "440000.00" and obi["overdue_since"] == "2026-09-01"
    assert (
        obi["next_due_date"] == "2026-11-01"
        and obi["next_due_amount"] == "270000.00"
        and obi["can_pay_online"]
    )
    with scenarios.frozen_now():
        pays = tools.list_my_payments(for_user(world.users["chidi"]), ctx())["payments"]
    assert [p["receipt_number"] for p in pays] == ["RCT-000004", "RCT-000003", "RCT-000002", "RCT-000001"]
    assert pays[0]["amount"] == "100000.00" and pays[0]["date"] == "2026-10-05"


def test_paid_up_and_two_landlords(world):
    with scenarios.frozen_now():
        amina = tools.get_my_rent_summary(for_user(world.users["amina"]), ctx())["landlords"][0]
        tunde = {
            x["landlord"]: x
            for x in tools.get_my_rent_summary(for_user(world.users["tunde"]), ctx())["landlords"]
        }
    assert amina["owed_now"] == "0.00" and amina["next_due_date"] is None
    assert tunde["Obi Properties"]["owed_now"] == "150000.00"
    assert tunde["Sade Homes"]["owed_now"] == "0.00" and tunde["Sade Homes"]["next_due_date"] == "2026-11-01"
    assert tunde["Sade Homes"]["next_due_amount"] == "300000.00" and not tunde["Sade Homes"]["can_pay_online"]


def test_landlord_and_staff_views_match_spec(world):
    org = str(world.orgs["obi"].pk)
    with scenarios.frozen_now():
        arrears = tools.list_arrears(for_user(world.users["landlord"]), ctx(), organization_id=org)
        summary = tools.get_portfolio_summary(for_user(world.users["landlord"]), ctx(), organization_id=org)
        recent = tools.list_recent_payments(
            for_user(world.users["landlord"]), ctx(), organization_id=org, days=30
        )
        leads = tools.list_leads(
            for_user(world.users["staff_manager"]), ctx(), organization_id=org, stage=None
        )
    owed = {t["tenant"]: t["owed"] for t in arrears["tenants"]}
    assert arrears["total_overdue"] == "665000.00"
    assert owed == {"Chidi Okafor": "440000.00", "Tunde Adeyemi": "150000.00", "Musa Ibrahim": "75000.00"}
    assert (
        summary["units"] == 6
        and summary["occupied_units"] == 5
        and summary["vacant_units"] == ["Flat 4D, Palm Court"]
    )
    assert {p["receipt_number"] for p in recent["payments"]} == {"RCT-000004", "RCT-000006", "RCT-000007"}
    assert {(x["name"], x["stage"]) for x in leads["leads"]} == {
        ("Kemi Johnson", "new"),
        ("Ifeanyi Nwosu", "viewing_booked"),
    }
    with pytest.raises(tools.ToolError):
        tools.list_arrears(for_user(world.users["staff_agent"]), ctx(), organization_id=org)
    with pytest.raises(tools.ToolError):
        tools.send_payment_link(
            for_user(world.users["staff_viewer"]),
            ctx(),
            organization_id=org,
            tenant_id=str(world.tenants["chidi"].pk),
            charge_ids=[],
        )


def test_prospect_listings_match_spec(world):
    from apps.assistant.principal import Principal

    p = Principal(phone="+2348031119999")
    with scenarios.frozen_now():
        lekki = tools.search_listings(p, ctx(), area="Lekki", max_rent=None, bedrooms=None)["listings"]
        abuja = tools.search_listings(p, ctx(), area="Abuja", max_rent=None, bedrooms=None)["listings"]
        palm = tools.get_listing(p, ctx(), listing_ref="LST-PALM4D")
        ikeja = tools.get_listing(p, ctx(), listing_ref="lst-ikjsc")
    assert [x["listing_ref"] for x in lekki] == ["LST-PALM4D"] and abuja == []
    assert [s["starts"] for s in palm["open_viewing_slots"]] == ["2026-10-18 14:00", "2026-10-19 10:00"]
    assert ikeja["open_viewing_slots"] == [] and palm["price"] == "4500000.00"


def test_eval_files_are_well_formed():
    names = {t.name for t in tools.TOOLS}
    for role in runner.ROLES:
        items = runner.load(role)
        assert len(items) >= 100, role
        assert len({i["id"] for i in items}) == len(items)
        for i in items:
            assert (
                i["role"] == role
                and i["scenario"] in scenarios.PRINCIPAL_FOR_SCENARIO
                and i["language"] in ("en", "pcm")
            )
            e = i["expect"]
            assert set(e["tools_any"]) | set(e["must_not_call"]) <= names, i["id"]
            assert e["behaviour"] in {"answer", "confirm", "escalate", "emergency", "refuse", "clarify"}


def test_scorer():
    item = {
        "expect": {
            "behaviour": "answer",
            "tools_any": ["get_my_rent_summary"],
            "must_include_any": ["440,000"],
            "must_not_include": ["Tunde"],
            "must_not_call": ["list_arrears"],
            "escalation": None,
            "confirmation": False,
        }
    }
    ok, _ = runner.score(
        item,
        reply="You owe ₦440,000.",
        tools_called=["get_my_rent_summary"],
        pending=None,
        executed=False,
        escalation_reason=None,
    )
    assert ok
    ok, reasons = runner.score(
        item,
        reply="You owe 4,400,000 like Tunde",
        tools_called=[],
        pending=None,
        executed=False,
        escalation_reason=None,
    )
    assert not ok and len(reasons) == 3
    assert runner.includes("₦440,000.00 is due", "440000") and not runner.includes("1440,000", "440,000")


def test_runner_end_to_end_with_mock_model():
    report = runner.run(("tenant",), ids={"tenant-001", "tenant-002"})
    assert report["summary"]["total"] == 2
    first = report["results"][0]
    assert "get_my_rent_summary" in first["tools"] and "440000.00" in first["reply"]
    json.dumps(report)  # serialisable


def test_bills_scenario_matches_spec(world):
    chidi = for_user(world.users["chidi"])
    with scenarios.frozen_now():
        lease = tools.get_my_lease(chidi, ctx())["leases"][0]
        orders = tools.my_bill_orders(chidi, ctx())["orders"]
        mtn = tools.list_bill_options(chidi, ctx(), category="data", biller_code="mtn")["billers"][0]
    assert (lease["meter_number"], lease["disco"]) == ("45123456789", "ikeja-electric")
    assert orders[0]["token"] == "1234-5678-9012-3456-7890" and orders[0]["receipt_number"] == "BIL-000001"
    assert {p["name"]: p["price"] for p in mtn["plans"]} == {
        "1GB, 30 days (sample)": "1000.00",
        "5GB, 30 days (sample)": "4000.00",
    }


def test_repairs_scenario_matches_spec(world):
    chidi = for_user(world.users["chidi"])
    emeka = for_user(world.users["landlord"])
    org_id = str(world.orgs["obi"].pk)
    with scenarios.frozen_now():
        mine = tools.my_repairs(chidi, ctx())["repairs"]
        staff = tools.list_repairs(emeka, ctx(), organization_id=org_id, status=None)
    assert mine == [
        {
            "reference": "R0000A01",
            "title": "Kitchen tap leaking",
            "unit": "Flat 2B",
            "status": "assigned",
            "priority": "urgent",
            "reported": mine[0]["reported"],
            "artisan": "Kunle Plumbing Works",
            "artisan_verified": True,
            "visit": "Fri 16 Oct 02:00 PM",
            "reason": None,
        }
    ]
    assert {r["reference"] for r in staff["repairs"]} == {"R0000A01", "R0000A02"}
    assert staff["awaiting_approval"] == 1
