from celery import shared_task

from . import services


@shared_task
def daily() -> dict:
    """Raise dues, send dues reminders, expire old gate passes (once a day, morning)."""
    return {
        "dues_created": services.generate_dues(),
        **services.send_dues_reminders(),
        "passes_expired": services.expire_passes(),
    }
