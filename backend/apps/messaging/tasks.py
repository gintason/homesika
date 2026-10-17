import logging

from celery import shared_task
from django.utils import timezone

from . import services, whatsapp
from .models import Message

logger = logging.getLogger(__name__)


@shared_task
def process_webhook(payload: dict) -> dict:
    batch = whatsapp.parse_webhook(payload)
    stored = sum(1 for m in batch.messages if services.record_inbound(m))
    for update in batch.statuses:
        services.apply_status(update)
    return {"messages": stored, "statuses": len(batch.statuses)}


@shared_task
def handle_inbound(message_id: str) -> None:
    message = Message.objects.select_related("conversation__contact").get(pk=message_id)
    services.handle_inbound_message(message)


@shared_task(bind=True, max_retries=5, retry_backoff=True, retry_backoff_max=300)
def send_message(self, message_id: str, template: list | None = None) -> str:
    message = Message.objects.select_related("conversation__contact").get(pk=message_id)
    if message.status != Message.Status.QUEUED:
        return message.status
    contact = message.conversation.contact
    if contact is None:
        return message.status  # app/web conversations are read in the app; nothing to send
    if contact.opt_in == contact.OptIn.OPTED_OUT and message.sender != Message.Sender.SYSTEM:
        message.status, message.error = Message.Status.FAILED, "opted out"
        message.save(update_fields=["status", "error", "updated_at"])
        return message.status
    try:
        gw = whatsapp.provider()
        if template:
            name, language, params = template
            ref = gw.send_template(contact.wa_id, name, language, params)
        else:
            ref = gw.send_text(contact.wa_id, message.body)
    except whatsapp.WhatsAppError as exc:
        final = not exc.retryable or self.request.retries >= self.max_retries
        message.error = str(exc)[:255]
        if final:
            message.status = Message.Status.FAILED
            message.save(update_fields=["status", "error", "updated_at"])
            services._sms_fallback(message)
            return message.status
        message.save(update_fields=["error", "updated_at"])
        raise self.retry(exc=exc) from exc
    message.status, message.provider_message_id, message.error = Message.Status.SENT, ref or None, ""
    message.save(update_fields=["status", "provider_message_id", "error", "updated_at"])
    if message.notification_id:
        message.notification.__class__.objects.filter(pk=message.notification_id).update(
            status="sent", provider_ref=ref, sent_at=timezone.now()
        )
    return message.status
