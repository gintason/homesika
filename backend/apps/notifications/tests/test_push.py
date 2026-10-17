import pytest
from django.urls import reverse

from apps.notifications.models import PushDevice
from apps.notifications.services import push_or_sms
from conftest import make_user

pytestmark = pytest.mark.django_db
TOKEN = "ExponentPushToken[abcdefghijklmnop]"


def test_register_and_remove_device(auth_client, user):
    url = reverse("v1:push-devices")
    assert (
        auth_client.post(url, {"token": "nonsense", "platform": "android"}, format="json").status_code == 400
    )
    assert auth_client.post(url, {"token": TOKEN, "platform": "android"}, format="json").status_code == 204
    assert auth_client.post(url, {"token": TOKEN, "platform": "android"}, format="json").status_code == 204
    assert PushDevice.objects.filter(user=user, is_active=True).count() == 1
    # the same phone signed in by someone else moves to them
    other = make_user(phone="+2348031119999", first="Other")
    auth_client.force_authenticate(other)
    auth_client.post(url, {"token": TOKEN, "platform": "ios"}, format="json")
    assert PushDevice.objects.get(token=TOKEN).user == other
    auth_client.delete(url, {"token": TOKEN}, format="json")
    assert not PushDevice.objects.exists()


def test_push_or_sms(user, _sms_outbox, _push_outbox):
    other = make_user(phone="+2348031119999", first="Other")
    PushDevice.objects.create(user=user, token=TOKEN, platform="android")
    out = push_or_sms(
        recipients=[(user, user.phone_number), (other, other.phone_number), (None, "+2348031118888")],
        title="Hi",
        body="There",
        kind="test",
    )
    assert out == {"push": 1, "sms": 2}
    assert {p for p, _t in _sms_outbox} == {"+2348031119999", "+2348031118888"}
    out = push_or_sms(
        recipients=[(user, user.phone_number)], title="Hi", body="There", kind="test", sms="always"
    )
    assert out == {"push": 1, "sms": 1}
