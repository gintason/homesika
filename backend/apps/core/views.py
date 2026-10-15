"""Health checks for load balancers and uptime monitors (no auth, no personal data)."""

import logging

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@never_cache
@require_GET
def live(request):
    """The process is up and serving."""
    return JsonResponse({"status": "ok"})


@never_cache
@require_GET
def ready(request):
    """Dependencies are reachable: database and Redis/cache. 503 if any is down."""
    checks = {}
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report, never raise, from a health check
        logger.error("Readiness: database unavailable: %s", type(exc).__name__)
        checks["database"] = "unavailable"
    try:
        cache.set("health:ping", "1", timeout=5)
        checks["cache"] = "ok" if cache.get("health:ping") == "1" else "unavailable"
    except Exception as exc:  # noqa: BLE001
        logger.error("Readiness: cache unavailable: %s", type(exc).__name__)
        checks["cache"] = "unavailable"
    healthy = all(v == "ok" for v in checks.values())
    return JsonResponse(
        {"status": "ok" if healthy else "degraded", "checks": checks}, status=200 if healthy else 503
    )
