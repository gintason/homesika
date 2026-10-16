from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from . import sms
from .models import Notification


@shared_task(bind=True, max_retries=5, retry_backoff=True, retry_backoff_max=600)
def send_notification(self, notification_id: str) -> str:
    note = Notification.objects.get(pk=notification_id)
    if note.status == Notification.Status.SENT:
        return note.status
    note.attempts += 1
    try:
        if note.channel == Notification.Channel.SMS:
            note.provider_ref = sms.send_sms(note.to, note.body)
        elif note.channel == Notification.Channel.EMAIL:
            send_mail(note.subject or "Homesika", note.body, settings.DEFAULT_FROM_EMAIL, [note.to])
        note.status, note.sent_at, note.error = Notification.Status.SENT, timezone.now(), ""
        note.save(update_fields=["status", "sent_at", "error", "provider_ref", "attempts", "updated_at"])
    except (sms.SmsError, OSError) as exc:
        note.error = str(exc)[:255]
        final = self.request.retries >= self.max_retries
        note.status = Notification.Status.FAILED if final else Notification.Status.QUEUED
        note.save(update_fields=["status", "error", "attempts", "updated_at"])
        if not final:
            raise self.retry(exc=exc) from exc
    return note.status
