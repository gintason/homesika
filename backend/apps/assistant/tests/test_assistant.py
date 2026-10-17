import hashlib
import hmac
import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.assistant import guardrails, llm, services, tools
from apps.assistant.models import AssistantTurn, KbArticle, PendingAction
from apps.assistant.principal import for_contact, for_user
from apps.leasing.models import Charge
from apps.listings.models import Lead, Listing, ViewingSlot
from apps.messaging import services as messaging
from apps.messaging.models import Contact, Escalation
from apps.messaging.whatsapp import MockWhatsApp
from apps.orgs.services import create_organization, invite, link_invites
from apps.payments import services as payments
from apps.payments.models import PaymentLink
from apps.payments.tests.test_payments import make_lease
from conftest import make_user

pytestmark = pytest.mark.django_db
TENANT_PHONE = "+2348099999999"


@pytest.fixture(autouse=True)
def _wa():
    MockWhatsApp.outbox.clear()
    yield MockWhatsApp.outbox


@pytest.fixture
def tenant(org, user):
    t = make_lease(org, user, phone=TENANT_PHONE)
    payments.register_settlement_account(
        org=org, bank_code="058", bank_name="GTB", account_number="0123456789", account_name="Obi", by=user
    )
    return t


def whatsapp(client, text, *, msg_id, wa_id=TENANT_PHONE[1:]):
    body = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": wa_id, "profile": {"name": "Chidi"}}],
                            "messages": [
                                {"from": wa_id, "id": msg_id, "type": "text", "text": {"body": text}}
                            ],
                        }
                    }
                ]
            }
        ]
    }
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(MockWhatsApp.SECRET, raw, hashlib.sha256).hexdigest()
    resp = client.post(
        reverse("whatsapp-webhook"), raw, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=sig
    )
    assert resp.status_code == 200


class FakeLlm:
    """Scripted model: returns the queued responses in order and records every request."""

    name = "fake"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(json.loads(json.dumps(kwargs, default=str)))
        return self.responses.pop(0)


def text_resp(text, stop="end_turn", **kw):
    return llm.LlmResponse(
        content=[{"type": "text", "text": text}],
        stop_reason=stop,
        model="claude-opus-5-5",
        text=text,
        input_tokens=1000,
        output_tokens=100,
        **kw,
    )


def tool_resp(name, args, call_id="toolu_1"):
    return llm.LlmResponse(
        content=[{"type": "tool_use", "id": call_id, "name": name, "input": args}],
        stop_reason="tool_use",
        model="claude-opus-5-5",
        tool_calls=[llm.ToolCall(call_id, name, args)],
        input_tokens=1000,
        output_tokens=50,
    )


# ---- End to end on WhatsApp (mock model) ---------------------------------------------------------


def test_whatsapp_question_is_answered_from_tools(client, tenant, _wa):
    whatsapp(client, "How much do I owe?", msg_id="wamid.1")
    reply = _wa[-1]["body"]
    assert reply.startswith("MOCK:") and "owed_now" in reply and "Obi Properties" in reply
    turns = list(AssistantTurn.objects.all())
    assert any("get_my_rent_summary" in t.tools for t in turns) and len(turns) >= 2


def test_payment_link_needs_yes_then_is_created(client, tenant, _wa):
    whatsapp(client, "send me link", msg_id="wamid.1")
    pending = PendingAction.objects.get()
    assert pending.status == "proposed" and "YES" in _wa[-1]["body"]
    assert PaymentLink.objects.count() == 0  # nothing happens before the yes
    whatsapp(client, "YES", msg_id="wamid.2")
    pending.refresh_from_db()
    link = PaymentLink.objects.get()
    assert pending.status == "executed" and f"/pay/{link.reference}" in _wa[-1]["body"]
    owed = sum(
        c.balance
        for c in Charge.objects.filter(
            tenant=tenant, due_date__lte=timezone.localdate(), status__in=Charge.OUTSTANDING
        )
    )
    assert link.amount == owed


def test_anything_but_yes_cancels(client, tenant, _wa):
    whatsapp(client, "send me link", msg_id="wamid.1")
    whatsapp(client, "no", msg_id="wamid.2")
    assert PendingAction.objects.get().status == "rejected" and "cancelled" in _wa[-1]["body"]
    whatsapp(client, "yes", msg_id="wamid.3")
    assert PaymentLink.objects.count() == 0


def test_expired_proposal_does_nothing(client, tenant, _wa):
    whatsapp(client, "send me link", msg_id="wamid.1")
    PendingAction.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
    whatsapp(client, "yes", msg_id="wamid.2")
    assert PaymentLink.objects.count() == 0 and "expired" in _wa[-1]["body"]


def test_emergency_escalates_to_landlord(client, tenant, org, _wa, _sms_outbox):
    org.phone_number = "+2348031110000"
    org.save()
    whatsapp(client, "Help, there is a fire in my flat", msg_id="wamid.1")
    esc = Escalation.objects.get()
    assert esc.reason == "emergency" and esc.organization == org
    assert "112" in _wa[-1]["body"] or any("112" in m["body"] for m in _wa)
    assert any(to == "+2348031110000" and "needs a person" in text for to, text in _sms_outbox)


def test_handoff_silences_assistant(client, tenant, org, user, _wa):
    whatsapp(client, "How much do I owe?", msg_id="wamid.1")
    convo = Contact.objects.get().conversations.get()
    messaging.take_over(convo, by=user)
    n = len(_wa)
    whatsapp(client, "hello?", msg_id="wamid.2")
    assert len(_wa) == n


# ---- Permissions and privacy ---------------------------------------------------------------------


def test_tenant_cannot_use_someone_elses_charges(org, user, tenant):
    other = make_lease(org, user, phone="+2348077777777", label="Flat 9")
    their_charge = Charge.objects.filter(tenant=other).first()
    p = (
        for_user(make_user(phone=TENANT_PHONE))
        if False
        else for_contact(messaging.get_contact(TENANT_PHONE.lstrip("+")))
    )
    ctx = SimpleNamespace(propose=lambda *a: pytest.fail("must not propose"))
    with pytest.raises(tools.ToolError):
        tools.create_my_payment_link(p, ctx, charge_ids=[str(their_charge.pk)], organization_id=None)
    assert {t.name for t in tools.for_principal(p)} >= {"get_my_rent_summary"}
    assert "list_arrears" not in {t.name for t in tools.for_principal(p)}


def test_staff_tools_follow_the_role(org, user, tenant):
    agent = make_user(phone="+2348031110021")
    invite(org=org, phone_number=agent.phone_number, role="agent", by=user)
    link_invites(agent)
    p = for_user(agent)
    with pytest.raises(tools.ToolError, match="role"):
        tools.list_arrears(p, None, organization_id=str(org.pk))
    assert (
        tools.find_tenant(p, None, organization_id=str(org.pk), query="Chidi")["tenants"][0]["name"]
        == "Chidi Okafor"
    )
    owner_view = tools.list_arrears(for_user(user), None, organization_id=str(org.pk))
    assert owner_view["tenants"][0]["tenant"] == "Chidi Okafor"
    stranger_org = create_organization(
        user=make_user(phone="+2348031110010"), name="Sade Homes", kind="landlord"
    )
    with pytest.raises(tools.ToolError, match="not a team member"):
        tools.list_arrears(for_user(user), None, organization_id=str(stranger_org.pk))


def test_all_tool_schemas_are_strict():
    for t in tools.TOOLS:
        s = t.schema()
        assert s["strict"] is True and s["input_schema"]["additionalProperties"] is False
        assert set(s["input_schema"]["required"]) == set(s["input_schema"]["properties"])


def test_output_filter():
    text = (
        "Call Grace on 0803 111 2233 or me on +2348031110000, email grace@example.com. "
        "Acct 0123456789. Pay https://x.y/pay/HSKAB12"
    )
    out, changed = guardrails.filter_output(text, allowed_phones=["+2348031110000"])
    assert changed and "0803 111 2233" not in out and "+2348031110000" in out
    assert "grace@example.com" not in out and "0123456789" not in out and "https://x.y/pay/HSKAB12" in out
    assert guardrails.filter_output("You owe ₦440,000 (RCT-000004).")[0] == "You owe ₦440,000 (RCT-000004)."


def test_yes_no_and_language():
    assert guardrails.is_yes("Yes!") and guardrails.is_yes("oya") and guardrails.is_yes("do am")
    assert not guardrails.is_yes("yes but only September") and guardrails.is_no("No o")
    assert guardrails.detect_language("Abeg how much I dey owe?") == "pcm"
    assert guardrails.detect_language("How much do I owe for this month?", "pcm") == "en"
    assert guardrails.detect_language("ok", "pcm") == "pcm"


# ---- Limits, refusals, errors --------------------------------------------------------------------


@override_settings(ASSISTANT_RATE_LIMIT="2/600")
def test_rate_limit(client, tenant, _wa):
    for i in range(3):
        whatsapp(client, f"how much do I owe {i}", msg_id=f"wamid.{i}")
    assert "faster than I can answer" in _wa[-1]["body"]


@override_settings(ASSISTANT_USER_DAILY_CAP_USD="0")
def test_budget_cap_hands_off(client, tenant, _wa):
    whatsapp(client, "How much do I owe?", msg_id="wamid.1")
    assert "person from the team" in _wa[-1]["body"] and Escalation.objects.get().reason == "limit"


def test_refusal_is_polite_and_escalated(monkeypatch, tenant):
    fake = FakeLlm(text_resp("", stop="refusal", refusal_category="cyber"))
    monkeypatch.setattr(llm, "client", lambda: fake)
    convo = messaging.open_conversation(messaging.get_contact(TENANT_PHONE.lstrip("+")))
    reply = services.handle_message(convo, for_contact(convo.contact), "something odd")
    assert reply.escalated and "can't help with that" in reply.text
    assert any("refusal" in t.flags and t.refusal_category == "cyber" for t in AssistantTurn.objects.all())


def test_llm_outage_gives_canned_reply(monkeypatch, tenant):
    class Down:
        def create(self, **kw):
            raise llm.LlmUnavailable("HTTP 529")

    monkeypatch.setattr(llm, "client", lambda: Down())
    convo = messaging.open_conversation(messaging.get_contact(TENANT_PHONE.lstrip("+")))
    reply = services.handle_message(convo, for_contact(convo.contact), "hello there friend")
    assert "trouble" in reply.text


def test_history_is_append_only_across_turns(monkeypatch, tenant):
    fake = FakeLlm(
        tool_resp("get_my_rent_summary", {}),
        text_resp("You owe ₦440,000."),
        text_resp("Your next payment is due on 1 November."),
    )
    monkeypatch.setattr(llm, "client", lambda: fake)
    convo = messaging.open_conversation(messaging.get_contact(TENANT_PHONE.lstrip("+")))
    p = for_contact(convo.contact)
    assert services.handle_message(convo, p, "How much do I owe?").text == "You owe ₦440,000."
    services.handle_message(convo, p, "And when is the next one due?")
    first_turn = fake.calls[1]["messages"]
    second = fake.calls[2]["messages"]
    assert second[: len(first_turn) + 1] == [
        *first_turn,
        {"role": "assistant", "content": [{"type": "text", "text": "You owe ₦440,000."}]},
    ]
    assert second[-1] == {"role": "user", "content": "And when is the next one due?"}
    assert fake.calls[0]["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert all(t["strict"] for t in fake.calls[0]["tools"])


# ---- Prospects, listings -------------------------------------------------------------------------


def test_prospect_enquiry_and_booking(monkeypatch, org, user):
    listing = Listing.objects.create(
        organization=org,
        title="3-bed flat, Palm Court",
        area="Lekki",
        address="12 Admiralty Way",
        bedrooms=3,
        rent_amount=450_000_000,
        status="published",
        published_at=timezone.now(),
    )
    start = timezone.now() + timedelta(days=2)
    slot = ViewingSlot.objects.create(listing=listing, starts_at=start, ends_at=start + timedelta(minutes=30))
    fake = FakeLlm(
        tool_resp("get_listing", {"listing_ref": listing.ref}),
        text_resp("It is ₦4,500,000 per year."),
        tool_resp(
            "request_viewing",
            {"listing_ref": listing.ref, "slot_id": str(slot.pk), "name": "Kemi"},
            "toolu_2",
        ),
        text_resp("I can book that for you. Reply YES to confirm."),
    )
    monkeypatch.setattr(llm, "client", lambda: fake)
    convo = messaging.open_conversation(messaging.get_contact("2348031119999", "Kemi"))
    p = for_contact(convo.contact)
    assert p.roles == {"prospect"}
    services.handle_message(convo, p, "Tell me about the Lekki flat")
    assert Lead.objects.get().phone_number == "+2348031119999"
    reply = services.handle_message(convo, p, "Book Saturday for me, my name is Kemi")
    assert reply.pending_action and reply.pending_action.tool == "request_viewing"
    done = services.handle_message(convo, p, "yes")
    assert "12 Admiralty Way" in done.text and Lead.objects.get().stage == "viewing_booked"


# ---- App and web chat ----------------------------------------------------------------------------


def test_app_chat_confirm_button_and_erase(api_client, tenant):
    me = make_user(phone=TENANT_PHONE, first="Chidi")
    from apps.accounts.signals import user_registered

    user_registered.send(sender=None, user=me)
    api_client.force_authenticate(me)
    resp = api_client.post(
        reverse("v1:assistant-messages"), {"text": "send me link", "channel": "app"}, format="json"
    )
    assert resp.status_code == 201
    action = resp.json()["pending_action"]
    assert action["tool"] == "create_my_payment_link"
    done = api_client.post(reverse("v1:assistant-action", args=[action["id"], "confirm"])).json()
    assert "/pay/HSK" in done["text"]
    history = api_client.get(reverse("v1:assistant-messages"), {"channel": "app"}).json()
    assert [m["direction"] for m in history["messages"]] == ["in", "out", "out"]
    assert api_client.delete(reverse("v1:assistant-messages")).status_code == 204
    assert api_client.get(reverse("v1:assistant-messages")).json()["messages"] == []
    stranger = make_user(phone="+2348055555555")
    api_client.force_authenticate(stranger)
    assert api_client.post(reverse("v1:assistant-action", args=[action["id"], "confirm"])).status_code == 404


def test_kb_seeded_and_searchable(org):
    assert KbArticle.objects.filter(organization=None).count() >= 24
    hits = services.tools.search_help(
        for_user(make_user(phone="+2348031110002")),
        SimpleNamespace(language="pcm", org_ids=[]),
        query="receipt",
    )
    assert hits["articles"] and hits["articles"][0]["language"] == "pcm"


def test_org_kb_articles_managed_by_owner(auth_client, org):
    url = f"/api/v1/orgs/{org.pk}/kb-articles/"
    resp = auth_client.post(
        url,
        {
            "slug": "how-to-pay",
            "title": "Paying Obi Properties",
            "body": "Pay by the link only.",
            "language": "en",
            "audience": ["tenant"],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    assert auth_client.get(url).json()[0]["title"] == "Paying Obi Properties"


# ---- The Claude request itself -------------------------------------------------------------------


def test_anthropic_request_shape(monkeypatch, settings):
    settings.ANTHROPIC_MODEL = "claude-opus-5-5"
    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            usage = SimpleNamespace(
                input_tokens=10,
                output_tokens=5,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
                iterations=None,
            )
            return SimpleNamespace(
                to_dict=lambda: {"content": [{"type": "text", "text": "hi"}]},
                usage=usage,
                stop_reason="end_turn",
                model="claude-opus-5-5",
                stop_details=None,
            )

    import anthropic

    monkeypatch.setattr(
        anthropic, "Anthropic", lambda **kw: SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))
    )
    resp = llm.AnthropicLlm().create(
        system=[{"type": "text", "text": "s"}],
        messages=[{"role": "user", "content": "x"}],
        tools=[tools.TOOLS[0].schema()],
        effort="medium",
        max_tokens=4096,
    )
    assert captured["model"] == "claude-opus-5-5" and captured["fallbacks"] == "default"
    assert captured["betas"] == ["server-side-fallback-2026-07-01"] and captured["cache_control"] == {
        "type": "ephemeral"
    }
    assert captured["output_config"] == {"effort": "medium"} and "thinking" not in captured
    assert resp.text == "hi" and resp.cost_usd > 0


def test_echoable_drops_unreplayable_blocks_before_fallback():
    content = [
        {"type": "thinking", "thinking": ""},
        {"type": "text", "text": "a"},
        {"type": "tool_use", "id": "1", "name": "x", "input": {}},
        {"type": "fallback"},
        {"type": "text", "text": "b"},
    ]
    assert llm.echoable(content) == [
        {"type": "text", "text": "a"},
        {"type": "fallback"},
        {"type": "text", "text": "b"},
    ]
    plain = [{"type": "thinking", "thinking": ""}, {"type": "text", "text": "x"}]
    assert llm.echoable(plain) == plain
