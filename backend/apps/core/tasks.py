from celery import shared_task

from . import retention


@shared_task
def purge_old_data() -> dict:
    return retention.purge()
