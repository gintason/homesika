from celery import shared_task

from . import services


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def fulfil_order(self, order_id: str) -> str:
    return services.fulfil(order_id).status


@shared_task
def requery_order(order_id: str) -> str:
    return services.requery(order_id).status


@shared_task
def refund_order(order_id: str) -> str:
    return services.refund(order_id).status


@shared_task
def reconcile_bills() -> dict:
    return services.reconcile()


@shared_task
def process_provider_event(event_id: str) -> str:
    from django.utils import timezone

    from .models import Order, ProviderEvent

    event = ProviderEvent.objects.get(pk=event_id)
    order = Order.objects.filter(provider_reference=event.reference).first()
    if order is not None:
        services.requery(order.pk)  # never trust the webhook body: ask the provider
    ProviderEvent.objects.filter(pk=event.pk).update(processed_at=timezone.now())
    return order.status if order else "no_order"
