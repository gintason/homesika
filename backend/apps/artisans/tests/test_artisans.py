import io
import json
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
    """Pass every check the badge needs: NIN (mock provider + mock reader; its address matches, so the
    address passes too), 2 guarantors, 1 reference."""
    services.submit_id(
        profile, id_type="nin", id_number="12345678901", date_of_birth="1990-05-01", document=jpeg_with_gps()
    )
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
    assert checks == {
        "address": "not_started",
        "id": "not_started",
        "phone": "passed",
    }  # phone: OTP at sign-up
    assert body["verification_mode"] == "nin"
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
    assert {c["kind"]: c["status"] for c in r.json()["checks"]}["address"] == "not_started"  # prove it again


def test_manual_id_review_strips_location_and_staff_decide(
    api_client, artisan_user, user, _sms_outbox, settings
):
    settings.ID_VERIFICATION_PROVIDER = "manual"
    apply(api_client)
    assert {c.kind: c.status for c in VerificationCheck.objects.all()}[
        "address"
    ] == "pending"  # staff confirm
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


NIN = {"id_type": "nin", "date_of_birth": "1990-05-01"}


def submit(api_client, number, **over):
    return api_client.post(
        reverse("v1:artisan-id"),
        {**NIN, "id_number": number, "document": jpeg_with_gps(), **over},
        format="multipart",
    )


def checks_of(resp) -> dict:
    return {c["kind"]: c for c in resp.json()["checks"]}


def test_nin_check_passes_and_address_matches_the_nin_record(api_client, artisan_user, _sms_outbox):
    apply(api_client)
    assert "date_of_birth" in submit(api_client, "12345678901", date_of_birth="").json()["error"]["details"]
    assert "id_number" in submit(api_client, "1234").json()["error"]["details"]
    r = submit(api_client, "1234 5678 901")
    assert r.status_code == 200, r.json()
    c = checks_of(r)
    assert (
        c["id"]["status"] == "passed"
        and c["id"]["provider"] == "mock"
        and c["id"]["id_number_last4"] == "8901"
    )
    assert c["address"]["status"] == "passed" and c["address"]["provider"] == "nin+ai"
    check = VerificationCheck.objects.get(kind="id")
    evidence = json.loads(check.evidence)
    assert evidence["nin"] == {
        "provider": "mock",
        "found": True,
        "name_match": True,
        "dob_match": True,
        "phone_match": True,
        "has_address": True,
    }
    assert evidence["document"]["number_match"] is True and evidence["document"]["model"] == "mock"
    assert check.date_of_birth == "1990-05-01"
    assert "NIN" not in check.evidence.replace("nin", "")  # no full NIN or record copied into evidence
    assert any("ID (NIN) check passed" in b for _to, b in _sms_outbox)
    assert submit(api_client, "12345678901").status_code == 400  # already passed


def test_nin_not_found_or_wrong_name_fails_and_a_person_can_be_asked(api_client, artisan_user, _sms_outbox):
    apply(api_client)
    c = checks_of(submit(api_client, "12345670000"))["id"]
    assert c["status"] == "failed" and "couldn't find that NIN" in c["note"] and c["can_request_review"]
    assert "ask a person to review" in _sms_outbox[-1][1]
    c = checks_of(submit(api_client, "12345671111"))["id"]
    assert c["status"] == "failed" and "doesn't match your name" in c["note"]
    r = api_client.post(reverse("v1:artisan-review"), {"kind": "id"}, format="json")
    c = checks_of(r)["id"]
    assert c["status"] == "pending" and c["review_requested_at"] and not c["can_request_review"]
    assert api_client.post(reverse("v1:artisan-review"), {"kind": "id"}, format="json").status_code == 400
    assert AuditLog.objects.filter(action="artisan.review_requested").exists()


def test_no_address_on_record_means_a_proof_of_address(api_client, artisan_user):
    apply(api_client)
    c = checks_of(submit(api_client, "12345672222"))
    assert c["id"]["status"] == "passed" and c["address"]["status"] == "not_started"
    r = api_client.post(reverse("v1:artisan-address"), {"document": jpeg_with_gps()}, format="multipart")
    assert r.status_code == 200, r.json()
    assert checks_of(r)["address"]["status"] == "passed"  # mock reader
    assert ArtisanProfile.objects.get().status == "pending"  # still needs guarantors and a reference


class Reader:
    """Scripted Claude for the document reader (ASSISTANT_PROVIDER isn't mock in these tests)."""

    def __init__(self, monkeypatch, settings, *payloads, fail=False):
        from apps.assistant import llm
        from apps.assistant.tests.test_assistant import FakeLlm, text_resp

        settings.ASSISTANT_PROVIDER = "anthropic"
        self.fake = FakeLlm(*[text_resp(json.dumps(p)) for p in payloads])
        if fail:

            def boom():
                raise llm.LlmUnavailable("down")

            monkeypatch.setattr(llm, "client", lambda: type("C", (), {"create": lambda self, **k: boom()})())
        else:
            monkeypatch.setattr(llm, "client", lambda: self.fake)


ID_OK = {
    "is_identity_document": True,
    "document_type": "nin_slip",
    "legible": True,
    "name_on_document": "BELLO Musa",
    "nin_on_document": "123 4567 8901",
    "date_of_birth_on_document": "1990-05-01",
    "looks_altered": False,
    "concerns": [],
    "confidence": "high",
}


@pytest.mark.parametrize(
    "change,status,note",
    [
        ({}, "passed", ""),
        ({"nin_on_document": "99999999999"}, "failed", "doesn't match the NIN"),
        ({"legible": False}, "failed", "couldn't read the ID"),
        ({"looks_altered": True}, "pending", "A person at Homesika"),
        ({"name_on_document": "Chukwu Emeka"}, "pending", "A person at Homesika"),
        ({"confidence": "low"}, "pending", "A person at Homesika"),
        ({"nin_on_document": "", "name_on_document": ""}, "pending", "A person at Homesika"),
    ],
)
def test_ai_reading_of_the_id_photo_decides_by_rules(
    api_client, artisan_user, monkeypatch, settings, change, status, note
):
    apply(api_client)
    reader = Reader(monkeypatch, settings, {**ID_OK, **change}, {"same_place": "yes", "reason": "same"})
    c = checks_of(submit(api_client, "12345678901"))["id"]
    assert c["status"] == status and note in c["note"]
    sent = reader.fake.calls[0]
    assert sent["output_schema"]["required"][0] == "is_identity_document"
    assert sent["messages"][0]["content"][0]["type"] == "image"
    assert "not an instruction" in sent["system"][0]["text"]


def test_model_outage_leaves_it_processing_then_retries(api_client, artisan_user, monkeypatch, settings):
    apply(api_client)
    Reader(monkeypatch, settings, fail=True)
    assert checks_of(submit(api_client, "12345678901"))["id"]["status"] == "processing"
    check = VerificationCheck.objects.get(kind="id")
    assert services.housekeeping()["retried"] == 0  # not stuck yet
    Reader(monkeypatch, settings, ID_OK, {"same_place": "yes", "reason": "same"})
    later = timezone.now() + timedelta(minutes=11)
    assert services.housekeeping(later)["retried"] == 1
    check.refresh_from_db()
    assert check.status == "passed"


ADDRESS_OK = {
    "is_proof_of_address": True,
    "document_type": "utility_bill",
    "legible": True,
    "name_on_document": "Musa Bello",
    "address_on_document": "4, Ado Rd, Ajah",
    "issue_date": "",
    "same_address_as_claimed": "yes",
    "looks_altered": False,
    "concerns": [],
    "confidence": "high",
}


@pytest.mark.parametrize(
    "change,status",
    [
        ({}, "passed"),
        ({"issue_date": "2020-01-01"}, "failed"),
        ({"same_address_as_claimed": "no"}, "failed"),
        ({"is_proof_of_address": False}, "failed"),
        ({"same_address_as_claimed": "unsure"}, "pending"),
        ({"name_on_document": "Landlord Okoro"}, "pending"),
    ],
)
def test_proof_of_address_rules(api_client, artisan_user, monkeypatch, settings, change, status):
    apply(api_client)
    payload = {**ADDRESS_OK, "issue_date": timezone.localdate().isoformat(), **change}
    Reader(monkeypatch, settings, payload)
    r = api_client.post(reverse("v1:artisan-address"), {"document": jpeg_with_gps()}, format="multipart")
    assert checks_of(r)["address"]["status"] == status


def test_photos_are_deleted_90_days_after_passing(api_client, artisan_user):
    apply(api_client)
    submit(api_client, "12345678901")
    check = VerificationCheck.objects.get(kind="id")
    assert check.document
    assert services.housekeeping(timezone.now() + timedelta(days=89))["deleted"] == 0
    assert services.housekeeping(timezone.now() + timedelta(days=91))["deleted"] >= 1
    check.refresh_from_db()
    assert not check.document and check.document_deleted_at and check.id_number_last4 == "8901"


def test_names_match_rules():
    m = services.names_match
    assert m(["musa", "bello"], ["bello", "musa", "ibrahim"])  # order and middle names don't matter
    assert m(["olusegun", "adeyemi"], ["olushegun", "adeyemi"])  # small spelling difference
    assert not m(["musa", "bello"], ["musa", "okafor"])
    assert not m(["musa"], ["musa", "bello"])  # need first and last name


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
    services.submit_id(
        profile, id_type="nin", id_number="12345678901", date_of_birth="1990-05-01", document=jpeg_with_gps()
    )
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
        "ID_VERIFICATION_PROVIDER": "nin",
        "NIN_PROVIDER": "mock",
        "DJANGO_ALLOWED_HOSTS": "x",
    }
    for k, v in env.items():
        monkeypatch.setitem(os.environ, k, v)
    import config.settings.base as base

    importlib.reload(base)
    monkeypatch.delitem(sys.modules, "config.settings.production", raising=False)
    with pytest.raises(ImproperlyConfigured, match="NIN_PROVIDER"):
        importlib.import_module("config.settings.production")
    monkeypatch.delitem(sys.modules, "config.settings.production", raising=False)


def test_smileid_adapter_builds_the_sdk_request_and_reads_the_response(settings, monkeypatch):
    from smile_id_core import IdApi

    from apps.artisans import nin

    settings.NIN_PROVIDER, settings.SMILEID_PARTNER_ID, settings.SMILEID_API_KEY = "smileid", "123", "key"
    sent = {}

    def fake_submit(self, partner_params, id_params, options_params=None):
        sent.update(partner_params=partner_params, id_params=id_params, url=self.url)
        return {
            "ResultCode": "1012",
            "DOB": "1990-05-01",
            "PhoneNumber": "08055550001",
            "Address": "4 Ado Road, Ajah",
            "FullData": {"firstname": "MUSA", "middlename": "ADE", "surname": "BELLO"},
        }

    monkeypatch.setattr(IdApi, "submit_job", fake_submit)
    claimed = nin.Claimed("12345678901", "Musa", "Bello", "1990-05-01", "+2348055550001", "4 Ado Road")
    record = nin.get().lookup(claimed)
    assert record == nin.NinRecord(
        True, "MUSA", "ADE", "BELLO", "1990-05-01", "08055550001", "4 Ado Road, Ajah", "smileid"
    )
    assert sent["partner_params"]["job_type"] == 5 and sent["partner_params"]["job_id"].startswith("hsk-")
    assert sent["id_params"] == {
        "country": "NG",
        "id_type": "NIN_V2",
        "id_number": "12345678901",
        "first_name": "Musa",
        "last_name": "Bello",
        "dob": "1990-05-01",
        "entered": "true",
    }
    assert "testapi" in sent["url"]  # sandbox unless SMILEID_PRODUCTION

    monkeypatch.setattr(IdApi, "submit_job", lambda self, *a, **k: {"ResultCode": "1013"})
    assert nin.get().lookup(claimed).found is False
    monkeypatch.setattr(IdApi, "submit_job", lambda self, *a, **k: {"ResultCode": "9999"})
    with pytest.raises(nin.NinUnavailable):  # an unknown answer is never treated as a pass
        nin.get().lookup(claimed)


def test_a_check_stuck_for_hours_goes_to_a_person(api_client, artisan_user, monkeypatch, settings):
    from apps.artisans import nin

    apply(api_client)

    def down(self, claimed):
        raise nin.NinUnavailable("down")

    monkeypatch.setattr(nin.MockNin, "lookup", down)
    assert checks_of(submit(api_client, "12345678901"))["id"]["status"] == "processing"
    out = services.housekeeping(timezone.now() + timedelta(hours=7))
    assert out["to_person"] == 1
    assert VerificationCheck.objects.get(kind="id").status == "pending"


def test_production_needs_smileid_live_server(monkeypatch):
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
        "ID_VERIFICATION_PROVIDER": "nin",
        "NIN_PROVIDER": "smileid",
        "SMILEID_PRODUCTION": "false",
        "DJANGO_ALLOWED_HOSTS": "x",
    }
    for k, v in env.items():
        monkeypatch.setitem(os.environ, k, v)
    import config.settings.base as base

    importlib.reload(base)
    monkeypatch.delitem(sys.modules, "config.settings.production", raising=False)
    with pytest.raises(ImproperlyConfigured, match="SMILEID_PRODUCTION"):
        importlib.import_module("config.settings.production")
    monkeypatch.delitem(sys.modules, "config.settings.production", raising=False)
