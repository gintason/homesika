import pytest
from django.urls import reverse

from apps.accounts.validators import normalise_phone
from apps.core import markets

pytestmark = pytest.mark.django_db


def test_markets_api_lagos_and_abuja_on_ghana_off(api_client):
    r = api_client.get(reverse("v1:markets"))
    assert r.status_code == 200
    assert [c["code"] for c in r.data["countries"]] == ["NG"]
    cities = {c["slug"]: c for c in r.data["cities"]}
    assert set(cities) == {"lagos", "abuja"}  # Accra is listed but its country is off
    assert "Wuse 2" in cities["abuja"]["areas"] and cities["abuja"]["discos"] == ["abuja-electric"]


def test_ghana_switch(api_client, settings, user):
    api_client.force_authenticate(user)
    body = {"name": "Accra Homes", "kind": "landlord", "country": "GH"}
    r = api_client.post(reverse("v1:org-list"), body, format="json")
    assert r.status_code == 400 and "country" in r.json()["error"]["details"]

    settings.MARKETS_COUNTRIES = "NG,GH"
    r = api_client.post(reverse("v1:org-list"), body, format="json")
    assert r.status_code == 201, r.json()
    assert (r.data["currency"], r.data["timezone"]) == ("GHS", "Africa/Accra")
    bad = api_client.post(reverse("v1:org-list"), {**body, "currency": "NGN"}, format="json")
    assert bad.status_code == 400 and "currency" in bad.json()["error"]["details"]
    assert {c["slug"] for c in api_client.get(reverse("v1:markets")).data["cities"]} == {
        "lagos",
        "abuja",
        "accra",
    }


def test_phone_numbers_are_read_for_the_country():
    assert normalise_phone("0801 234 5678") == "+2348012345678"
    assert normalise_phone("8012345678") == "+2348012345678"
    assert normalise_phone("0241234567", "GH") == "+233241234567"
    assert normalise_phone("233241234567", "GH") == "+233241234567"
    assert normalise_phone("00447700900123") == "+447700900123"
    assert markets.country("gh").currency == "GHS"


def test_ghana_org_reads_local_tenant_numbers_as_ghanaian(api_client, settings, user):
    settings.MARKETS_COUNTRIES = "NG,GH"
    api_client.force_authenticate(user)
    org = api_client.post(
        reverse("v1:org-list"), {"name": "Accra Homes", "kind": "landlord", "country": "GH"}, format="json"
    ).data
    r = api_client.post(
        reverse("v1:tenant-list", args=[org["id"]]),
        {"full_name": "Kofi Mensah", "phone_number": "024 123 4567"},
        format="json",
    )
    assert r.status_code == 201, r.json()
    assert r.data["phone_number"] == "+233241234567"
