from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounting import analytics
from apps.assistant.evals import scenarios
from apps.payments.models import Payment

pytestmark = pytest.mark.django_db


@pytest.fixture
def world():
    return scenarios.build_all()


def test_org_analytics_match_the_records(api_client, world):
    org = world.orgs["obi"]
    api_client.force_authenticate(world.users["landlord"])
    with scenarios.frozen_now():
        r = api_client.get(reverse("v1:analytics", args=[org.pk]), {"months": 3})
        payments = Payment.objects.filter(organization=org, status="succeeded")
        october = sum(
            p.amount for p in payments if timezone.localtime(p.paid_at).strftime("%Y-%m") == "2026-10"
        )
    assert r.status_code == 200, r.data
    assert [m["month"] for m in r.data["months"]] == ["2026-08-01", "2026-09-01", "2026-10-01"]
    now = r.data["now"]
    assert Decimal(now["arrears"]) == Decimal("665000.00")  # docs/ASSISTANT.md §6
    assert now["tenants_in_arrears"] == 3  # Chidi, Tunde, Musa
    assert now["units"] >= now["occupied"] > 0
    oct_ = r.data["months"][-1]
    assert Decimal(oct_["collected"]) == Decimal(october) / 100
    for m in r.data["months"]:
        assert m["collection_rate"] is None or 0 <= m["collection_rate"] <= 100
        assert m["paid_on_time"] <= m["charges"]


def test_on_time_and_collection_rate(org, user):
    from datetime import date, timedelta

    from apps.leasing.models import Charge
    from apps.payments import services as payments
    from apps.payments.tests.test_payments import make_lease

    tenant = make_lease(org, user, phone="+2348031110001")
    today = timezone.localdate()
    charges = list(Charge.objects.filter(tenant=tenant, due_date__lte=today).order_by("due_date"))
    first = charges[0]
    payments.record_manual_payment(
        org=org,
        by=user,
        tenant=tenant,
        amount=first.amount,
        channel="cash",
        charge_ids=[first.pk],
        paid_at=timezone.make_aware(
            timezone.datetime.combine(first.due_date - timedelta(days=1), timezone.datetime.min.time())
        ),
    )
    rows = {r["month"]: r for r in analytics.monthly(org, months=4, today=today)}
    month = rows[first.due_date.replace(day=1).isoformat()]
    assert month["paid_on_time"] >= 1 and month["collection_rate"] > 0
    assert isinstance(date.fromisoformat(month["month"]), date)


def test_platform_metrics_are_for_staff_only(api_client, world):
    url = reverse("v1:platform-metrics")
    api_client.force_authenticate(world.users["landlord"])
    assert api_client.get(url).status_code == 403
    staff = world.users["chidi"]
    staff.is_staff = True
    staff.save()
    api_client.force_authenticate(staff)
    with scenarios.frozen_now():
        r = api_client.get(url, {"months": 2})
    assert r.status_code == 200
    assert r.data["organizations"]["landlord"] >= 2 and r.data["users"] > 5
    assert len(r.data["months"]) == 2 and "rent_and_dues_online" in r.data["months"][0]
