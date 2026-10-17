from django.conf import settings

from .base import DELIVERED, FAILED, PROCESSING, REJECTED, UNKNOWN, ProviderError, Result, VtuProvider
from .flutterwave import FlutterwaveBills
from .mock import MockVtu
from .vtung import VtuNg

_REGISTRY = {"vtung": VtuNg, "flutterwave": FlutterwaveBills, "mock": MockVtu}


def get(name: str) -> VtuProvider:
    return _REGISTRY[name]()


def enabled() -> list[str]:
    """Failover order, from BILLS_PROVIDERS (comma-separated)."""
    return [n.strip() for n in settings.BILLS_PROVIDERS.split(",") if n.strip() in _REGISTRY]


__all__ = [
    "DELIVERED",
    "FAILED",
    "PROCESSING",
    "REJECTED",
    "UNKNOWN",
    "ProviderError",
    "Result",
    "enabled",
    "get",
]
