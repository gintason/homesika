from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core import retention
from apps.estates import services as estates
from apps.estates.models import GatePass
from apps.notifications.models import Notification, PushDevice
from apps.security.models import PanicAlert
from conftest import make_user

pytestmark = pytest.mark.django_db


def test_purge_old_personal_data(org, user):
    now = timezone.now()
    estate = estates.create_estate(org=org, by=user, name="Palm Grove", address="1 Palm Ave")
    estates.add_houses(estate, ["A1"])
    resident = estates.approve(
        estates.join(user=make_user(phone="+2348031112222"), code=estate.join_code, house="A1"), by=user
    )
    old_note = Notification.objects.create(
        channel="sms", kind="gate_pass", to="+2348035551234", body="code 123456"
    )
    new_note = Notification.objects.create(
        channel="sms", kind="gate_pass", to="+2348035551234", body="code 654321"
    )
    Notification.objects.filter(pk=old_note.pk).update(created_at=now - timedelta(days=200))
    closed = PanicAlert.objects.create(
        estate=estate,
        raised_by=resident.user,
        member=resident,
        status="resolved",
        location='{"lat": 6.4, "lng": 3.4}',
        closed_at=now - timedelta(days=100),
    )
    open_alert = PanicAlert.objects.create(
        estate=estate, raised_by=resident.user, member=resident, location='{"lat": 6.4, "lng": 3.4}'
    )
    gp = estates.create_pass(member=resident, visitor_name="Tolu", visitor_phone="08035551234")
    GatePass.objects.filter(pk=gp.pk).update(
        valid_from=now - timedelta(days=100), valid_to=now - timedelta(days=95)
    )
    dead = PushDevice.objects.create(
        user=resident.user, token="ExponentPushToken[old-device-000]", platform="android", is_active=False
    )
    PushDevice.objects.filter(pk=dead.pk).update(updated_at=now - timedelta(days=100))
    live = PushDevice.objects.create(
        user=resident.user, token="ExponentPushToken[live-device-00]", platform="ios"
    )

    out = retention.purge()

    assert out == {"notifications": 1, "alert_locations": 1, "visitor_phones": 1, "push_devices": 1}
    assert (
        not Notification.objects.filter(pk=old_note.pk).exists()
        and Notification.objects.filter(pk=new_note.pk).exists()
    )
    closed.refresh_from_db()
    open_alert.refresh_from_db()
    assert closed.location == "" and open_alert.location != ""
    gp.refresh_from_db()
    assert gp.visitor_phone == "" and gp.visitor_name == "Tolu"
    assert list(PushDevice.objects.all()) == [live]
    assert retention.purge() == {
        "notifications": 0,
        "alert_locations": 0,
        "visitor_phones": 0,
        "push_devices": 0,
    }


def test_deploy_checks_for_keys_and_cors(settings):
    from apps.core import checks

    assert checks.encryption_keys(None) == []
    settings.FIELD_ENCRYPTION_KEYS = []
    assert [e.id for e in checks.encryption_keys(None)] == ["homesika.E002"]
    settings.FIELD_ENCRYPTION_KEYS = ["c2hvcnQ="]  # 5 bytes
    assert [e.id for e in checks.encryption_keys(None)] == ["homesika.E002"]
    settings.CORS_ALLOWED_ORIGINS = []
    assert [w.id for w in checks.cors_origins(None)] == ["homesika.W003"]
    settings.CORS_ALLOWED_ORIGINS = ["https://app.example"]
    assert checks.cors_origins(None) == []
