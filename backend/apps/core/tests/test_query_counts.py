"""Lists must not run one query per row (N+1): the query count is the same for 1 row and for 4."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.estates import services as estates
from apps.estates.models import Estate
from apps.orgs.models import Membership
from apps.security import services as security
from conftest import make_user

pytestmark = pytest.mark.django_db


def count(client, url, **params):
    with CaptureQueriesContext(connection) as ctx:
        r = client.get(url, params)
    assert r.status_code == 200, r.data
    return len(ctx)


def org_url(name, org):
    return reverse(f"v1:{name}", args=[org.pk])


def add_estate(org, user, n):
    e = estates.create_estate(org=org, by=user, name=f"Estate {n}", address="1 Road")
    estates.add_houses(e, ["A1", "A2"])
    m = estates.approve(
        estates.join(user=make_user(phone=f"+234803200{n:04d}", first="R"), code=e.join_code, house="A1"),
        by=user,
    )
    estates.create_pass(member=m, visitor_name="Tolu")
    alert, _ = security.raise_alert(user=m.user, estate=e, client_id=f"alert-{n}")
    security.close(alert, by=user, outcome="false_alarm", note="test")
    security.raise_alert(user=m.user, estate=e, client_id=f"alert-b-{n}")
    return e


@pytest.mark.parametrize(
    "name,params",
    [
        ("estate-list", {}),
        ("estate-member-list", {"status": "approved"}),
        ("alert-list", {"status": "all"}),
        ("gate-list", {}),
        ("announcement-list", {}),
        ("dues-plan-list", {}),
    ],
)
def test_org_lists_do_not_grow_with_rows(api_client, org, user, name, params):
    Membership.objects.filter(organization=org, user=user).update(role="owner")
    api_client.force_authenticate(user)
    add_estate(org, user, 1)
    one = count(api_client, org_url(name, org), **params)
    for n in range(2, 5):
        add_estate(org, user, n)
    assert Estate.objects.count() == 4
    assert count(api_client, org_url(name, org), **params) == one


def test_charges_list_does_not_grow_with_rows(api_client, org, user):
    from apps.payments.tests.test_payments import make_lease

    api_client.force_authenticate(user)
    make_lease(org, user, phone="+2348031110001")
    url = reverse("v1:charge-list", args=[org.pk])
    one = count(api_client, url)
    for i in range(2, 5):
        make_lease(org, user, phone=f"+234803111000{i}", label=f"Flat {i}")
    assert count(api_client, url) == one
