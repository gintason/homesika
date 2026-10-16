from datetime import timedelta

import pytest

from apps.leasing.models import Charge
from apps.payments import reminders, services
from apps.payments.models import PaymentLink, ReminderLog
from apps.payments.tests.test_payments import make_lease

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant(org, user):
    return make_lease(org, user)


def first_charge(tenant):
    return Charge.objects.filter(tenant=tenant).order_by("due_date").first()


def test_reminder_stages_and_no_duplicates(org, user, tenant, _sms_outbox):
    services.register_settlement_account(
        org=org, bank_code="058", bank_name="GTB", account_number="0123456789", account_name="Obi", by=user
    )
    charge = first_charge(tenant)
    due = charge.due_date

    assert reminders.send_due_reminders(today=due - timedelta(days=7)) == {"sent": 1}
    to, text = _sms_outbox[-1]
    assert to == tenant.phone_number and "is due on" in text and "NGN 100,000.00" in text
    assert "/pay/HSK" in text and text.endswith("- Obi Properties")
    assert PaymentLink.objects.count() == 1

    # Rerunning the same day sends nothing new.
    assert reminders.send_due_reminders(today=due - timedelta(days=7)) == {"sent": 0}
    # Days with no stage send nothing.
    assert reminders.send_due_reminders(today=due - timedelta(days=5)) == {"sent": 0}

    reminders.send_due_reminders(today=due)
    assert "due today" in _sms_outbox[-1][1]
    reminders.send_due_reminders(today=due + timedelta(days=3))
    assert "overdue" in _sms_outbox[-1][1]
    assert set(ReminderLog.objects.values_list("stage", flat=True)) == {"before_7", "due", "late_3"}


def test_no_reminder_for_paid_charges_or_when_disabled(org, user, tenant, _sms_outbox):
    charge = first_charge(tenant)
    Charge.objects.filter(pk=charge.pk).update(amount_paid=charge.amount, status="paid")
    assert reminders.send_due_reminders(today=charge.due_date) == {"sent": 0}

    second = Charge.objects.filter(tenant=tenant).order_by("due_date")[1]
    org.rent_reminders_enabled = False
    org.save()
    assert reminders.send_due_reminders(today=second.due_date) == {"sent": 0}


def test_reminder_without_payout_account_has_no_link(org, tenant, _sms_outbox):
    charge = first_charge(tenant)
    reminders.send_due_reminders(today=charge.due_date - timedelta(days=1))
    assert "contact your landlord" in _sms_outbox[-1][1]
    assert PaymentLink.objects.count() == 0
