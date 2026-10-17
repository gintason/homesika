from celery import shared_task

from . import services


@shared_task
def housekeeping() -> dict:
    return services.housekeeping()
