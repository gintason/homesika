"""Estate tools: a verified resident's estate, gate passes and panic alerts (both need a YES)."""

from datetime import date

import pytest

from apps.assistant import llm, services
from apps.assistant.principal import for_contact, for_user
from apps.assistant.tests.test_assistant import FakeLlm, text_resp, tool_resp
from apps.estates import services as estates
from apps.estates.models import Announcement, DuesPlan, GatePass
from apps.messaging import services as messaging
from apps.orgs.models import Membership
from apps.security.models import AlertDelivery, PanicAlert
from conftest import make_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate(org, user):
    e = estates.create_estate(org=org, by=user, name="Palm Grove Estate", address="1 Palm Ave")
    estates.add_houses(e, ["A1", "A2"])
    DuesPlan.objects.create(
        estate=e, name="Security levy", amount=15_000_00, start_date=date.today().replace(day=1)
    )
    Announcement.objects.create(estate=e, title="Water off", body="Saturday 9am-1pm", created_by=user)
    guard = make_user(phone="+2348030000009", first="Guard")
    Membership.objects.create(organization=org, user=guard, role="security")
    return e


@pytest.fixture
def ngozi(estate, user):
    u = make_user(phone="+2348031112222", first="Ngozi", last="Eze")
    return estates.approve(estates.join(user=u, code=estate.join_code, house="A1"), by=user)


def test_resident_role_and_my_estate(monkeypatch, ngozi):
    p = for_user(ngozi.user)
    assert "resident" in p.roles and "Palm Grove Estate" in p.context_text()
    from apps.assistant import tools

    names = {t.name for t in tools.for_principal(p)}
    assert {"my_estate", "create_gate_pass", "raise_panic_alert"} <= names
    out = tools.my_estate(p, None, None)
    assert out["house"] == "A1" and out["dues_owed"] == "15000.00"
    assert out["announcements"][0]["title"] == "Water off"


def test_gate_pass_by_chat_after_yes(monkeypatch, ngozi, _sms_outbox):
    fake = FakeLlm(
        tool_resp(
            "create_gate_pass",
            {
                "estate_id": None,
                "visitor_name": "Tolu",
                "visitor_phone": "08035551234",
                "hours": 4,
                "max_uses": 1,
            },
        ),
        text_resp("I'll make a 4-hour pass for Tolu. Reply YES to confirm."),
    )
    monkeypatch.setattr(llm, "client", lambda: fake)
    convo = messaging.open_conversation(messaging.get_contact("2348031112222", "Ngozi"))
    p = for_contact(convo.contact)
    reply = services.handle_message(convo, p, "My friend Tolu is coming, 08035551234")
    assert reply.pending_action.tool == "create_gate_pass" and not GatePass.objects.exists()
    done = services.handle_message(convo, p, "YES")
    gp = GatePass.objects.get()
    assert gp.code in done.text and "texted it" in done.text
    assert f"gate code is {gp.code}" in _sms_outbox[-1][1]


def test_panic_alert_by_whatsapp_for_resident_without_app(monkeypatch, org, user, estate, _sms_outbox):
    unit = estate.property.units.get(label="A2")
    m = estates.add_member(
        estate=estate, by=user, full_name="Bayo Ade", phone_number="08039998888", unit_id=unit.pk
    )
    assert m.user is None
    fake = FakeLlm(
        tool_resp("raise_panic_alert", {"estate_id": None, "kind": "robbery"}),
        text_resp("Call 112 now. Reply YES and I'll alert estate security."),
    )
    monkeypatch.setattr(llm, "client", lambda: fake)
    convo = messaging.open_conversation(messaging.get_contact("2348039998888", "Bayo"))
    p = for_contact(convo.contact)
    assert "resident" in p.roles
    reply = services.handle_message(convo, p, "Armed robbers dey for my compound now!")
    assert "112" in reply.text and reply.pending_action.tool == "raise_panic_alert"
    assert not PanicAlert.objects.exists()
    _sms_outbox.clear()
    done = services.handle_message(convo, p, "yes")
    alert = PanicAlert.objects.get()
    assert (
        alert.member == m
        and alert.raised_by is None
        and alert.kind == "robbery"
        and alert.channel == "whatsapp"
    )
    assert "112" in done.text
    assert AlertDelivery.objects.filter(alert=alert, audience="staff", channel="sms").count() == 2
    assert "+2348039998888" in {ph for ph, _t in _sms_outbox}  # the raiser is told it was sent
    assert not AlertDelivery.objects.filter(alert=alert, phone_number="+2348039998888").exists()


def test_not_a_resident_gets_no_estate_tools(org, user):
    from apps.assistant import tools

    names = {t.name for t in tools.for_principal(for_user(user))}
    assert "raise_panic_alert" not in names and "list_estate_alerts" in names
