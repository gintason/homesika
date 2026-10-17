"""
Data retention (NDPA: keep personal data no longer than needed). Runs daily (`core-retention`).

* Sent notifications (SMS/WhatsApp/push text: gate codes, pay links) are deleted after
  NOTIFICATION_RETENTION_DAYS. Alert delivery rows keep their timings; only the link to the text goes.
* Panic alert locations are erased ALERT_LOCATION_RETENTION_DAYS after the alert closed. The alert,
  its incident log and delivery record stay as the estate's safety record.
* Visitors' phone numbers on gate passes are erased GATE_PASS_RETENTION_DAYS after the pass ended
  (the name stays in the gate log).
* Push devices switched off for PUSH_DEVICE_RETENTION_DAYS are deleted.
Artisan ID photos have their own rule (apps.artisans, 90 days after the check passes).
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone


def purge(now=None) -> dict:
    from apps.estates.models import GatePass
    from apps.notifications.models import Notification, PushDevice
    from apps.security.models import PanicAlert

    now = now or timezone.now()
    days = lambda n: now - timedelta(days=n)  # noqa: E731
    notifications, _ = Notification.objects.filter(
        created_at__lt=days(settings.NOTIFICATION_RETENTION_DAYS)
    ).delete()
    locations = (
        PanicAlert.objects.filter(closed_at__lt=days(settings.ALERT_LOCATION_RETENTION_DAYS))
        .exclude(location="")
        .update(location="", updated_at=now)
    )
    visitor_phones = (
        GatePass.objects.filter(valid_to__lt=days(settings.GATE_PASS_RETENTION_DAYS))
        .exclude(visitor_phone="")
        .update(visitor_phone="", updated_at=now)
    )
    devices, _ = PushDevice.objects.filter(
        is_active=False, updated_at__lt=days(settings.PUSH_DEVICE_RETENTION_DAYS)
    ).delete()
    return {
        "notifications": notifications,
        "alert_locations": locations,
        "visitor_phones": visitor_phones,
        "push_devices": devices,
    }
