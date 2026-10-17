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
