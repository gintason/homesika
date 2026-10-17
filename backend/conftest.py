import pytest
from rest_framework.test import APIClient

LOGIN_PIN = "482915"


@pytest.fixture(autouse=True)
def _clear_cache():
    """Throttle counters live in the cache; isolate them per test."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _sms_outbox():
    from apps.notifications.sms import MockSms

    MockSms.outbox.clear()
    yield MockSms.outbox


@pytest.fixture(autouse=True)
def _push_outbox():
    from apps.notifications.push import MockPush

    MockPush.outbox.clear()
    MockPush.receipts_map.clear()
    yield MockPush.outbox


@pytest.fixture(autouse=True)
def _run_on_commit_immediately(monkeypatch):
    """Tests run inside a rolled-back transaction; run on_commit hooks inline (Celery is eager in tests)."""
    from django.db import transaction

    monkeypatch.setattr(transaction, "on_commit", lambda func, using=None, robust=False: func())


@pytest.fixture
def api_client():
    return APIClient()


def make_user(phone="+2348012345678", first="Ada", last="Obi", email=None, pin=LOGIN_PIN):
    from apps.accounts.models import User

    user = User.objects.create_user(
        phone_number=phone, first_name=first, last_name=last, email=email, is_phone_verified=True
    )
    if pin:
        user.set_login_pin(pin)
    return user


@pytest.fixture
def user(db):
    return make_user()


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user)
    return api_client


@pytest.fixture
def org(user):
    from apps.orgs.services import create_organization

    return create_organization(user=user, name="Obi Properties", kind="landlord")
