import io
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.listings.models import Lead, Listing, Viewing, ViewingSlot
from apps.orgs.services import invite, link_invites
from conftest import make_user

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def url(name, org, *args):
    return reverse(f"v1:{name}", args=[org.pk, *args])


def png(name="flat.png", size=(64, 48)):
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 180, 160)).save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@pytest.fixture
def listing(auth_client, org):
    resp = auth_client.post(
        url("listing-list", org),
        {
            "title": "3-bed flat, Palm Court, Lekki",
            "area": "Lekki",
            "address": "12 Admiralty Way",
            "bedrooms": 3,
            "rent_amount": "4500000",
            "rent_period": "year",
            "features": ["Fitted kitchen", "Parking"],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()


@pytest.fixture
def published(auth_client, org, listing):
    assert auth_client.post(url("listing-publish", org, listing["id"])).status_code == 200
    return Listing.objects.get(pk=listing["id"])


def slot(listing, hours=48, capacity=1):
    start = timezone.now() + timedelta(hours=hours)
    return ViewingSlot.objects.create(
        listing=listing, starts_at=start, ends_at=start + timedelta(minutes=30), capacity=capacity
    )


def test_create_publish_and_photos(auth_client, org, listing):
    assert (
        listing["status"] == "draft"
        and listing["ref"].startswith("LST-")
        and listing["rent_amount"] == "4500000.00"
    )
    up = auth_client.post(url("listing-photos", org, listing["id"]), {"image": png()}, format="multipart")
    assert up.status_code == 201, up.json()
    bad = auth_client.post(
        url("listing-photos", org, listing["id"]),
        {"image": SimpleUploadedFile("x.png", b"not an image", content_type="image/png")},
        format="multipart",
    )
    assert bad.status_code == 400
    detail = auth_client.get(url("listing-detail", org, listing["id"])).json()
    assert len(detail["photos"]) == 1
    auth_client.delete(url("listing-delete-photo", org, listing["id"], detail["photos"][0]["id"]))
    assert auth_client.get(url("listing-detail", org, listing["id"])).json()["photos"] == []


def test_public_search_and_detail_hide_address(api_client, org, published):
    s = slot(published)
    results = api_client.get(reverse("v1:public-listings"), {"area": "lekki", "max_rent": "5000000"}).json()
    assert [r["ref"] for r in results] == [published.ref]
    assert "address" not in results[0] and results[0]["landlord"] == "Obi Properties"
    assert api_client.get(reverse("v1:public-listings"), {"area": "Abuja"}).json() == []
    detail = api_client.get(reverse("v1:public-listing", args=[published.ref])).json()
    assert detail["slots"][0]["id"] == str(s.pk)
    Listing.objects.filter(pk=published.pk).update(status="draft")
    assert api_client.get(reverse("v1:public-listing", args=[published.ref])).status_code == 404


def test_enquiry_creates_one_lead_and_alerts_team(api_client, published, _sms_outbox):
    org = published.organization
    org.phone_number = "+2348031110000"
    org.save()
    body = {"name": "Kemi Johnson", "phone_number": "0803 111 9999", "message": "Is it still available?"}
    assert (
        api_client.post(
            reverse("v1:public-listing-enquire", args=[published.ref]), body, format="json"
        ).status_code
        == 201
    )
    alerts = sum("new enquiry" in text for _, text in _sms_outbox)
    assert alerts == 2  # the listing's contact and the organization's number
    api_client.post(
        reverse("v1:public-listing-enquire", args=[published.ref]),
        {**body, "message": "Can I pay quarterly?"},
        format="json",
    )
    lead = Lead.objects.get()
    assert lead.phone_number == "+2348031119999" and "quarterly" in lead.message
    assert (
        sum("new enquiry" in text for _, text in _sms_outbox) == alerts
    )  # a repeat enquiry doesn't re-alert


def test_booking_respects_capacity_and_past_slots(api_client, published, _sms_outbox):
    s = slot(published)
    book = reverse("v1:public-listing-book", args=[published.ref])
    first = api_client.post(
        book, {"name": "Ifeanyi", "phone_number": "08031112222", "slot": str(s.pk)}, format="json"
    )
    assert first.status_code == 201
    assert Lead.objects.get().stage == "viewing_booked"
    assert any("12 Admiralty Way" in text for to, text in _sms_outbox if to == "+2348031112222")
    full = api_client.post(
        book, {"name": "Kemi", "phone_number": "08031113333", "slot": str(s.pk)}, format="json"
    )
    assert full.status_code == 409 and full.json()["error"]["code"] == "slot_unavailable"
    past = ViewingSlot.objects.create(
        listing=published,
        starts_at=timezone.now() - timedelta(hours=2),
        ends_at=timezone.now() - timedelta(hours=1),
    )
    assert (
        api_client.post(
            book, {"name": "Kemi", "phone_number": "08031113333", "slot": str(past.pk)}, format="json"
        ).status_code
        == 409
    )
    Viewing.objects.update(status="cancelled")
    again = api_client.post(
        book, {"name": "Kemi", "phone_number": "08031113333", "slot": str(s.pk)}, format="json"
    )
    assert again.status_code == 201


def test_leads_and_viewings_for_staff(auth_client, org, published):
    s = slot(published)
    from apps.listings import services

    services.book_viewing(listing=published, slot_id=s.pk, phone="+2348031112222", name="Ifeanyi")
    leads = auth_client.get(url("lead-list", org), {"stage": "viewing_booked"}).json()["results"]
    assert leads[0]["name"] == "Ifeanyi" and leads[0]["viewings"][0]["status"] == "booked"
    upd = auth_client.patch(url("lead-detail", org, leads[0]["id"]), {"stage": "viewed"}, format="json")
    assert upd.json()["stage"] == "viewed"
    upcoming = auth_client.get(url("viewing-list", org), {"upcoming": "1"}).json()
    assert len(upcoming) == 1 and upcoming[0]["lead_name"] == "Ifeanyi"


def test_roles_and_org_scope(api_client, auth_client, org, user, listing):
    accountant = make_user(phone="+2348031110022")
    invite(org=org, phone_number=accountant.phone_number, role="accountant", by=user)
    link_invites(accountant)
    api_client.force_authenticate(accountant)
    assert api_client.get(url("listing-list", org)).status_code == 200
    assert api_client.post(url("listing-publish", org, listing["id"])).status_code == 403
    agent = make_user(phone="+2348031110021")
    invite(org=org, phone_number=agent.phone_number, role="agent", by=user)
    link_invites(agent)
    api_client.force_authenticate(agent)
    assert api_client.post(url("listing-publish", org, listing["id"])).status_code == 200
    api_client.force_authenticate(make_user(phone="+2348055555555"))
    assert api_client.get(url("listing-detail", org, listing["id"])).status_code == 404


def test_generator_returns_a_draft(auth_client, org, listing):
    auth_client.post(url("listing-photos", org, listing["id"]), {"image": png()}, format="multipart")
    resp = auth_client.post(
        url("listing-generate", org),
        {
            "listing": listing["id"],
            "kind": "3-bedroom flat",
            "area": "Lekki",
            "bedrooms": 3,
            "rent_amount": "4500000",
            "features": ["Fitted kitchen"],
        },
        format="json",
    )
    assert resp.status_code == 200, resp.json()
    draft = resp.json()
    assert set(draft) >= {"title", "description", "whatsapp_caption", "features", "suggested_replies"}
    assert draft["model"] == "mock"
