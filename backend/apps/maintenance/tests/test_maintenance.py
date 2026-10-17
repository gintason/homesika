from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.artisans import services as artisans
from apps.artisans.models import ArtisanProfile
from apps.artisans.tests.test_artisans import jpeg_with_gps, links
from apps.leasing.models import Lease
from apps.maintenance import services
from apps.maintenance.models import Job, Rating, Ticket
from apps.orgs.services import invite, link_invites
from apps.payments.tests.test_payments import make_lease
from conftest import make_user

pytestmark = pytest.mark.django_db
TENANT_PHONE = "+2348031110001"


@pytest.fixture
def tenant_user(db):
    return make_user(phone=TENANT_PHONE, first="Chidi", last="Okafor")


@pytest.fixture
def lease(org, user, tenant_user):
    tenant = make_lease(org, user, phone=TENANT_PHONE)
    return Lease.objects.get(tenant=tenant)


def make_artisan(phone="+2348055550001", name="Musa Plumbing Works", trades=("plumbing",), verified=True):
    u = make_user(phone=phone, first=name.split()[0])
    p = artisans.apply(
        user=u,
        display_name=name,
        trades=list(trades),
        service_areas=["Lekki"],
        address="4 Ado Road",
        consent=True,
    )
    if verified:
        ArtisanProfile.objects.filter(pk=p.pk).update(status="verified", verified_at=timezone.now())
        p.refresh_from_db()
    return p


@pytest.fixture
def artisan(db):
    return make_artisan()


def as_(client, u):
    client.force_authenticate(u)
    return client


def report(client, lease, **over):
    body = {
        "lease": str(lease.pk),
        "category": "plumbing",
        "priority": "urgent",
        "title": "Kitchen tap leaking",
        "description": "Water drips all night from the kitchen tap.",
        "access_notes": "After 4pm",
        **over,
    }
    return client.post(
        reverse("v1:my-ticket-list"),
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY=over.pop("key", "ticket-key-000000001"),
    )


def org_url(name, org, *args):
    return reverse(f"v1:{name}", args=[org.pk, *args])


def test_full_repair_flow(api_client, org, user, tenant_user, lease, artisan, _sms_outbox):
    # 1. tenant reports, with a photo
    r = report(as_(api_client, tenant_user), lease)
    assert r.status_code == 201, r.json()
    t = r.json()
    assert t["status"] == "awaiting_approval" and t["reference"].startswith("R")
    assert t["tenant"] is None  # tenants don't get the staff view of themselves
    assert t["can"] == ["cancel", "comment", "photo"]
    staff_sms = [b for to, b in _sms_outbox if "URGENT repair request" in b]
    assert staff_sms and "Chidi Okafor" in staff_sms[0] and "/repairs/" in staff_sms[0]
    photo = api_client.post(
        reverse("v1:my-ticket-photos", args=[t["id"]]), {"image": jpeg_with_gps()}, format="multipart"
    )
    assert photo.status_code == 201
    # the signed link serves the photo to anyone holding it, for a while
    assert api_client.get(photo.json()["url"]).status_code == 200

    # 2. landlord sees it, approves, assigns a verified artisan
    as_(api_client, user)
    listed = api_client.get(org_url("ticket-list", org)).json()["results"]
    assert [x["id"] for x in listed] == [t["id"]]
    assert listed[0]["tenant"]["phone_number"] == TENANT_PHONE
    assert (
        api_client.post(org_url("ticket-approve", org, t["id"]), {"note": "OK"}, format="json").status_code
        == 200
    )
    assert "approved" in _sms_outbox[-1][1] and _sms_outbox[-1][0] == TENANT_PHONE
    r = api_client.post(
        org_url("ticket-assign", org, t["id"]),
        {"artisan": str(artisan.pk), "note": "Bring tape"},
        format="json",
    )
    assert r.status_code == 200 and r.json()["status"] == "assigned"
    assert r.json()["job"]["artisan"]["phone_number"] is None  # not until they accept
    assert "new job" in _sms_outbox[-1][1] and _sms_outbox[-1][0] == artisan.user.phone_number

    # 3. artisan sees only the area until they accept
    as_(api_client, artisan.user)
    jobs = api_client.get(reverse("v1:my-job-list")).json()["results"]
    assert len(jobs) == 1 and jobs[0]["can"] == ["accept", "decline"]
    job_id = jobs[0]["id"]
    assert "address" not in jobs[0]["location"] and jobs[0]["contact"] is None
    assert jobs[0]["ticket"]["access_notes"] == "" and len(jobs[0]["ticket"]["photos"]) == 1
    when = (timezone.now() + timedelta(days=1)).isoformat()
    r = api_client.post(reverse("v1:my-job-accept", args=[job_id]), {"scheduled_for": when}, format="json")
    assert r.status_code == 200
    j = r.json()
    assert j["location"]["address"] == "Lekki" and j["contact"] == {
        "name": "Chidi",
        "phone_number": TENANT_PHONE,
    }
    assert j["ticket"]["access_notes"] == "After 4pm"
    assert any("Verified artisan" in b for to, b in _sms_outbox if to == TENANT_PHONE)

    # 4. arrives, finishes with a photo
    assert api_client.post(reverse("v1:my-job-start", args=[job_id])).json()["status"] == "on_site"
    done_photo = api_client.post(
        reverse("v1:my-job-photos", args=[job_id]), {"image": jpeg_with_gps()}, format="multipart"
    )
    assert done_photo.json()["stage"] == "completion"
    assert (
        api_client.post(reverse("v1:my-job-complete", args=[job_id]), {"note": ""}, format="json").status_code
        == 400
    )
    r = api_client.post(
        reverse("v1:my-job-complete", args=[job_id]), {"note": "Replaced washer"}, format="json"
    )
    assert r.json()["status"] == "completed"
    assert "Please confirm" in _sms_outbox[-1][1]

    # 5. tenant confirms and rates
    as_(api_client, tenant_user)
    mine = api_client.get(reverse("v1:my-ticket-detail", args=[t["id"]])).json()
    assert mine["status"] == "done" and mine["can"] == ["confirm", "reopen", "comment", "photo"]
    assert mine["job"]["artisan"]["phone_number"] == artisan.user.phone_number
    r = api_client.post(reverse("v1:my-ticket-confirm", args=[t["id"]]))
    assert r.json()["status"] == "confirmed" and r.json()["can"] == ["rate"]
    r = api_client.post(
        reverse("v1:my-ticket-rate", args=[t["id"]]), {"score": 5, "comment": "Fast"}, format="json"
    )
    assert r.json()["rating"] == {"score": 5, "comment": "Fast"} and r.json()["can"] == []
    assert (
        api_client.post(reverse("v1:my-ticket-rate", args=[t["id"]]), {"score": 4}, format="json").status_code
        == 400
    )
    artisan.refresh_from_db()
    assert (artisan.jobs_completed, artisan.rating_avg, artisan.rating_count) == (1, 5.0, 1)
    kinds = [e["kind"] for e in mine["events"]]
    assert kinds[:4] == ["created", "approved", "assigned", "accepted"]
    # landlords see they've used this artisan before
    as_(api_client, user)
    assert api_client.get(org_url("org-artisans", org)).json()[0]["jobs_with_us"] == 1


def test_report_rules(api_client, org, user, tenant_user, lease):
    as_(api_client, tenant_user)
    first = report(api_client, lease)
    again = report(api_client, lease, key="ticket-key-000000002")  # double tap on a new key
    assert again.json()["id"] == first.json()["id"]
    assert report(api_client, lease, title="x", key="ticket-key-000000003").status_code == 400
    # someone else's lease, or a non-tenant
    stranger = make_user(phone="+2348099990000")
    as_(api_client, stranger)
    assert report(api_client, lease, key="ticket-key-000000004").status_code == 400
    assert api_client.get(reverse("v1:my-ticket-detail", args=[first.json()["id"]])).status_code == 404
    # emergencies tell the tenant to call 112 and still go to staff
    as_(api_client, tenant_user)
    r = report(
        api_client, lease, priority="emergency", title="Burst pipe flooding", key="ticket-key-000000005"
    )
    assert r.status_code == 201


def test_emergency_reply_mentions_112(api_client, org, user, tenant_user, lease, _sms_outbox):
    assert services._emergency_extra("emergency").endswith("112 now.")


def test_reject_and_cancel(api_client, org, user, tenant_user, lease, _sms_outbox):
    t = report(as_(api_client, tenant_user), lease).json()
    as_(api_client, user)
    assert api_client.post(org_url("ticket-reject", org, t["id"]), {}, format="json").status_code == 400
    r = api_client.post(
        org_url("ticket-reject", org, t["id"]), {"reason": "Tenant damage, fix yourself"}, format="json"
    )
    assert r.json()["status"] == "rejected"
    assert "not approved" in _sms_outbox[-1][1] and "fix yourself" in _sms_outbox[-1][1]
    assert api_client.post(org_url("ticket-approve", org, t["id"]), {}, format="json").json()["error"][
        "code"
    ] == ("ticket_wrong_state")
    t2 = report(
        as_(api_client, tenant_user),
        lease,
        title="Door lock broken",
        category="locksmith",
        key="ticket-key-000000009",
    ).json()
    r = api_client.post(
        reverse("v1:my-ticket-cancel", args=[t2["id"]]), {"reason": "Fixed it myself"}, format="json"
    )
    assert r.json()["status"] == "cancelled"
    assert any("tenant cancelled" in b for _to, b in _sms_outbox)


def test_permissions(api_client, org, user, tenant_user, lease, artisan):
    t = report(as_(api_client, tenant_user), lease).json()
    # an agent can view and assign but not approve; a viewer can only look
    agent, viewer = make_user(phone="+2348077770001"), make_user(phone="+2348077770002")
    invite(org=org, phone_number=agent.phone_number, role="agent", by=user)
    invite(org=org, phone_number=viewer.phone_number, role="viewer", by=user)
    link_invites(agent)
    link_invites(viewer)
    as_(api_client, agent)
    assert api_client.get(org_url("ticket-detail", org, t["id"])).status_code == 200
    assert api_client.post(org_url("ticket-approve", org, t["id"]), {}, format="json").status_code == 403
    as_(api_client, viewer)
    assert (
        api_client.post(org_url("ticket-comments", org, t["id"]), {"note": "hi"}, format="json").status_code
        == 403
    )
    # other organizations don't see it at all; the artisan sees nothing before an offer
    other = make_user(phone="+2348077770003")
    from apps.orgs.services import create_organization

    other_org = create_organization(user=other, name="Other Homes", kind="landlord")
    as_(api_client, other)
    assert api_client.get(org_url("ticket-detail", other_org, t["id"])).status_code == 404
    as_(api_client, artisan.user)
    assert api_client.get(reverse("v1:my-job-list")).json()["results"] == []


def test_only_verified_available_artisans_can_be_assigned(api_client, org, user, tenant_user, lease):
    t = report(as_(api_client, tenant_user), lease).json()
    as_(api_client, user)
    api_client.post(org_url("ticket-approve", org, t["id"]), {}, format="json")
    pending = make_artisan(verified=False)
    r = api_client.post(org_url("ticket-assign", org, t["id"]), {"artisan": str(pending.pk)}, format="json")
    assert "artisan" in r.json()["error"]["details"]
    # the tenant can't be assigned their own ticket
    own = artisans.apply(
        user=tenant_user,
        display_name="Chidi Fix",
        trades=["plumbing"],
        service_areas=["Lekki"],
        address="x",
        consent=True,
    )
    ArtisanProfile.objects.filter(pk=own.pk).update(status="verified")
    r = api_client.post(org_url("ticket-assign", org, t["id"]), {"artisan": str(own.pk)}, format="json")
    assert r.status_code == 400


def test_decline_and_offer_expiry_return_ticket_to_staff(
    api_client, org, user, tenant_user, lease, artisan, _sms_outbox
):
    t = report(as_(api_client, tenant_user), lease).json()
    as_(api_client, user)
    api_client.post(org_url("ticket-approve", org, t["id"]), {}, format="json")
    api_client.post(org_url("ticket-assign", org, t["id"]), {"artisan": str(artisan.pk)}, format="json")
    job = Job.objects.get()
    as_(api_client, artisan.user)
    r = api_client.post(reverse("v1:my-job-decline", args=[job.pk]), {"reason": "Too far"}, format="json")
    assert r.json()["status"] == "declined"
    assert Ticket.objects.get().status == "approved"
    assert any("declined" in b and "Choose another artisan" in b for _to, b in _sms_outbox)
    # the decline reason is an internal note: the tenant doesn't see it
    as_(api_client, tenant_user)
    assert "declined" not in [
        e["kind"] for e in api_client.get(reverse("v1:my-ticket-detail", args=[t["id"]])).json()["events"]
    ]

    second = make_artisan(phone="+2348055550009", name="Bayo Pipes")
    as_(api_client, user)
    api_client.post(org_url("ticket-assign", org, t["id"]), {"artisan": str(second.pk)}, format="json")
    Job.objects.filter(artisan=second).update(offer_expires_at=timezone.now() - timedelta(minutes=1))
    as_(api_client, second.user)
    late = api_client.post(
        reverse("v1:my-job-accept", args=[Job.objects.get(artisan=second).pk]), {}, format="json"
    )
    assert late.status_code == 409
    assert services.housekeeping()["expired"] == 1
    assert Ticket.objects.get().status == "approved"
    assert any("didn't answer" in b for _to, b in _sms_outbox)


def test_reassign_cancels_the_open_offer(api_client, org, user, tenant_user, lease, artisan, _sms_outbox):
    t = report(as_(api_client, tenant_user), lease).json()
    as_(api_client, user)
    api_client.post(org_url("ticket-approve", org, t["id"]), {}, format="json")
    api_client.post(org_url("ticket-assign", org, t["id"]), {"artisan": str(artisan.pk)}, format="json")
    second = make_artisan(phone="+2348055550009", name="Bayo Pipes")
    r = api_client.post(org_url("ticket-assign", org, t["id"]), {"artisan": str(second.pk)}, format="json")
    assert r.status_code == 200 and r.json()["job"]["artisan"]["display_name"] == "Bayo Pipes"
    assert Job.objects.get(artisan=artisan).status == "cancelled"
    assert any(to == artisan.user.phone_number and "cancelled" in b for to, b in _sms_outbox)


def test_reopen_goes_back_to_the_same_artisan(
    api_client, org, user, tenant_user, lease, artisan, _sms_outbox
):
    t = report(as_(api_client, tenant_user), lease).json()
    ticket = Ticket.objects.get()
    services.approve(ticket, by=user)
    job = services.assign(ticket, artisan=artisan, by=user)
    services.accept(job)
    services.complete(job, note="Done")
    as_(api_client, tenant_user)
    assert (
        api_client.post(
            reverse("v1:my-ticket-reopen", args=[t["id"]]), {"note": ""}, format="json"
        ).status_code
        == 400
    )
    r = api_client.post(
        reverse("v1:my-ticket-reopen", args=[t["id"]]), {"note": "Still dripping"}, format="json"
    )
    assert r.json()["status"] == "assigned"
    job.refresh_from_db()
    assert job.status == "accepted"
    assert any(to == artisan.user.phone_number and "Still dripping" in b for to, b in _sms_outbox)


def test_reminder_then_auto_confirm(org, user, tenant_user, lease, artisan, _sms_outbox, api_client):
    report(as_(api_client, tenant_user), lease)
    ticket = Ticket.objects.get()
    services.approve(ticket, by=user)
    job = services.assign(ticket, artisan=artisan, by=user)
    services.accept(job)
    services.complete(job, note="Done")
    now = timezone.now()
    assert services.housekeeping(now + timedelta(days=1)) == {
        "expired": 0,
        "reminded": 0,
        "auto_confirmed": 0,
    }
    assert services.housekeeping(now + timedelta(days=3))["reminded"] == 1
    assert "is it fixed?" in _sms_outbox[-1][1]
    assert services.housekeeping(now + timedelta(days=4))["reminded"] == 0  # once only
    assert services.housekeeping(now + timedelta(days=8))["auto_confirmed"] == 1
    ticket.refresh_from_db()
    assert ticket.status == "confirmed" and ticket.auto_confirmed
    artisan.refresh_from_db()
    assert artisan.jobs_completed == 1


def test_staff_ticket_resolve_and_confirm_without_tenant(api_client, org, user, artisan):
    from apps.properties.models import Property, Unit

    prop = Property.objects.create(organization=org, name="Vacant Block", address="Yaba")
    unit = Unit.objects.create(property=prop, label="Flat 9")
    as_(api_client, user)
    r = api_client.post(
        org_url("ticket-list", org),
        {
            "unit": str(unit.pk),
            "category": "painting",
            "title": "Repaint before letting",
            "description": "Whole flat needs a fresh coat before viewings.",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="staff-ticket-0000001",
    )
    assert r.status_code == 201 and r.json()["status"] == "approved" and r.json()["raised_by_staff"]
    t = r.json()
    r = api_client.post(
        org_url("ticket-resolve", org, t["id"]), {"note": "Our caretaker did it"}, format="json"
    )
    assert r.json()["status"] == "done" and "confirm" in r.json()["can"]
    r = api_client.post(org_url("ticket-confirm", org, t["id"]))
    assert r.json()["status"] == "confirmed"
    # a unit from another org is refused
    from apps.orgs.services import create_organization

    other = create_organization(user=make_user(phone="+2348077779999"), name="X", kind="landlord")
    p2 = Property.objects.create(organization=other, name="Theirs", address="Ikoyi")
    u2 = Unit.objects.create(property=p2, label="A")
    r = api_client.post(
        org_url("ticket-list", org),
        {
            "unit": str(u2.pk),
            "category": "painting",
            "title": "Not ours",
            "description": "Should be refused, really.",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="staff-ticket-0000002",
    )
    assert r.status_code == 404


def test_internal_comments_stay_with_staff(api_client, org, user, tenant_user, lease):
    t = report(as_(api_client, tenant_user), lease).json()
    as_(api_client, user)
    api_client.post(
        org_url("ticket-comments", org, t["id"]),
        {"note": "Tenant broke it last time", "internal": True},
        format="json",
    )
    api_client.post(org_url("ticket-comments", org, t["id"]), {"note": "We'll look today"}, format="json")
    staff_notes = [e["note"] for e in api_client.get(org_url("ticket-detail", org, t["id"])).json()["events"]]
    assert "Tenant broke it last time" in staff_notes
    as_(api_client, tenant_user)
    notes = [
        e["note"] for e in api_client.get(reverse("v1:my-ticket-detail", args=[t["id"]])).json()["events"]
    ]
    assert "We'll look today" in notes and "Tenant broke it last time" not in notes
    # a tenant can't mark their comment internal
    api_client.post(
        reverse("v1:my-ticket-comments", args=[t["id"]]), {"note": "secret?", "internal": True}, format="json"
    )
    as_(api_client, user)
    ev = [
        e
        for e in api_client.get(org_url("ticket-detail", org, t["id"])).json()["events"]
        if e["note"] == "secret?"
    ]
    assert ev and ev[0]["internal"] is False


def test_photo_links_expire_and_photos_are_limited(api_client, org, user, tenant_user, lease, settings):
    t = report(as_(api_client, tenant_user), lease).json()
    url = reverse("v1:my-ticket-photos", args=[t["id"]])
    settings.MAINTENANCE_MAX_PHOTOS = 2
    for _ in range(2):
        assert api_client.post(url, {"image": jpeg_with_gps()}, format="multipart").status_code == 201
    assert api_client.post(url, {"image": jpeg_with_gps()}, format="multipart").status_code == 400
    from django.core.files.uploadedfile import SimpleUploadedFile

    fake = SimpleUploadedFile("x.jpg", b"not an image", content_type="image/jpeg")
    settings.MAINTENANCE_MAX_PHOTOS = 6
    assert api_client.post(url, {"image": fake}, format="multipart").status_code == 400
    link = api_client.get(reverse("v1:my-ticket-detail", args=[t["id"]])).json()["photos"][0]["url"]
    anon = type(api_client)()
    assert anon.get(link).status_code == 200
    assert anon.get(link[:-3] + "abc/").status_code == 404  # tampered
    settings.PRIVATE_MEDIA_LINK_SECONDS = -1
    assert anon.get(link).status_code == 404  # expired


def test_rating_validation(api_client, org, user, tenant_user, lease, artisan):
    t = report(as_(api_client, tenant_user), lease).json()
    ticket = Ticket.objects.get()
    services.approve(ticket, by=user)
    job = services.assign(ticket, artisan=artisan, by=user)
    services.accept(job)
    services.complete(job, note="Done")
    as_(api_client, tenant_user)
    assert (
        api_client.post(reverse("v1:my-ticket-rate", args=[t["id"]]), {"score": 5}, format="json").status_code
        == 409
    )
    api_client.post(reverse("v1:my-ticket-confirm", args=[t["id"]]))
    assert (
        api_client.post(reverse("v1:my-ticket-rate", args=[t["id"]]), {"score": 6}, format="json").status_code
        == 400
    )
    assert Rating.objects.count() == 0


def test_guarantor_links_reused_by_tests():
    assert links([("+234", "see https://x/v/abc_DEF-1 now")]) == ["abc_DEF-1"]
