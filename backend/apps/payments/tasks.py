from celery import shared_task
from django.utils import timezone

from . import gateways, reminders, services
from .models import GatewayEvent


@shared_task(bind=True, max_retries=6, retry_backoff=True, retry_backoff_max=900)
def process_gateway_event(self, event_id: str) -> str:
    event = GatewayEvent.objects.get(pk=event_id)
    if event.status in (GatewayEvent.Status.PROCESSED, GatewayEvent.Status.IGNORED):
        return event.status
    event.attempts += 1
    try:
        if event.reference.startswith("BIL"):  # bills settle to Homesika, handled by the bills app
            from apps.bills import services as bills

            payment = bills.confirm_payment(event.gateway, event.reference)
        else:
            payment = services.confirm(event.gateway, event.reference)
        event.status = GatewayEvent.Status.PROCESSED if payment else GatewayEvent.Status.IGNORED
        event.processed_at, event.last_error = timezone.now(), ""
        event.save(update_fields=["status", "processed_at", "last_error", "attempts", "updated_at"])
    except gateways.GatewayError as exc:
        event.last_error = str(exc)[:2000]
        event.save(update_fields=["last_error", "attempts", "updated_at"])
        raise self.retry(exc=exc) from exc
    return event.status


@shared_task
def reconcile_pending_links() -> dict:
    return services.check_pending_links()


@shared_task
def daily_reconciliation() -> dict:
    return services.daily_reconciliation()


@shared_task
def send_rent_reminders() -> dict:
    return reminders.send_due_reminders()
