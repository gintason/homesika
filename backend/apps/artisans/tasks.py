from celery import shared_task

from . import services


@shared_task
def run_id_check(check_id: str) -> str:
    return services.run_id_check(check_id)


@shared_task
def run_address_check(check_id: str) -> str:
    return services.run_address_check(check_id)


@shared_task
def housekeeping() -> dict:
    return services.housekeeping()
