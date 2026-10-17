from django.db import transaction

from .models import Notification


def notify_sms(*, to: str, body: str, kind: str, user=None, organization=None) -> Notification:
    """Record and queue an SMS; the Celery task sends it (with retries) after the transaction commits."""
    note = Notification.objects.create(
        channel=Notification.Channel.SMS, kind=kind, to=to, body=body, user=user, organization=organization
    )
    from .tasks import send_notification

    transaction.on_commit(lambda: send_notification.delay(str(note.pk)))
    return note


def notify(
    *, to: str, body: str, kind: str, user=None, organization=None, wa_params: list[str] | None = None
) -> Notification:
    """WhatsApp first, SMS otherwise. WhatsApp is used only when: it's enabled, an approved template is
    configured for this kind (WHATSAPP_TEMPLATES), and the person has opted in. `body` is the plain-text
    version (sent as the SMS, and as the fallback SMS if WhatsApp delivery fails)."""
    from django.conf import settings

    from apps.messaging import whatsapp

    template = (settings.WHATSAPP_TEMPLATES or {}).get(kind)
    if template and wa_params is not None and whatsapp.enabled():
        from apps.messaging.models import Contact
        from apps.messaging.services import send_template, wa_id_from_phone

        contact = Contact.objects.filter(wa_id=wa_id_from_phone(to), opt_in=Contact.OptIn.OPTED_IN).first()
        if contact:
            note = Notification.objects.create(
                channel=Notification.Channel.WHATSAPP,
                kind=kind,
                to=to,
                body=body,
                user=user,
                organization=organization,
            )
            send_template(
                contact,
                name=template["name"],
                language=template.get("language", "en"),
                params=[str(p) for p in wa_params],
                body=body,
                notification=note,
            )
            return note
    return notify_sms(to=to, body=body, kind=kind, user=user, organization=organization)


def push_or_sms(
    *, recipients, title: str, body: str, kind: str, data=None, sms: str = "fallback", organization=None
) -> dict:
    """Tell people by push where they have the app, and by SMS otherwise.

    recipients: iterable of (user or None, phone). sms: "fallback" (only those without a working push
    device), "always" (everyone also gets an SMS) or "never". Returns counts. Not for panic alerts,
    which track every delivery (apps.security)."""
    from . import push

    people = [(u, p) for u, p in recipients if u is not None or p]
    tokens = push.active_tokens({u.pk for u, _p in people if u is not None})
    messages, owners = [], []
    for u, phone in people:
        for token in tokens.get(getattr(u, "pk", None), []):
            messages.append(push.Push(token=token, title=title, body=body, data=data or {}))
            owners.append((u, phone))
    reached: set = set()
    dead: list[str] = []
    if messages:
        try:
            tickets = push.provider().send(messages)
        except push.PushError:
            tickets = [push.Ticket(False, error="unreachable")] * len(messages)
        for msg, (u, _p), t in zip(messages, owners, tickets, strict=False):
            if t.ok:
                reached.add(u.pk)
            elif t.error == "DeviceNotRegistered":
                dead.append(msg.token)
        push.deactivate(dead)
    sms_sent = 0
    if sms != "never":
        seen: set = set()
        for u, phone in people:
            if not phone or phone in seen:
                continue
            if sms == "fallback" and u is not None and u.pk in reached:
                continue
            seen.add(phone)
            notify_sms(to=phone, body=f"{title}: {body}"[:480], kind=kind, user=u, organization=organization)
            sms_sent += 1
    return {"push": len(reached), "sms": sms_sent}
