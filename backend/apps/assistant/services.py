"""
The assistant's single entry point for WhatsApp, app and web: handle_message(). Order of work:

1. guardrails in code (length, rate limit, cost caps);
2. a pending proposal is answered: yes -> our code runs it; anything else cancels it;
3. otherwise the model loop: Claude + strict tools, at most ASSISTANT_MAX_TOOL_ROUNDS rounds;
4. output filter, logging, and escalation on refusal or failure.

History is append-only per session: each model response is stored exactly as returned and replayed
unchanged on the next call.
"""

import json
import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.messaging import services as messaging
from apps.messaging.models import Conversation, Message

from . import guardrails, llm, prompts, tools
from .models import AssistantState, AssistantTurn, PendingAction
from .principal import Principal

logger = logging.getLogger(__name__)
SESSION_IDLE = timedelta(hours=12)
SESSION_MAX_ENTRIES = 60
PENDING_TTL = timedelta(minutes=15)

CANNED = {
    "too_long": {
        "en": "That message is too long for me. Please send a shorter question (under 2,000 characters).",
        "pcm": "Dis message too long for me. Abeg send short question (e no pass 2,000 letters).",
    },
    "rate": {
        "en": "You're sending messages faster than I can answer. Please wait a few minutes and try again.",
        "pcm": "You dey send message too fast. Abeg wait small, then try again.",
    },
    "budget": {
        "en": (
            "I can't answer more questions right now. I've asked a person from the team to reply to you here."
        ),
        "pcm": "I no fit answer more question now. I don tell person for the team make dem reply you here.",
    },
    "error": {
        "en": (
            "Sorry, I'm having trouble right now. Please try again in a few minutes, or "
            "reply HUMAN to reach a person."
        ),
        "pcm": (
            "Sorry, something no work well now. Abeg try again small time, or reply HUMAN "
            "make person answer you."
        ),
    },
    "refusal": {
        "en": (
            "Sorry, I can't help with that. I can help with your rent, payments, receipts, "
            "lease and listings, or connect you with a person."
        ),
        "pcm": (
            "Sorry, I no fit help with dat one. I fit help with your rent, payment, receipt, "
            "lease and house listing, or connect you with person."
        ),
    },
    "cancelled": {
        "en": "Okay, I've cancelled that. Nothing was done.",
        "pcm": "Okay, I don cancel am. Nothing happen.",
    },
    "expired": {
        "en": "That request expired, so nothing was done. Tell me again if you still want it.",
        "pcm": "Dat request don expire, nothing happen. Tell me again if you still want am.",
    },
    "failed": {
        "en": "I couldn't complete that: {error}",
        "pcm": "I no fit finish am: {error}",
    },
}

DONE = {
    "create_my_payment_link": {
        "en": (
            "Here is your payment link for ₦{amount} to {landlord}: {pay_url}\nYour receipt "
            "comes automatically after you pay."
        ),
        "pcm": (
            "See your payment link for ₦{amount} to {landlord}: {pay_url}\nReceipt go come "
            "by itself after you pay."
        ),
    },
    "send_payment_link": {
        "en": "Done. I sent {sent_to} a payment link for ₦{amount}.",
        "pcm": "E don go. I don send {sent_to} payment link for ₦{amount}.",
    },
    "request_viewing": {
        "en": "Your viewing is booked for {when}. Address: {address}. Contact: {contact}.",
        "pcm": "Your viewing don book for {when}. Address: {address}. Contact: {contact}.",
    },
}


@dataclass
class Reply:
    text: str
    pending_action: PendingAction | None = None
    escalated: bool = False


def _fmt_amount(value) -> str:
    try:
        n = float(value)
        return f"{n:,.0f}" if n == int(n) else f"{n:,.2f}"
    except (TypeError, ValueError):
        return str(value)


class Context:
    """What tool executors may use beyond the principal: proposing, escalating, remembering."""

    def __init__(self, convo: Conversation, principal: Principal, state: AssistantState):
        self.convo, self.principal, self.state = convo, principal, state
        self.language = convo.language
        self.channel_source = "whatsapp" if convo.channel == "whatsapp" else "app"
        self.org_ids = [
            *principal.memberships.keys(),
            *[str(t.organization_id) for t in principal.tenant_profiles],
        ]
        self.proposed: PendingAction | None = None
        self.escalation = None

    def propose(self, tool: str, arguments: dict, summary: str) -> dict:
        PendingAction.objects.filter(conversation=self.convo, status="proposed").update(
            status="expired", decided_at=timezone.now()
        )
        self.proposed = PendingAction.objects.create(
            conversation=self.convo,
            tool=tool,
            arguments=arguments,
            summary=summary[:300],
            expires_at=timezone.now() + PENDING_TTL,
        )
        return {
            "status": "needs_confirmation",
            "action_id": str(self.proposed.pk),
            "summary": self.proposed.summary,
        }

    def remember(self, **values) -> None:
        self.state.context = {**self.state.context, **values}
        AssistantState.objects.filter(pk=self.state.pk).update(context=self.state.context)

    def routing_org(self):
        from apps.orgs.models import Organization

        p = self.principal
        if p.tenant_profiles:
            return p.tenant_profiles[0].organization
        last = self.state.context.get("last_listing_org")
        if last and not p.memberships:
            return Organization.objects.filter(pk=last).first()
        return None  # staff and unknown people go to Homesika support

    def escalate(self, reason: str, summary: str):
        self.escalation = messaging.escalate(
            self.convo, reason=reason, summary=summary, organization=self.routing_org()
        )
        return self.escalation


def _state(convo: Conversation) -> AssistantState:
    state, _ = AssistantState.objects.get_or_create(conversation=convo)
    if state.history and (
        timezone.now() - state.updated_at > SESSION_IDLE or len(state.history) > SESSION_MAX_ENTRIES
    ):
        state.session += 1
        state.history = []
        state.session_started_at = timezone.now()
        state.save(update_fields=["session", "history", "session_started_at", "updated_at"])
    return state


def _append(state: AssistantState, *entries: dict) -> None:
    state.history = [*state.history, *entries]
    AssistantState.objects.filter(pk=state.pk).update(history=state.history, updated_at=timezone.now())


def _log(convo, principal: Principal, resp: llm.LlmResponse | None, *, flags=(), tools_used=(), error=""):
    org_id = (
        principal.tenant_profiles[0].organization_id
        if principal.tenant_profiles
        else (next(iter(principal.memberships), None))
    )
    AssistantTurn.objects.create(
        conversation=convo,
        user=principal.user,
        organization_id=org_id,
        sender=principal.sender_key,
        model=resp.model if resp else settings.ANTHROPIC_MODEL,
        stop_reason=resp.stop_reason if resp else "",
        input_tokens=resp.input_tokens if resp else 0,
        output_tokens=resp.output_tokens if resp else 0,
        cache_read_tokens=resp.cache_read_tokens if resp else 0,
        cache_write_tokens=resp.cache_write_tokens if resp else 0,
        cost_usd=resp.cost_usd if resp else 0,
        latency_ms=resp.latency_ms if resp else 0,
        tools=list(tools_used),
        flags=list(flags),
        refusal_category=(resp.refusal_category or "") if resp else "",
        fallback_used=resp.fallback_used if resp else False,
        error=error[:200],
    )


def _allowed_contacts(principal: Principal) -> tuple[list, list]:
    phones = [principal.phone, settings.SUPPORT_PHONE]
    for t in principal.tenant_profiles:
        phones.append(t.organization.phone_number)
    for m in principal.memberships.values():
        phones.append(m.organization.phone_number)
    emails = [getattr(principal.user, "email", "") or "", "support@homesika.com"]
    return phones, emails


def _resolve_pending(convo, principal, state, text, lang) -> Reply | None:
    pending = PendingAction.objects.filter(conversation=convo, status="proposed").first()
    if pending is None:
        return None
    now = timezone.now()
    if pending.expires_at <= now:
        pending.status, pending.decided_at = "expired", now
        pending.save(update_fields=["status", "decided_at", "updated_at"])
        if guardrails.is_yes(text):
            return _record_direct(state, text, CANNED["expired"][lang])
        return None
    if not guardrails.is_yes(text):
        pending.status, pending.decided_at = "rejected", now
        pending.save(update_fields=["status", "decided_at", "updated_at"])
        if guardrails.is_no(text):
            return _record_direct(state, text, CANNED["cancelled"][lang])
        return None  # a new question: the proposal is dropped and the model answers it
    ctx = Context(convo, principal, state)
    try:
        with transaction.atomic():
            result = tools.RUNNERS[pending.tool](principal, ctx, **pending.arguments)
    except Exception as exc:  # ToolError or a service error (e.g. slot just taken)
        msg = str(getattr(exc, "detail", "") or exc) or "please try again"
        pending.status, pending.result, pending.decided_at = "failed", {"error": msg[:300]}, now
        pending.save(update_fields=["status", "result", "decided_at", "updated_at"])
        return _record_direct(state, text, CANNED["failed"][lang].format(error=msg[:200]))
    pending.status, pending.result, pending.decided_at = "executed", result, now
    pending.save(update_fields=["status", "result", "decided_at", "updated_at"])
    values = {k: (_fmt_amount(v) if k == "amount" else v) for k, v in result.items()}
    return _record_direct(state, text, DONE[pending.tool][lang].format(**values))


def _record_direct(state, user_text: str, reply: str) -> Reply:
    """A reply our code produced (confirmations, limits). Kept in the model's "
    "history so it has the context."""
    _append(
        state,
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": [{"type": "text", "text": reply}]},
    )
    return Reply(text=reply)


def handle_message(convo: Conversation, principal: Principal, text: str) -> Reply:
    lang = guardrails.detect_language(text, convo.language)
    if lang != convo.language:
        Conversation.objects.filter(pk=convo.pk).update(language=lang)
        convo.language = lang
    if len(text) > guardrails.MAX_INPUT_CHARS:
        return Reply(text=CANNED["too_long"][lang])
    if guardrails.rate_limited(principal.sender_key):
        return Reply(text=CANNED["rate"][lang])

    state = _state(convo)
    direct = _resolve_pending(convo, principal, state, text, lang)
    if direct:
        return direct

    org_id = (
        principal.tenant_profiles[0].organization_id
        if principal.tenant_profiles
        else next(iter(principal.memberships), None)
    )
    cap = guardrails.over_budget(sender_key=principal.sender_key, organization_id=org_id)
    if cap:
        ctx = Context(convo, principal, state)
        ctx.escalate("limit", f"Assistant {cap} spending cap reached")
        _log(convo, principal, None, flags=[f"cap:{cap}"])
        return Reply(text=CANNED["budget"][lang], escalated=True)
    return _run_model(convo, principal, state, text, lang)


def _run_model(convo, principal, state, text, lang) -> Reply:
    ctx = Context(convo, principal, state)
    available = tools.for_principal(principal)
    tool_schemas = [t.schema() for t in available]
    names = {t.name for t in available}
    system = [
        {"type": "text", "text": prompts.SYSTEM, "cache_control": {"type": "ephemeral"}},
        {
            "type": "text",
            "text": prompts.context_block(
                principal, channel=convo.channel, language=lang, today=str(timezone.localdate())
            ),
        },
    ]
    new_entries: list[dict] = [{"role": "user", "content": text}]
    client = llm.client()
    used: list[str] = []
    flags: list[str] = []
    texts: list[str] = []  # text from every round (e.g. "Call 112 now" before a tool call) is shown
    resp = None
    for _round in range(settings.ASSISTANT_MAX_TOOL_ROUNDS):
        try:
            resp = client.create(
                system=system,
                messages=[*state.history, *new_entries],
                tools=tool_schemas,
                effort=settings.ASSISTANT_EFFORT_CHAT,
                max_tokens=settings.ASSISTANT_MAX_TOKENS,
            )
        except llm.LlmUnavailable as exc:
            _log(convo, principal, None, flags=["llm_unavailable"], tools_used=used, error=str(exc))
            return Reply(text=CANNED["error"][lang])
        new_entries.append({"role": "assistant", "content": resp.content})
        if resp.text.strip() and resp.stop_reason != "refusal":
            texts.append(resp.text.strip())
        if resp.stop_reason == "refusal":
            flags.append("refusal")
            _log(convo, principal, resp, flags=flags, tools_used=used)
            _append(state, *new_entries)
            ctx.escalate("refusal", f"Assistant declined ({resp.refusal_category or 'unspecified'})")
            return Reply(text=CANNED["refusal"][lang], escalated=True)
        if resp.stop_reason != "tool_use" or not resp.tool_calls:
            break
        results = []
        for call in resp.tool_calls:
            used.append(call.name)
            results.append(_execute(call, names, principal, ctx))
        _log(convo, principal, resp, tools_used=[c.name for c in resp.tool_calls])
        new_entries.append({"role": "user", "content": results})
    else:
        flags.append("max_rounds")

    _append(state, *new_entries)
    reply = "\n\n".join(texts) or CANNED["error"][lang]
    phones, emails = _allowed_contacts(principal)
    reply, changed = guardrails.filter_output(reply, allowed_phones=phones, allowed_emails=emails)
    if changed:
        flags.append("output_filtered")
        logger.warning("Assistant output filtered in conversation %s", convo.pk)
    if resp and resp.stop_reason != "tool_use":
        _log(convo, principal, resp, flags=flags)
    elif flags:
        _log(convo, principal, None, flags=flags, tools_used=used)
    if ctx.proposed and lang == "en" and "YES" not in reply.upper():
        reply += "\n\nReply YES to confirm."
    elif ctx.proposed and lang == "pcm" and "YES" not in reply.upper():
        reply += "\n\nReply YES make I do am."
    return Reply(text=reply, pending_action=ctx.proposed, escalated=ctx.escalation is not None)


def _execute(call: llm.ToolCall, names: set, principal: Principal, ctx: Context) -> dict:
    if call.name not in names:
        return {"type": "tool_result", "tool_use_id": call.id, "is_error": True, "content": "Unknown tool."}
    tool = tools.BY_NAME[call.name]
    try:
        with transaction.atomic():
            result = tool.handler(principal, ctx, **call.input)
    except tools.ToolError as exc:
        return {"type": "tool_result", "tool_use_id": call.id, "is_error": True, "content": str(exc)}
    except TypeError as exc:
        logger.warning("Tool %s got unexpected input: %s", call.name, exc)
        return {
            "type": "tool_result",
            "tool_use_id": call.id,
            "is_error": True,
            "content": "Invalid input for this tool.",
        }
    except Exception:
        logger.exception("Tool %s failed", call.name)
        return {
            "type": "tool_result",
            "tool_use_id": call.id,
            "is_error": True,
            "content": "This tool failed; try another way or offer a person.",
        }
    return {
        "type": "tool_result",
        "tool_use_id": call.id,
        "content": json.dumps(result, ensure_ascii=False, default=str),
    }


# ---- Conversations for the app and web chat ---------------------------------------------------------------


def app_conversation(user, channel: str) -> Conversation:
    convo = (
        Conversation.objects.filter(user=user, channel=channel)
        .exclude(status="closed")
        .order_by("-created_at")
        .first()
    )
    return convo or Conversation.objects.create(channel=channel, user=user, language="en")


def chat(user, *, channel: str, text: str) -> tuple[Conversation, Reply]:
    from .principal import for_user

    convo = app_conversation(user, channel)
    now = timezone.now()
    Message.objects.create(
        conversation=convo, direction="in", sender="person", body=text[:4000], status="received"
    )
    Conversation.objects.filter(pk=convo.pk).update(last_inbound_at=now, last_message_at=now)
    reply = handle_message(convo, for_user(user), text)
    Message.objects.create(
        conversation=convo, direction="out", sender="assistant", body=reply.text, status="delivered"
    )
    return convo, reply


def confirm_action(user, action_id, *, confirm: bool) -> Reply:
    """App/web buttons: the same path as a typed YES / NO."""
    from .principal import for_user

    pending = PendingAction.objects.select_related("conversation").get(pk=action_id, conversation__user=user)
    convo = pending.conversation
    if pending.status != "proposed":
        return Reply(text="")
    text = "yes" if confirm else "no"
    reply = handle_message(convo, for_user(user), text)
    Message.objects.create(
        conversation=convo, direction="out", sender="assistant", body=reply.text, status="delivered"
    )
    return reply
