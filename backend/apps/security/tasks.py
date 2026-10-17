from celery import shared_task

from . import services


@shared_task(acks_late=True, soft_time_limit=60)
def fan_out(alert_id: str) -> dict:
    """Push + SMS to everyone who must hear about a new alert ("alerts" queue, high priority)."""
    return services.fan_out(alert_id)


@shared_task(soft_time_limit=50)
def housekeeping() -> dict:
    """Every minute: push receipts, SMS fallback for unconfirmed pushes, SMS delivery status."""
    return services.check_deliveries()
