import hashlib
import hmac
import json
from datetime import timedelta

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.messaging import services
from apps.messaging.models import Contact, Conversation, Escalation, Message
from apps.messaging.whatsapp import MockWhatsApp
from apps.notifications.models import Notification
from conftest import make_user

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _wa_outbox():
    MockWhatsApp.outbox.clear()
    yield MockWhatsApp.outbox


def payload(*, wa_id="2348031110001", msg_id="wamid.IN1", text="Hello", name="Chidi"):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": wa_id, "profile": {"name": name}}],
                            "messages": [
                                {
                                    "from": wa_id,
                                    "id": msg_id,
                                    "timestamp": "1760000000",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        }
                    }
                ]
            }
        ],
    }


def post_signed(client, body: dict, secret=MockWhatsApp.SECRET):
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(secret, raw, hashlib.sha256).hexdigest()
    return client.post(
        reverse("whatsapp-webhook"), raw, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=sig
    )


@override_settings(WHATSAPP_VERIFY_TOKEN="verify-me")
def test_webhook_verification_handshake(client):
    url = reverse("whatsapp-webhook")
    ok = client.get(url, {"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "12345"})
    assert ok.status_code == 200 and ok.content == b"12345"
    assert (
        client.get(
            url, {"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"}
        ).status_code
        == 403
    )


@override_settings(MESSAGING_INBOUND_HANDLER="")
def test_inbound_message_is_stored_once_and_links_the_user(client):
    user = make_user(phone="+2348031110001")
    assert post_signed(client, payload()).status_code == 200
    assert post_signed(client, payload()).status_code == 200  # Meta retries the same delivery
    msg = Message.objects.get()
    assert msg.body == "Hello" and msg.direction == "in"
    contact = Contact.objects.get()
    assert contact.user == user and contact.name == "Chidi" and contact.opt_in == "opted_in"
    assert Conversation.objects.get().last_inbound_at is not None


def test_bad_signature_is_rejected(client):
    assert post_signed(client, payload(), secret=b"wrong").status_code == 401
    assert Message.objects.count() == 0


@override_settings(MESSAGING_INBOUND_HANDLER="")
def test_stop_and_start(client, _wa_outbox):
    post_signed(client, payload(text="STOP", msg_id="wamid.1"))
    contact = Contact.objects.get()
    assert contact.opt_in == "opted_out" and "START" in _wa_outbox[-1]["body"]
    post_signed(client, payload(text="start", msg_id="wamid.2"))
    contact.refresh_from_db()
    assert contact.opt_in == "opted_in"


@override_settings(MESSAGING_INBOUND_HANDLER="apps.messaging.tests.test_messaging.echo_handler")
def test_inbound_goes_to_the_handler_unless_handed_off(client, _wa_outbox):
    post_signed(client, payload(text="hi", msg_id="wamid.1"))
    assert _wa_outbox[-1]["body"] == "echo: hi"
    convo = Conversation.objects.get()
    staff = make_user(phone="+2348099990000")
    services.take_over(convo, by=staff)
    post_signed(client, payload(text="are you there?", msg_id="wamid.2"))
    assert _wa_outbox[-1]["body"] == "echo: hi"  # assistant stayed silent


def echo_handler(message):
    services.send_text(message.conversation, f"echo: {message.body}", force=True)


@override_settings(MESSAGING_INBOUND_HANDLER="")
def test_status_updates_and_failed_whatsapp_falls_back_to_sms(client, _sms_outbox):
    contact = services.get_contact("2348031110001")
    services._set_opt_in(contact, True)
    with override_settings(WHATSAPP_TEMPLATES={"receipt": {"name": "payment_receipt", "language": "en"}}):
        from apps.notifications.services import notify

        note = notify(to="+2348031110001", body="Payment received", kind="receipt", wa_params=["NGN 1.00"])
    assert note.channel == "whatsapp"
    out = Message.objects.get(kind="template")
    assert out.status == "sent" and out.template_name == "payment_receipt"
    status_body = {
        "entry": [
            {"changes": [{"value": {"statuses": [{"id": out.provider_message_id, "status": "delivered"}]}}]}
        ]
    }
    post_signed(client, status_body)
    out.refresh_from_db()
    assert out.status == "delivered"
    failed = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [
                                {
                                    "id": out.provider_message_id,
                                    "status": "failed",
                                    "errors": [{"code": 131026, "title": "Undeliverable"}],
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    post_signed(client, failed)
    out.refresh_from_db()
    assert out.status == "failed" and out.error == "Undeliverable"
    assert _sms_outbox[-1] == ("+2348031110001", "Payment received")
    assert Notification.objects.filter(kind="receipt:fallback", channel="sms").count() == 1


def test_notify_uses_sms_without_template_or_opt_in(_sms_outbox):
    from apps.notifications.services import notify

    note = notify(to="+2348031110001", body="Hi", kind="receipt", wa_params=["x"])
    assert note.channel == "sms" and _sms_outbox[-1][1] == "Hi"


def test_free_text_only_inside_24h_window():
    contact = services.get_contact("2348031110001")
    convo = services.open_conversation(contact)
    with pytest.raises(services.OutsideWindow):
        services.send_text(convo, "hello")
    Conversation.objects.filter(pk=convo.pk).update(last_inbound_at=timezone.now() - timedelta(hours=2))
    convo.refresh_from_db()
    msg = services.send_text(convo, "hello")
    msg.refresh_from_db()
    assert msg.status == "sent"


def test_inbox_takeover_reply_release(auth_client, org, user, _wa_outbox, _sms_outbox):
    contact = services.get_contact("2348031110001", "Chidi")
    convo = services.open_conversation(contact)
    Conversation.objects.filter(pk=convo.pk).update(last_inbound_at=timezone.now())
    esc = services.escalate(convo, reason="dispute", summary="Says he paid September", organization=org)
    assert esc.organization == org and _sms_outbox  # owner alerted
    base = f"/api/v1/orgs/{org.pk}/conversations/"
    listed = auth_client.get(base, {"escalated": "1"}).json()["results"]
    assert listed[0]["open_escalation"]["reason"] == "dispute" and listed[0]["contact_name"] == "Chidi"
    reply = auth_client.post(f"{base}{convo.pk}/reply/", {"body": "Hi Chidi, checking now."}, format="json")
    assert reply.status_code == 201 and reply.json()["status"] == "handoff"
    assert _wa_outbox[-1]["body"] == "Hi Chidi, checking now."
    released = auth_client.post(f"{base}{convo.pk}/release/").json()
    assert released["status"] == "bot"
    assert Escalation.objects.get().status == "resolved"


def test_inbox_is_org_scoped(api_client, org):
    convo = services.open_conversation(services.get_contact("2348031110001"))
    services.escalate(convo, reason="dispute", organization=org)
    stranger = make_user(phone="+2348055555555")
    api_client.force_authenticate(stranger)
    assert api_client.get(f"/api/v1/orgs/{org.pk}/conversations/").status_code == 404


def test_my_whatsapp_preference(auth_client, user):
    assert auth_client.get(reverse("v1:my-whatsapp")).json() == {"opted_in": False}
    auth_client.put(reverse("v1:my-whatsapp"), {"opted_in": True}, format="json")
    assert auth_client.get(reverse("v1:my-whatsapp")).json() == {"opted_in": True}
    assert Contact.objects.get().user == user


def test_inbox_reply_retry_sends_once(auth_client, org, _wa_outbox):
    convo = services.open_conversation(services.get_contact("2348031110001"))
    Conversation.objects.filter(pk=convo.pk).update(last_inbound_at=timezone.now(), organization=org)
    url = f"/api/v1/orgs/{org.pk}/conversations/{convo.pk}/reply/"
    for _ in range(2):
        resp = auth_client.post(
            url, {"body": "On it"}, format="json", HTTP_IDEMPOTENCY_KEY="inbox-reply-0001-abcd"
        )
        assert resp.status_code == 201
    assert [m["body"] for m in _wa_outbox] == ["On it"]
