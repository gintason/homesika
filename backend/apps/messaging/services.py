"""
WhatsApp conversations: inbound messages, sending, delivery status, opt-in/out, escalation and the
staff hand-off. The assistant plugs in through MESSAGING_INBOUND_HANDLER (an import path), so this
app doesn't depend on it.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.module_loading import import_string
from django.utils.translation import gettext as _t
from rest_framework import serializers, status

from apps.accounts.models import Consent, User
from apps.core import audit
from apps.core.exceptions import HomesikaAPIException

from . import whatsapp
from .models import Contact, Conversation, Escalation, Message

logger = logging.getLogger(__name__)
WINDOW = timedelta(hours=24)  # TODO(verify) Meta's customer-service window length
STOP_WORDS = {"stop", "unsubscribe", "stop all", "cancel messages"}
START_WORDS = {"start", "subscribe", "unstop"}


class OutsideWindow(HomesikaAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "This person last wrote more than 24 hours ago, so WhatsApp only allows an approved template. "
        "Send an SMS instead."
    )
    default_code = "whatsapp_window_closed"


def phone_from_wa_id(wa_id: str) -> str:
    return "+" + "".join(ch for ch in wa_id if ch.isdigit())


def wa_id_from_phone(phone_e164: str) -> str:
    return phone_e164.lstrip("+")


def get_contact(wa_id: str, name: str = "") -> Contact:
    phone = phone_from_wa_id(wa_id)
    contact, created = Contact.objects.get_or_create(
        wa_id=wa_id, defaults={"phone_number": phone, "name": name[:120]}
    )
    changed = []
    if name and contact.name != name[:120]:
        contact.name, changed = name[:120], [*changed, "name"]
    if contact.user_id is None:
        user = User.objects.filter(phone_number=phone).first()
        if user:
            contact.user, changed = user, [*changed, "user"]
    if changed:
        contact.save(update_fields=[*changed, "updated_at"])
    return contact


def link_user(user: User) -> None:
    """A new account: attach any WhatsApp contact with the same phone number."""
    Contact.objects.filter(phone_number=user.phone_number, user__isnull=True).update(user=user)


def open_conversation(contact: Contact) -> Conversation:
    convo = Conversation.objects.filter(contact=contact, channel="whatsapp").exclude(status="closed").first()
    if convo:
        return convo
    try:
        with transaction.atomic():
            return Conversation.objects.create(
                channel="whatsapp", contact=contact, user=contact.user, language=contact.language
            )
    except IntegrityError:
        return Conversation.objects.get(contact=contact, channel="whatsapp", status__in=["bot", "handoff"])


def within_window(convo: Conversation) -> bool:
    return bool(convo.last_inbound_at and timezone.now() - convo.last_inbound_at < WINDOW)


def _set_opt_in(contact: Contact, opted_in: bool) -> None:
    now = timezone.now()
    if opted_in:
        contact.opt_in, contact.opted_in_at = Contact.OptIn.OPTED_IN, now
    else:
        contact.opt_in, contact.opted_out_at = Contact.OptIn.OPTED_OUT, now
    contact.save(update_fields=["opt_in", "opted_in_at", "opted_out_at", "updated_at"])
    if contact.user_id:
        if opted_in:
            Consent.objects.create(
                user_id=contact.user_id, purpose=Consent.Purpose.WHATSAPP, version="whatsapp-inbound"
            )
        else:
            Consent.objects.filter(
                user_id=contact.user_id, purpose=Consent.Purpose.WHATSAPP, withdrawn_at__isnull=True
            ).update(withdrawn_at=now)


def set_user_opt_in(user: User, opted_in: bool) -> Contact:
    """From the app's settings screen."""
    contact = Contact.objects.filter(user=user).first() or get_contact(wa_id_from_phone(user.phone_number))
    _set_opt_in(contact, opted_in)
    return contact


def record_inbound(msg: whatsapp.InboundMessage) -> Message | None:
    """Store one inbound message exactly once. Returns None for a duplicate delivery."""
    if (
        not msg.provider_message_id
        or Message.objects.filter(provider_message_id=msg.provider_message_id).exists()
    ):
        return None
    contact = get_contact(msg.wa_id, msg.profile_name)
    convo = open_conversation(contact)
    now = timezone.now()
    try:
        with transaction.atomic():
            message = Message.objects.create(
                conversation=convo,
                direction=Message.Direction.INBOUND,
                sender=Message.Sender.PERSON,
                kind=msg.kind,
                body=msg.body[:4000],
                provider_message_id=msg.provider_message_id,
                status=Message.Status.RECEIVED,
            )
    except IntegrityError:
        return None  # a concurrent delivery of the same message won
    Contact.objects.filter(pk=contact.pk).update(last_inbound_at=now)
    Conversation.objects.filter(pk=convo.pk).update(last_inbound_at=now, last_message_at=now)

    word = msg.body.strip().lower()
    if word in STOP_WORDS:
        _set_opt_in(contact, False)
        send_text(
            convo,
            _t("You won't get reminders or receipts on WhatsApp any more. Reply START to turn them back on."),
            sender="system",
            force=True,
        )
        return message
    if word in START_WORDS or contact.opt_in == Contact.OptIn.UNKNOWN:
        # Writing to us first counts as opting in to service messages.
        # TODO(verify) against Meta's opt-in policy.
        _set_opt_in(contact, True)
        if word in START_WORDS:
            send_text(
                convo,
                _t("WhatsApp reminders and receipts are on. Reply STOP any time to turn them off."),
                sender="system",
                force=True,
            )
            return message
    transaction.on_commit(lambda: _dispatch_inbound(message.pk))
    return message


def _dispatch_inbound(message_id) -> None:
    from .tasks import handle_inbound

    handle_inbound.delay(str(message_id))


def handle_inbound_message(message: Message) -> None:
    """Called by the Celery task: hand the message to the assistant unless a person has taken over."""
    convo = message.conversation
    if convo.status == Conversation.Status.HANDOFF:
        logger.info("Conversation %s is with a person; assistant stays silent", convo.pk)
        return
    if message.kind not in ("text", "interactive", "button"):
        send_text(
            convo,
            _t("Sorry, I can only read text messages for now. Please type your question."),
            sender="system",
        )
        return
    handler = getattr(settings, "MESSAGING_INBOUND_HANDLER", "")
    if handler:
        import_string(handler)(message)


def send_text(
    convo: Conversation, body: str, *, sender: str = "assistant", sent_by=None, force: bool = False
) -> Message:
    """Queue a free-form WhatsApp text. Only allowed inside the 24-hour window (force: our replies to a
    message that just arrived, which are inside the window by definition)."""
    if not force and not within_window(convo):
        raise OutsideWindow()
    message = Message.objects.create(
        conversation=convo,
        direction=Message.Direction.OUTBOUND,
        sender=sender,
        body=body[:4096],
        status=Message.Status.QUEUED,
        sent_by=sent_by,
    )
    Conversation.objects.filter(pk=convo.pk).update(last_message_at=timezone.now())
    transaction.on_commit(lambda: _dispatch_send(message.pk))
    return message


def send_template(
    contact: Contact, *, name: str, language: str, params: list[str], body: str, notification=None
) -> Message:
    convo = open_conversation(contact)
    message = Message.objects.create(
        conversation=convo,
        direction=Message.Direction.OUTBOUND,
        sender=Message.Sender.SYSTEM,
        kind="template",
        template_name=name,
        body=body[:4096],
        status=Message.Status.QUEUED,
        notification=notification,
    )
    transaction.on_commit(lambda: _dispatch_send(message.pk, template=(name, language, params)))
    return message


def _dispatch_send(message_id, template=None) -> None:
    from .tasks import send_message

    send_message.delay(str(message_id), list(template) if template else None)


def apply_status(update: whatsapp.StatusUpdate) -> None:
    order = ["queued", "sent", "delivered", "read"]
    message = (
        Message.objects.select_related("notification")
        .filter(provider_message_id=update.provider_message_id)
        .first()
    )
    if message is None:
        return
    if update.status == "failed":
        if message.status != Message.Status.FAILED:
            message.status, message.error = Message.Status.FAILED, update.error[:255]
            message.save(update_fields=["status", "error", "updated_at"])
            _sms_fallback(message)
        return
    if update.status in order and (
        message.status not in order or order.index(update.status) > order.index(message.status)
    ):
        message.status = update.status
        message.save(update_fields=["status", "updated_at"])


def _sms_fallback(message: Message) -> None:
    """A reminder or receipt that WhatsApp couldn't deliver goes out by SMS instead (once)."""
    note = message.notification
    if note is None or note.kind.endswith(":fallback"):
        return
    from apps.notifications.services import notify_sms

    notify_sms(
        to=note.to,
        body=note.body,
        kind=f"{note.kind}:fallback",
        user=note.user,
        organization=note.organization,
    )


# ---- Escalation and hand-off ---------------------------------------------------------------------


def escalate(convo: Conversation, *, reason: str, summary: str = "", organization=None) -> Escalation:
    org = organization or convo.organization
    if org and convo.organization_id is None:
        Conversation.objects.filter(pk=convo.pk).update(organization=org)
        convo.organization = org
    existing = convo.escalations.exclude(status=Escalation.Status.RESOLVED).first()
    if existing:
        return existing
    esc = Escalation.objects.create(
        conversation=convo, organization=org, reason=reason, summary=summary[:500]
    )
    _alert_staff(esc)
    return esc


def _alert_staff(esc: Escalation) -> None:
    from apps.notifications.services import notify_sms
    from apps.orgs.models import Membership

    who = esc.conversation.contact.name if esc.conversation.contact_id else ""
    body = _t(
        "Homesika: a conversation needs a person (%(reason)s). %(who)s %(summary)s Open the inbox: %(url)s"
    ) % {
        "reason": esc.get_reason_display(),
        "who": who,
        "summary": esc.summary[:120],
        "url": f"{settings.WEB_APP_URL.rstrip('/')}/inbox",
    }
    phones: set[str] = set()
    if esc.organization_id:
        phones |= set(
            Membership.objects.filter(
                organization_id=esc.organization_id, status="active", role__in=["owner", "manager"]
            ).values_list("user__phone_number", flat=True)
        )
        if esc.organization.phone_number:
            phones.add(esc.organization.phone_number)
    elif settings.SUPPORT_PHONE:
        phones.add(settings.SUPPORT_PHONE)
    for phone in sorted(p for p in phones if p):
        notify_sms(to=phone, body=body, kind="escalation", organization=esc.organization)


def take_over(convo: Conversation, *, by, request=None) -> Conversation:
    Conversation.objects.filter(pk=convo.pk).update(
        status=Conversation.Status.HANDOFF, handoff_by=by, handoff_at=timezone.now()
    )
    convo.escalations.filter(status=Escalation.Status.OPEN).update(
        status=Escalation.Status.ASSIGNED, assigned_to=by
    )
    audit.record(
        "conversation.taken_over", actor=by, organization=convo.organization, obj=convo, request=request
    )
    convo.refresh_from_db()
    return convo


def release(convo: Conversation, *, by, request=None) -> Conversation:
    """Back to the assistant; open escalations are marked resolved."""
    Conversation.objects.filter(pk=convo.pk).update(
        status=Conversation.Status.BOT, handoff_by=None, handoff_at=None
    )
    convo.escalations.exclude(status=Escalation.Status.RESOLVED).update(
        status=Escalation.Status.RESOLVED, resolved_at=timezone.now()
    )
    audit.record(
        "conversation.released", actor=by, organization=convo.organization, obj=convo, request=request
    )
    convo.refresh_from_db()
    return convo


def staff_reply(convo: Conversation, *, body: str, by) -> Message:
    if convo.channel != Conversation.Channel.WHATSAPP:
        raise serializers.ValidationError({"body": ["Replies can only be sent to WhatsApp conversations."]})
    if convo.status != Conversation.Status.HANDOFF:
        take_over(convo, by=by)
    return send_text(convo, body, sender="staff", sent_by=by)
