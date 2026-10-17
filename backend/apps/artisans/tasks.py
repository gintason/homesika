from celery import shared_task

from . import services


# The provider SDK sets no HTTP timeout: cap the task so a slow provider can't hold a worker. A check
# cut off here stays "processing" and housekeeping retries it.
@shared_task(soft_time_limit=90, time_limit=120)
def run_id_check(check_id: str) -> str:
    return services.run_id_check(check_id)


@shared_task(soft_time_limit=90, time_limit=120)
def run_address_check(check_id: str) -> str:
    return services.run_address_check(check_id)


@shared_task
def housekeeping() -> dict:
    return services.housekeeping()
