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
