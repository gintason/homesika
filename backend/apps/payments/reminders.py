"""
Rent reminders by SMS: 7 days and 1 day before, on the due day, then 3/7/14/30 days late.
One message per tenant per stage covers all their charges at that stage, with a pay link when the
landlord has a payout account. ReminderLog makes a rerun of the daily job harmless.
"""

import logging
from collections import defaultdict
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _t

from apps.core.money import format_money
from apps.leasing.models import Charge
from apps.notifications.services import notify_sms

from . import services
from .models import ReminderLog, SettlementAccount

logger = logging.getLogger(__name__)

# Days relative to the due date -> stage name. Negative = before the due date.
STAGES = {-7: "before_7", -1: "before_1", 0: "due", 3: "late_3", 7: "late_7", 14: "late_14", 30: "late_30"}


def _message(stage: str, *, first_name, amount, due: date, org_name, link_url) -> str:
    due_str = f"{due:%d %b}"
    if stage.startswith("before"):
        lead = _t("Hi %(name)s, your rent of %(amount)s is due on %(due)s.")
    elif stage == "due":
        lead = _t("Hi %(name)s, your rent of %(amount)s is due today.")
    else:
        lead = _t("Hi %(name)s, your rent of %(amount)s was due on %(due)s and is now overdue.")
    text = lead % {"name": first_name, "amount": amount, "due": due_str}
    tail = (
        (_t(" Pay: %(url)s") % {"url": link_url}) if link_url else _t(" Please contact your landlord to pay.")
    )
    return f"{text}{tail} - {org_name}"


def send_due_reminders(today: date | None = None) -> dict:
    today = today or timezone.localdate()
    due_dates = {today - timedelta(days=offset): stage for offset, stage in STAGES.items()}
    charges = (
        Charge.objects.filter(
            status__in=Charge.OUTSTANDING,
            due_date__in=list(due_dates),
            organization__rent_reminders_enabled=True,
            organization__is_active=True,
            lease__status="active",
        )
        .select_related("organization", "tenant")
        .order_by("due_date")
    )
    groups: dict[tuple, list[Charge]] = defaultdict(list)
    for charge in charges:
        stage = due_dates[charge.due_date]
        if not ReminderLog.objects.filter(charge=charge, stage=stage).exists():
            groups[(charge.tenant_id, stage)].append(charge)

    payout_orgs = set(
        SettlementAccount.objects.filter(status=SettlementAccount.Status.ACTIVE).values_list(
            "organization_id", flat=True
        )
    )
    sent = 0
    for (_tenant_id, stage), items in groups.items():
        tenant, org = items[0].tenant, items[0].organization
        try:
            with transaction.atomic():
                link = None
                if org.pk in payout_orgs:
                    link = services.create_link(
                        org=org, tenant=tenant, charge_ids=[c.pk for c in items], description=_t("Rent")
                    )
                ReminderLog.objects.bulk_create(
                    [ReminderLog(charge=c, stage=stage, payment_link=link) for c in items]
                )
                amount = format_money(sum(c.balance for c in items), items[0].currency, plain=True)
                notify_sms(
                    to=tenant.phone_number,
                    kind="rent_reminder",
                    user=tenant.user,
                    organization=org,
                    body=_message(
                        stage,
                        first_name=tenant.full_name.split(" ")[0],
                        amount=amount,
                        due=items[0].due_date,
                        org_name=org.name,
                        link_url=services.pay_url(link) if link else "",
                    ),
                )
                sent += 1
        except IntegrityError:
            logger.info("Reminder %s for tenant %s already sent", stage, tenant.pk)
    return {"sent": sent}
