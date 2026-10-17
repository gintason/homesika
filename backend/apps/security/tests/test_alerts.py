from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from apps.estates import services as estates
from apps.estates.tests.test_estates import as_, org_url, staff
from apps.notifications.models import PushDevice
from apps.security import services
from apps.security.models import AlertDelivery, PanicAlert
from conftest import make_user

pytestmark = pytest.mark.django_db
GUARD_TOKEN = "ExponentPushToken[guard-aaaaaaaaaaaaa]"
NEIGHBOUR_TOKEN = "ExponentPushToken[neighbour-aaaaaaaaa]"
RAISER_TOKEN = "ExponentPushToken[raiser-aaaaaaaaaaaa]"


@pytest.fixture
def estate(org, user):
    e = estates.create_estate(org=org, by=user, name="Palm Grove Estate", address="1 Palm Ave, Lekki")
    estates.add_houses(e, ["A1", "A2", "A3"])
    return e


def resident(estate, by, phone, first, house, token=None):
    u = make_user(phone=phone, first=first, last="Resident")
    m = estates.approve(estates.join(user=u, code=estate.join_code, house=house), by=by)
    if token:
        PushDevice.objects.create(user=u, token=token, platform="android")
    return m


@pytest.fixture
def people(org, user, estate):
    guard = staff(org, "security", "+2348030000009")
    PushDevice.objects.create(user=guard, token=GUARD_TOKEN, platform="android")
    raiser = resident(estate, user, "+2348031110001", "Ngozi", "A1", RAISER_TOKEN)
    neighbour = resident(estate, user, "+2348031110002", "Femi", "A2", NEIGHBOUR_TOKEN)
    no_app = resident(estate, user, "+2348031110003", "Bisi", "A3")
    return {"guard": guard, "raiser": raiser, "neighbour": neighbour, "no_app": no_app}


def trigger(client, estate, **over):
    body = {"estate": str(estate.pk), "client_id": "phone-alert-0001", **over}
    return client.post(reverse("v1:my-alert-list"), body, format="json")


def deliveries(alert, **f):
    return list(
        AlertDelivery.objects.filter(alert=alert, **f).values_list("audience", "channel", "phone_number")
    )


def test_alert_reaches_everyone(api_client, org, user, estate, people, _sms_outbox, _push_outbox):
    _sms_outbox.clear()
    r = trigger(
        as_(api_client, people["raiser"].user),
        estate,
        location={"lat": 6.4281234567, "lng": 3.4219, "accuracy": 12.34},
    )
    assert r.status_code == 201, r.data
    alert = PanicAlert.objects.get(pk=r.data["id"])
    assert alert.location == '{"lat": 6.428123, "lng": 3.4219, "accuracy": 12.3}'
    pushed = {p.token for p in _push_outbox}
    # staff (guard + owner without a device), the neighbour by push; raiser told it was sent
    assert {GUARD_TOKEN, NEIGHBOUR_TOKEN, RAISER_TOKEN} == pushed
    assert all(p.urgent for p in _push_outbox if p.token != RAISER_TOKEN)
    assert "EMERGENCY at Palm Grove Estate" in _push_outbox[0].title
    assert "A1" in _push_outbox[0].body
    guard_push = next(p for p in _push_outbox if p.token == GUARD_TOKEN)
    neighbour_push = next(p for p in _push_outbox if p.token == NEIGHBOUR_TOKEN)
    assert guard_push.data["org"] == str(estate.organization_id) and guard_push.data["audience"] == "staff"
    assert "org" not in neighbour_push.data
    sms_to = {p for p, _t in _sms_outbox}
    # staff always get SMS too; the resident without the app gets SMS; the neighbour with push does not
    assert {"+2348030000009", user.phone_number, "+2348031110003"} <= sms_to
    assert "+2348031110002" not in sms_to
    assert ("resident", "push", "+2348031110002") in deliveries(alert)
    assert ("resident", "sms", "+2348031110003") in deliveries(alert)
    assert not AlertDelivery.objects.filter(alert=alert, user=people["raiser"].user).exists()


def test_retry_and_second_press_return_same_alert(api_client, estate, people):
    c = as_(api_client, people["raiser"].user)
    first = trigger(c, estate)
    again = trigger(c, estate)
    assert again.status_code == 200 and again.data["id"] == first.data["id"]
    second = trigger(c, estate, client_id="phone-alert-0002", kind="robbery")
    assert second.status_code == 200 and second.data["id"] == first.data["id"]
    assert second.data["kind"] == "robbery"  # the second press said what's happening
    assert PanicAlert.objects.count() == 1


@override_settings(PANIC_MAX_PER_HOUR=2)
def test_rate_limit_says_call_112(api_client, user, estate, people):
    c = as_(api_client, people["raiser"].user)
    for i in range(2):
        r = trigger(c, estate, client_id=f"phone-alert-000{i}")
        services.close(
            PanicAlert.objects.get(pk=r.data["id"]), by=people["raiser"].user, outcome="cancelled", note=""
        )
    r = trigger(c, estate, client_id="phone-alert-0009")
    assert r.status_code == 429
    assert "112" in r.json()["error"]["message"]


def test_silent_alert_only_staff_and_nothing_to_raiser(
    api_client, user, estate, people, _sms_outbox, _push_outbox
):
    _sms_outbox.clear()
    r = trigger(as_(api_client, people["raiser"].user), estate, silent=True, kind="kidnapping")
    alert = PanicAlert.objects.get(pk=r.data["id"])
    assert {a for a, _c, _p in deliveries(alert)} == {"staff"}
    assert RAISER_TOKEN not in {p.token for p in _push_outbox}
    assert "+2348031110001" not in {p for p, _t in _sms_outbox}
    # staff acknowledging still sends nothing to the raiser
    as_(api_client, people["guard"])
    api_client.post(org_url("alert-acknowledge", alert.estate.organization, alert.pk))
    assert RAISER_TOKEN not in {p.token for p in _push_outbox}
    assert "+2348031110001" not in {p for p, _t in _sms_outbox}


def test_dead_token_falls_back_to_sms_at_once(api_client, user, estate, people, _sms_outbox):
    PushDevice.objects.filter(token=NEIGHBOUR_TOKEN).update(token="ExponentPushToken[Invalid-neighbour00]")
    _sms_outbox.clear()
    trigger(as_(api_client, people["raiser"].user), estate)
    assert "+2348031110002" in {p for p, _t in _sms_outbox}
    assert not PushDevice.objects.get(token="ExponentPushToken[Invalid-neighbour00]").is_active
    d = AlertDelivery.objects.get(phone_number="+2348031110002", channel="sms")
    assert d.fallback_for is not None and d.fallback_for.status == "failed"


def _age(alert, seconds):
    AlertDelivery.objects.filter(alert=alert, channel="push").update(
        sent_at=timezone.now() - timedelta(seconds=seconds)
    )


@override_settings(PANIC_PUSH_FALLBACK_SECONDS=45)
def test_receipts_and_fallback(api_client, estate, people, _sms_outbox):
    r = trigger(as_(api_client, people["raiser"].user), estate)
    alert = PanicAlert.objects.get(pk=r.data["id"])
    guard_push = AlertDelivery.objects.get(alert=alert, user=people["guard"], channel="push")
    neighbour_push = AlertDelivery.objects.get(alert=alert, user=people["neighbour"].user, channel="push")
    from apps.notifications.push import MockPush

    MockPush.receipts_map[neighbour_push.provider_ref] = "pending"
    _age(alert, 10)
    assert services.check_deliveries() == {"delivered": 0, "fallback_sms": 0}  # too early to judge
    _age(alert, 60)
    assert services.check_deliveries() == {"delivered": 1, "fallback_sms": 0}  # guard ok; neighbour waits
    guard_push.refresh_from_db()
    assert guard_push.status == "delivered"
    _sms_outbox.clear()
    _age(alert, 100)
    assert services.check_deliveries()["fallback_sms"] == 1  # still no receipt: SMS
    assert [p for p, _t in _sms_outbox] == ["+2348031110002"]
    assert services.check_deliveries()["fallback_sms"] == 0  # never twice
    # an error receipt fails the push
    MockPush.receipts_map[neighbour_push.provider_ref] = "error:MessageRateExceeded"
    services.check_deliveries()
    neighbour_push.refresh_from_db()
    assert neighbour_push.status == "failed" and neighbour_push.error == "MessageRateExceeded"
    # SMS rows become delivered once the SMS provider sent them
    assert AlertDelivery.objects.filter(alert=alert, channel="sms", status="delivered").exists()


def test_received_marks_seen(api_client, estate, people):
    r = trigger(as_(api_client, people["raiser"].user), estate)
    as_(api_client, people["neighbour"].user)
    assert api_client.post(reverse("v1:my-alert-received", args=[r.data["id"]])).status_code == 204
    assert AlertDelivery.objects.get(user=people["neighbour"].user, channel="push").status == "acknowledged"
    # someone it wasn't sent to can't
    stranger = make_user(phone="+2348039990000", first="X")
    assert (
        as_(api_client, stranger).post(reverse("v1:my-alert-received", args=[r.data["id"]])).status_code
        == 404
    )


def test_desk_lifecycle_and_metrics(api_client, org, estate, people, _push_outbox):
    r = trigger(as_(api_client, people["raiser"].user), estate, kind="medical")
    aid = r.data["id"]
    as_(api_client, people["guard"])
    lst = api_client.get(org_url("alert-list", org))
    assert [a["id"] for a in lst.data["results"]] == [aid]
    assert (
        lst.data["results"][0]["house"] == "A1"
        and lst.data["results"][0]["raised_by_phone"] == "+2348031110001"
    )
    r = api_client.post(org_url("alert-acknowledge", org, aid))
    assert r.data["status"] == "acknowledged"
    assert any("seen your alert" in p.body for p in _push_outbox if p.token == RAISER_TOKEN)
    assert api_client.post(org_url("alert-acknowledge", org, aid)).status_code == 409
    r = api_client.post(org_url("alert-respond", org, aid), {"note": "Two guards going"}, format="json")
    assert r.data["status"] == "responding"
    assert (
        api_client.post(org_url("alert-resolve", org, aid), {}, format="json").status_code == 400
    )  # needs a note
    r = api_client.post(org_url("alert-false-alarm", org, aid), {"note": "Pressed by a child"}, format="json")
    assert r.data["status"] == "false_alarm"
    assert [n["kind"] for n in r.data["notes"]] == ["triggered", "acknowledged", "responding", "false_alarm"]
    assert r.data["metrics"]["staff_total"] == 2 and r.data["metrics"]["acknowledge_seconds"] is not None
    assert r.data["false_alarms_90d"] == 1
    assert any("All clear" in p.body for p in _push_outbox if p.token == NEIGHBOUR_TOKEN)
    assert api_client.get(org_url("alert-list", org)).data["results"] == []
    rep = api_client.get(org_url("alert-report", org), {"estate": str(estate.pk)})
    assert rep.data["alerts"] == 1 and rep.data["false_alarms"] == 1


def test_raiser_cancels(api_client, estate, people, _push_outbox):
    c = as_(api_client, people["raiser"].user)
    aid = trigger(c, estate).data["id"]
    r = c.post(reverse("v1:my-alert-cancel", args=[aid]))
    assert r.data["status"] == "cancelled"
    assert any("cancelled the alert" in p.body for p in _push_outbox if p.token == GUARD_TOKEN)


def test_who_can_raise_and_see(api_client, org, user, estate, people):
    pending = make_user(phone="+2348031110009", first="New")
    estates.join(user=pending, code=estate.join_code, house="A3")
    assert trigger(as_(api_client, pending), estate).status_code == 403
    assert as_(api_client, pending).get(org_url("alert-list", org)).status_code == 404
    accountant = staff(org, "accountant", "+2348030000010")
    assert as_(api_client, accountant).get(org_url("alert-list", org)).status_code == 403
    # estate staff can raise one too
    assert trigger(as_(api_client, people["guard"]), estate, client_id="guard-alert-00001").status_code == 201
    estate.panic_enabled = False
    estate.save()
    assert (
        trigger(as_(api_client, people["raiser"].user), estate, client_id="x-alert-0000001").status_code
        == 400
    )


def test_drill_goes_to_staff_only(api_client, org, user, estate, people, _push_outbox, _sms_outbox):
    _sms_outbox.clear()
    r = as_(api_client, user).post(org_url("alert-drill", org) + f"?estate={estate.pk}")
    assert r.status_code == 201, r.data
    assert r.data["kind"] == "drill"
    tokens = {p.token for p in _push_outbox}
    assert tokens == {GUARD_TOKEN}
    assert all(p.title.startswith("TEST") for p in _push_outbox)
    assert all(t.startswith("TEST") for _p, t in _sms_outbox)
    assert {p for p, _t in _sms_outbox} == {"+2348030000009"}  # the owner pressed it; not sent to themselves
    # a guard can't run drills
    assert (
        as_(api_client, people["guard"])
        .post(org_url("alert-drill", org) + f"?estate={estate.pk}")
        .status_code
        == 403
    )


@pytest.mark.django_db(transaction=True)
def test_desk_websocket(org, user, estate):
    from config.asgi import application

    guard = staff(org, "security", "+2348030000009")
    member = resident(estate, user, "+2348031110001", "Ngozi", "A1")
    accountant = staff(org, "accountant", "+2348030000010")

    async def run():
        bad = WebsocketCommunicator(
            application, f"/ws/estates/{estate.pk}/desk/", headers=[(b"origin", b"http://localhost")]
        )
        assert (await bad.connect())[0]
        await bad.send_json_to({"type": "auth", "token": str(AccessToken.for_user(accountant))})
        assert (await bad.receive_output())["type"] == "websocket.close"

        evil = WebsocketCommunicator(
            application, f"/ws/estates/{estate.pk}/desk/", headers=[(b"origin", b"https://evil.example")]
        )
        assert not (await evil.connect())[0]

        ws = WebsocketCommunicator(
            application, f"/ws/estates/{estate.pk}/desk/", headers=[(b"origin", b"http://localhost")]
        )
        assert (await ws.connect())[0]
        await ws.send_json_to({"type": "auth", "token": str(AccessToken.for_user(guard))})
        assert await ws.receive_json_from() == {"type": "ready"}
        from channels.db import database_sync_to_async

        await database_sync_to_async(services.raise_alert)(
            user=member.user, estate=estate, client_id="ws-test-0001"
        )
        msg = await ws.receive_json_from(timeout=5)
        assert msg["type"] == "alert.new" and msg["alert"]["house"] == "A1"
        await ws.disconnect()

    async_to_sync(run)()
