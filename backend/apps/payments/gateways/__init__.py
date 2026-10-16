"""Gateway registry. PAYMENT_GATEWAYS (comma-separated, in failover order) picks what is tried."""

from django.conf import settings

from .base import Checkout, CheckoutRequest, GatewayError, PaymentGateway, VerifiedTransaction, WebhookEvent
from .flutterwave import FlutterwaveGateway
from .mock import MockGateway
from .paystack import PaystackGateway

_REGISTRY = {"paystack": PaystackGateway, "flutterwave": FlutterwaveGateway, "mock": MockGateway}


def get(name: str) -> PaymentGateway:
    return _REGISTRY[name]()


def enabled() -> list[str]:
    return [g.strip() for g in settings.PAYMENT_GATEWAYS.split(",") if g.strip() in _REGISTRY]


__all__ = [
    "Checkout",
    "CheckoutRequest",
    "GatewayError",
    "PaymentGateway",
    "VerifiedTransaction",
    "WebhookEvent",
    "enabled",
    "get",
]
