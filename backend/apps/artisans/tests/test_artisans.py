import io
import re
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.artisans import services
from apps.artisans.models import ArtisanProfile, VerificationCheck, Voucher
from apps.core.models import AuditLog
from conftest import make_user

pytestmark = pytest.mark.django_db

APPLY = {
    "display_name": "Musa Plumbing Works",
    "trades": ["plumbing", "tiling"],
    "service_areas": ["Lekki", "Ajah", "lekki"],
    "address": "4 Ado Road, Ajah",
    "city": "Lagos",
    "state": "Lagos",
    "years_experience": 8,
    "consent": True,
}


def jpeg_with_gps(size=(80, 60)) -> SimpleUploadedFile:
    img = Image.new("RGB", size, (90, 120, 200))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make
    exif[0x8825] = {1: "N", 2: (6.0, 27.0, 0.0)}  # GPS IFD: a location we must not keep
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return SimpleUploadedFile("id.jpg", buf.getvalue(), content_type="image/jpeg")


@pytest.fixture
def artisan_user(api_client):
    u = make_user(phone="+2348055550001", first="Musa", last="Bello")
    api_client.force_authenticate(u)
    return u


def apply(api_client, **over):
    return api_client.post(reverse("v1:artisan-apply"), {**APPLY, **over}, format="json")


def links(outbox) -> list[str]:
    return [m for _to, body in outbox for m in re.findall(r"/v/([\w-]+)", body)]


def verify_fully(profile, staff, outbox, settings) -> ArtisanProfile:
    """Pass every check the badge needs (ID by the mock, address by staff, 2 guarantors, 1 reference)."""
    settings.ID_VERIFICATION_PROVIDER = "mock"
    services.submit_id(profile, id_type="nin", id_number="12345678901")
    services.review_check(profile.checks.get(kind="address"), passed=True, by=staff)
    for i, kind in enumerate(["guarantor", "guarantor", "reference"]):
        services.add_voucher(
            profile,
            kind=kind,
            full_name=f"Person {i}",
            phone_number=f"0806000000{i}",
            relationship="uncle",
            address="1 Road",
        )
    for token in links(outbox)[-3:]:
        services.respond_voucher(token, confirm=True)
    profile.refresh_from_db()
    return profile


def test_apply_creates_profile_with_checks_and_consent(api_client, artisan_user):
    r = apply(api_client)
    assert r.status_code == 201, r.json()
    body = r.json()
    assert body["status"] == "pending" and body["is_verified"] is False
    assert body["service_areas"] == ["Lekki", "Ajah"]  # duplicates dropped
    checks = {c["kind"]: c["status"] for c in body["checks"]}
    assert checks == {"address": "pending", "id": "not_started", "phone": "passed"}  # phone: OTP at sign-up
    assert body["requirements"] == {
        "id": False,
        "phone": True,
        "address": False,
        "guarantors": 0,
        "guarantors_needed": 2,
        "references": 0,
        "references_needed": 1,
        "complete": False,
    }
    assert ArtisanProfile.objects.get().data_consent_at is not None
    assert apply(api_client).json()["error"]["code"] == "already_artisan"


def test_apply_needs_consent_and_valid_trades(api_client, artisan_user):
    assert "consent" in apply(api_client, consent=False).json()["error"]["details"]
    assert apply(api_client, trades=["astrology"]).status_code == 400
    assert apply(api_client, trades=[]).status_code == 400
    assert api_client.get(reverse("v1:artisan-me")).json()["error"]["code"] == "not_artisan"


def test_address_is_encrypted_and_change_needs_reconfirming(api_client, artisan_user, user):
    apply(api_client)
    profile = ArtisanProfile.objects.get()
    from django.db import connection

    with connection.cursor() as c:
        c.execute("SELECT address FROM artisans_artisanprofile")
        assert "Ado Road" not in c.fetchone()[0]
    services.review_check(profile.checks.get(kind="address"), passed=True, by=user)
    r = api_client.patch(reverse("v1:artisan-me"), {"address": "9 New Street, Ajah"}, format="json")
    assert r.status_code == 200
    assert {c["kind"]: c["status"] for c in r.json()["checks"]}["address"] == "pending"


def test_manual_id_review_strips_location_and_staff_decide(api_client, artisan_user, user, _sms_outbox):
    apply(api_client)
    url = reverse("v1:artisan-id")
    missing = api_client.post(url, {"id_type": "nin", "id_number": "12345678901"}, format="multipart")
    assert "document" in missing.json()["error"]["details"]
    bad_nin = api_client.post(
        url, {"id_type": "nin", "id_number": "1234", "document": jpeg_with_gps()}, format="multipart"
    )
    assert "id_number" in bad_nin.json()["error"]["details"]

    r = api_client.post(
        url, {"id_type": "nin", "id_number": "123 4567 8901", "document": jpeg_with_gps()}, format="multipart"
    )
    assert r.status_code == 200, r.json()
    check = VerificationCheck.objects.get(kind="id")
    assert check.status == "pending" and check.provider == "manual" and check.id_number_last4 == "8901"
    with check.document.open("rb") as f, Image.open(f) as stored:
        assert stored.format == "JPEG" and not stored.getexif()  # EXIF (incl. GPS) gone

    services.review_check(check, passed=False, by=user, note="The photo is blurry.")
    assert "blurry" in _sms_outbox[-1][1]
    assert AuditLog.objects.filter(action="artisan.check_failed").exists()


def test_mock_id_check(api_client, artisan_user, settings):
    settings.ID_VERIFICATION_PROVIDER = "mock"
    apply(api_client)
    url = reverse("v1:artisan-id")
    failed = api_client.post(url, {"id_type": "nin", "id_number": "12345670000"}, format="json")
    assert {c["kind"]: c for c in failed.json()["checks"]}["id"]["status"] == "failed"
    passed = api_client.post(url, {"id_type": "nin", "id_number": "12345678901"}, format="json")
    assert {c["kind"]: c for c in passed.json()["checks"]}["id"]["status"] == "passed"
    again = api_client.post(url, {"id_type": "nin", "id_number": "12345678901"}, format="json")
    assert again.status_code == 400  # already passed


def test_guarantor_link_flow(api_client, artisan_user, _sms_outbox):
    apply(api_client)
    url = reverse("v1:artisan-vouchers")
    own = api_client.post(
        url,
        {
            "kind": "guarantor",
            "full_name": "Me",
            "phone_number": "08055550001",
            "relationship": "self",
            "address": "x",
        },
        format="json",
    )
    assert "phone_number" in own.json()["error"]["details"]
    no_address = api_client.post(
        url,
        {
            "kind": "guarantor",
            "full_name": "Uncle Sule",
            "phone_number": "08061112222",
            "relationship": "uncle",
        },
        format="json",
    )
    assert "address" in no_address.json()["error"]["details"]
    r = api_client.post(
        url,
        {
            "kind": "guarantor",
            "full_name": "Uncle Sule",
            "phone_number": "08061112222",
            "relationship": "uncle",
            "address": "2 Market Rd",
        },
        format="json",
    )
    assert r.status_code == 201 and r.json()["phone_number"] == "+2348061112222"
    to, body = _sms_outbox[-1]
    assert to == "+2348061112222" and "Musa Plumbing Works" in body
    dup = api_client.post(
        url,
        {"kind": "reference", "full_name": "Sule", "phone_number": "+2348061112222", "relationship": "uncle"},
        format="json",
    )
    assert dup.status_code == 400

    token = links(_sms_outbox)[-1]
    anon = type(api_client)()
    page = anon.get(reverse("v1:vouch", args=[token]))
    assert page.status_code == 200
    assert page.json() == {
        "kind": "guarantor",
        "full_name": "Uncle Sule",
        "artisan_name": "Musa Plumbing Works",
        "trades": ["Plumbing", "Tiling and masonry"],
        "status": "pending",
    }
    assert "phone" not in str(page.json()) and "Ado" not in str(page.json())  # nothing private on the page
    done = anon.post(
        reverse("v1:vouch", args=[token]), {"confirm": True, "comment": "Good boy"}, format="json"
    )
    assert done.json()["status"] == "confirmed"
    # answering again can't flip it
    assert anon.post(reverse("v1:vouch", args=[token]), {"confirm": False}, format="json").json()[
        "status"
    ] == ("confirmed")
    assert (
        anon.get(reverse("v1:vouch", args=["not-a-real-token"])).json()["error"]["code"]
        == "voucher_link_invalid"
    )
    me = api_client.get(reverse("v1:artisan-me")).json()
    assert me["requirements"]["guarantors"] == 1


def test_declined_voucher_tells_artisan_and_links_expire(api_client, artisan_user, _sms_outbox, settings):
    apply(api_client)
    profile = ArtisanProfile.objects.get()
    services.add_voucher(
        profile, kind="reference", full_name="Mrs Ade", phone_number="08062223333", relationship="past client"
    )
    services.respond_voucher(links(_sms_outbox)[-1], confirm=False)
    assert "said no" in _sms_outbox[-1][1] and _sms_outbox[-1][0] == "+2348055550001"

    v = services.add_voucher(
        profile, kind="reference", full_name="Mr Obi", phone_number="08063334444", relationship="landlord"
    )
    token = links(_sms_outbox)[-1]
    Voucher.objects.filter(pk=v.pk).update(link_sent_at=timezone.now() - timedelta(days=15))
    anon = type(api_client)()
    assert anon.get(reverse("v1:vouch", args=[token])).status_code == 404
    v.refresh_from_db()
    assert v.status == "expired"
    # resend: a new link works, the old one doesn't; and there's a 10 minute gap and 3 sends max
    resent = api_client.post(reverse("v1:artisan-voucher-resend", args=[v.pk]))
    assert resent.status_code == 200 and resent.json()["status"] == "pending"
    assert anon.get(reverse("v1:vouch", args=[token])).status_code == 404
    assert anon.get(reverse("v1:vouch", args=[links(_sms_outbox)[-1]])).status_code == 200
    assert api_client.post(reverse("v1:artisan-voucher-resend", args=[v.pk])).status_code == 400


def test_verified_badge_needs_every_check_and_can_be_suspended(
    api_client, artisan_user, user, _sms_outbox, settings
):
    apply(api_client)
    profile = ArtisanProfile.objects.get()
    settings.ID_VERIFICATION_PROVIDER = "mock"
    services.submit_id(profile, id_type="nin", id_number="12345678901")
    services.review_check(profile.checks.get(kind="address"), passed=True, by=user)
    for i, kind in enumerate(["guarantor", "reference"]):
        services.add_voucher(
            profile,
            kind=kind,
            full_name=f"P{i}",
            phone_number=f"0806000000{i}",
            relationship="x",
            address="y",
        )
    for token in links(_sms_outbox)[-2:]:
        services.respond_voucher(token, confirm=True)
    profile.refresh_from_db()
    assert profile.status == "pending"  # one guarantor short
    services.add_voucher(
        profile, kind="guarantor", full_name="P9", phone_number="08060000009", relationship="x", address="y"
    )
    services.respond_voucher(links(_sms_outbox)[-1], confirm=True)
    profile.refresh_from_db()
    assert profile.status == "verified" and profile.verified_at
    assert "Verified artisan" in _sms_outbox[-1][1]

    services.set_status(profile, status="suspended", by=user, reason="Complaint")
    profile.refresh_from_db()
    assert profile.status == "suspended" and services.directory() == []
    services.set_status(profile, status="pending", by=user)  # reinstate: checks still pass
    profile.refresh_from_db()
    assert profile.status == "verified"


def test_directory_only_lists_verified_available_artisans(
    api_client, artisan_user, user, org, _sms_outbox, settings
):
    apply(api_client)
    profile = verify_fully(ArtisanProfile.objects.get(), user, _sms_outbox, settings)
    other = make_user(phone="+2348055550002", first="Emeka")
    services.apply(
        user=other,
        display_name="Emeka Sparks",
        trades=["electrical"],
        service_areas=["Ikeja"],
        address="x",
        consent=True,
    )  # not verified

    api_client.force_authenticate(user)
    url = reverse("v1:org-artisans", args=[org.pk])
    rows = api_client.get(url).json()
    assert [r["display_name"] for r in rows] == ["Musa Plumbing Works"]
    assert "phone_number" not in rows[0] and "address" not in rows[0]
    assert rows[0]["is_verified"] is True and rows[0]["jobs_with_us"] == 0
    assert api_client.get(url, {"trade": "plumbing", "area": "lekki"}).json()[0]["id"] == str(profile.pk)
    assert api_client.get(url, {"trade": "electrical"}).json() == []
    assert api_client.get(url, {"area": "Abuja"}).json() == []
    ArtisanProfile.objects.filter(pk=profile.pk).update(is_available=False)
    assert api_client.get(url).json() == []

    outsider = make_user(phone="+2348055550003")
    api_client.force_authenticate(outsider)
    assert api_client.get(url).status_code == 404


def test_production_refuses_mock_id_check(monkeypatch):
    import importlib
    import os
    import sys

    from django.core.exceptions import ImproperlyConfigured

    env = {
        "DJANGO_SECRET_KEY": "x" * 60,
        "DATABASE_URL": "sqlite:///:memory:",
        "ENVIRONMENT": "production",
        "PAYMENT_GATEWAYS": "paystack",
        "ASSISTANT_PROVIDER": "anthropic",
        "WHATSAPP_PROVIDER": "off",
        "BILLS_PROVIDERS": "vtung",
        "ID_VERIFICATION_PROVIDER": "mock",
        "DJANGO_ALLOWED_HOSTS": "x",
    }
    for k, v in env.items():
        monkeypatch.setitem(os.environ, k, v)
    import config.settings.base as base

    importlib.reload(base)
    monkeypatch.delitem(sys.modules, "config.settings.production", raising=False)
    with pytest.raises(ImproperlyConfigured, match="ID_VERIFICATION_PROVIDER"):
        importlib.import_module("config.settings.production")
    monkeypatch.delitem(sys.modules, "config.settings.production", raising=False)
