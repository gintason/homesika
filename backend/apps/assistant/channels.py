"""WhatsApp -> assistant. Set as MESSAGING_INBOUND_HANDLER; runs in a Celery worker."""

from apps.messaging import services as messaging

from . import principal, services


def handle_whatsapp(message) -> None:
    convo = message.conversation
    reply = services.handle_message(convo, principal.for_contact(convo.contact), message.body)
    if reply.text:
        messaging.send_text(convo, reply.text, sender="assistant", force=True)
