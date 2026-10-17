"""
The evaluation scenarios of docs/ASSISTANT.md §6, built exactly (names, phones, amounts, receipt
numbers, listing refs). Everything runs at a frozen "now": 2026-10-15 10:00 Lagos.
"""

import contextlib
from datetime import date, datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.utils import timezone

LAGOS = ZoneInfo("Africa/Lagos")
NOW = datetime(2026, 10, 15, 10, 0, tzinfo=LAGOS)
N = 100  # kobo per naira


@contextlib.contextmanager
def frozen_now(at: datetime = NOW):
    with mock.patch("django.utils.timezone.now", return_value=at.astimezone(ZoneInfo("UTC"))):
        yield


def at(y, m, d, hh=10, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=LAGOS)


class Built:
    """Handles to what a scenario created, for the runner and the tests."""

    def __init__(self):
        self.users = {}
        self.orgs = {}
        self.tenants = {}
        self.listings = {}


def _user(b: Built, key, phone, first, last):
    from apps.accounts.models import User

    u = User.objects.create_user(phone_number=phone, first_name=first, last_name=last, is_phone_verified=True)
    b.users[key] = u
    return u


def _org(b: Built, key, name, owner, phone, payout: bool):
    from apps.orgs.services import create_organization
    from apps.payments.models import SettlementAccount

    org = create_organization(user=owner, name=name, kind="landlord")
    org.phone_number = phone
    org.save(update_fields=["phone_number"])
    if payout:
        SettlementAccount.objects.create(
            organization=org,
            gateway="mock",
            bank_code="058",
            bank_name="GTBank",
            account_number="0123456789",
            account_last4="6789",
            account_name=name,
            subaccount_code="MOCK_SUB_6789",
            status="active",
        )
    b.orgs[key] = org
    return org


def _lease(org, user, unit, *, name, phone, start, end, rent, freq, service=0):
    from apps.leasing import services as leasing
    from apps.leasing.models import Lease

    tenant = leasing.create_tenant(org=org, by=None, full_name=name, phone_number=phone)
    if user is not None:
        tenant.user = user
        tenant.save(update_fields=["user"])
    lease = Lease.objects.create(
        organization=org,
        unit=unit,
        tenant=tenant,
        start_date=start,
        end_date=end,
        rent_amount=rent * N,
        rent_frequency=freq,
        service_charge_amount=service * N,
    )
    leasing.activate_lease(lease, by=None)
    return tenant


def _pay(org, tenant, *, amount, when, channel, receipt, charges_paid):
    """A payment allocated to the given (charge, amount) pairs, with a fixed receipt number."""
    from apps.leasing.models import Charge
    from apps.payments.models import Allocation, Payment, Receipt

    gateway = "manual" if channel in ("cash", "bank_transfer") else "mock"
    p = Payment.objects.create(
        organization=org,
        tenant=tenant,
        gateway=gateway,
        gateway_reference=f"EVAL-{receipt}",
        channel=channel,
        amount=amount * N,
        currency="NGN",
        paid_at=when,
    )
    for charge, part in charges_paid:
        Allocation.objects.create(payment=p, charge=charge, amount=part * N)
        Charge.objects.filter(pk=charge.pk).update(amount_paid=charge.amount_paid + part * N)
        charge.refresh_from_db()
        charge.refresh_status()
        charge.save(update_fields=["status"])
    Receipt.objects.create(payment=p, organization=org, number=receipt)
    return p


def _charges(tenant, y, m):
    from apps.leasing.models import Charge

    return list(Charge.objects.filter(tenant=tenant, due_date__year=y, due_date__month=m).order_by("kind"))


def build_all() -> Built:
    """Every §6 scenario lives in one world (they share Obi Properties), so any scenario name works."""
    from apps.listings.models import Lead, Listing, Viewing, ViewingSlot
    from apps.orgs.services import invite, link_invites
    from apps.payments.models import ReceiptCounter
    from apps.properties.models import Property, Unit

    b = Built()
    with frozen_now():
        emeka = _user(b, "landlord", "+2348031110000", "Emeka", "Obi")
        sade = _user(b, "sade", "+2348031110010", "Sade", "Martins")
        obi = _org(b, "obi", "Obi Properties", emeka, "+2348031110000", payout=True)
        sade_org = _org(b, "sade", "Sade Homes", sade, "+2348031110010", payout=False)

        palm = Property.objects.create(
            organization=obi, name="Palm Court", address="12 Admiralty Way, Lekki, Lagos"
        )
        allen = Property.objects.create(
            organization=obi, name="Allen Plaza", address="Allen Avenue, Ikeja, Lagos"
        )
        akoka = Property.objects.create(
            organization=sade_org, name="Akoka Lodge", address="Akoka, Yaba, Lagos"
        )
        units = {
            label: Unit.objects.create(property=prop, label=label)
            for prop, label in [
                (palm, "Flat 1A"),
                (palm, "Flat 2B"),
                (palm, "Flat 3C"),
                (palm, "Flat 4D"),
                (allen, "Shop 4"),
                (allen, "Shop 5"),
                (akoka, "Room 3"),
            ]
        }

        chidi_u = _user(b, "chidi", "+2348031110001", "Chidi", "Okafor")
        amina_u = _user(b, "amina", "+2348031110002", "Amina", "Bello")
        tunde_u = _user(b, "tunde", "+2348031110003", "Tunde", "Adeyemi")

        chidi = _lease(
            obi,
            chidi_u,
            units["Flat 2B"],
            name="Chidi Okafor",
            phone="+2348031110001",
            start=date(2026, 6, 1),
            end=date(2027, 5, 31),
            rent=250_000,
            freq="monthly",
            service=20_000,
        )
        amina = _lease(
            obi,
            amina_u,
            units["Flat 1A"],
            name="Amina Bello",
            phone="+2348031110002",
            start=date(2026, 3, 1),
            end=date(2027, 2, 28),
            rent=3_000_000,
            freq="annual",
        )
        grace = _lease(
            obi,
            None,
            units["Flat 3C"],
            name="Grace Eze",
            phone="+2348031110004",
            start=date(2026, 10, 1),
            end=date(2027, 9, 30),
            rent=400_000,
            freq="monthly",
        )
        tunde_obi = _lease(
            obi,
            tunde_u,
            units["Shop 4"],
            name="Tunde Adeyemi",
            phone="+2348031110003",
            start=date(2026, 10, 1),
            end=date(2027, 9, 30),
            rent=150_000,
            freq="monthly",
        )
        musa = _lease(
            obi,
            None,
            units["Shop 5"],
            name="Musa Ibrahim",
            phone="+2348031110005",
            start=date(2026, 10, 1),
            end=date(2027, 9, 30),
            rent=150_000,
            freq="monthly",
        )
        tunde_sade = _lease(
            sade_org,
            tunde_u,
            units["Room 3"],
            name="Tunde Adeyemi",
            phone="+2348031110003",
            start=date(2026, 11, 1),
            end=date(2027, 10, 31),
            rent=300_000,
            freq="quarterly",
        )
        b.tenants.update(
            chidi=chidi, amina=amina, grace=grace, tunde_obi=tunde_obi, musa=musa, tunde_sade=tunde_sade
        )

        for i, (month, day, channel) in enumerate(
            [(6, 1, "bank_transfer"), (7, 2, "card"), (8, 1, "card")], start=1
        ):
            pairs = [(c, c.amount // N) for c in _charges(chidi, 2026, month)]
            _pay(
                obi,
                chidi,
                amount=270_000,
                when=at(2026, month, day),
                channel=channel,
                receipt=f"RCT-00000{i}",
                charges_paid=pairs,
            )
        oct_rent = next(c for c in _charges(chidi, 2026, 10) if c.kind == "rent")
        _pay(
            obi,
            chidi,
            amount=100_000,
            when=at(2026, 10, 5),
            channel="cash",
            receipt="RCT-000004",
            charges_paid=[(oct_rent, 100_000)],
        )
        _pay(
            obi,
            amina,
            amount=3_000_000,
            when=at(2026, 3, 1),
            channel="bank_transfer",
            receipt="RCT-000005",
            charges_paid=[(c, c.amount // N) for c in _charges(amina, 2026, 3)],
        )
        _pay(
            obi,
            grace,
            amount=400_000,
            when=at(2026, 10, 1),
            channel="card",
            receipt="RCT-000006",
            charges_paid=[(c, c.amount // N) for c in _charges(grace, 2026, 10)],
        )
        _pay(
            obi,
            musa,
            amount=75_000,
            when=at(2026, 10, 3),
            channel="bank_transfer",
            receipt="RCT-000007",
            charges_paid=[(_charges(musa, 2026, 10)[0], 75_000)],
        )
        ReceiptCounter.objects.update_or_create(organization=obi, defaults={"last": 7})

        # Bills: Chidi's meter and one earlier electricity purchase; sample data/TV plans.
        from apps.bills import catalogue
        from apps.bills.models import Biller, Order, Plan
        from apps.bills.models import ReceiptCounter as BillCounter

        Unit.objects.filter(pk=units["Flat 2B"].pk).update(meter_number="45123456789", disco="ikeja-electric")
        catalogue.load_samples()
        ikeja = Biller.objects.get(category="electricity", code="ikeja-electric")
        Order.objects.create(
            user=chidi_u,
            phone_number="+2348031110001",
            unit=units["Flat 2B"],
            category="electricity",
            biller=ikeja,
            plan=Plan.objects.get(biller=ikeja, code="prepaid"),
            customer_id="45123456789",
            customer_name="CHIDI OKAFOR",
            amount=5_000 * N,
            fee=100 * N,
            total=5_100 * N,
            status="delivered",
            gateway="mock",
            gateway_reference="BILEVAL1",
            paid_amount=5_100 * N,
            paid_at=at(2026, 10, 10),
            delivered_at=at(2026, 10, 10),
            expires_at=at(2026, 10, 10, 11),
            token="1234-5678-9012-3456-7890",  # noqa: S106 - a fake electricity token in test data
            units="42.5kWh",
            receipt_number="BIL-000001",
            provider="mock",
        )
        BillCounter.objects.update_or_create(key="bills", defaults={"last": 1})

        # Repairs: a Verified plumber; Chidi's tap (assigned, visit booked) and Grace's light (waiting).
        from apps.artisans.models import ArtisanProfile
        from apps.maintenance.models import Job, Ticket, TicketEvent

        kunle_u = _user(b, "artisan", "+2348031110030", "Kunle", "Adebayo")
        kunle = ArtisanProfile.objects.create(
            user=kunle_u,
            display_name="Kunle Plumbing Works",
            trades=["plumbing"],
            service_areas=["Lekki", "Ajah"],
            status="verified",
            verified_at=at(2026, 9, 1),
            rating_sum=24,
            rating_count=5,
            jobs_completed=12,
            data_consent_at=at(2026, 8, 20),
        )
        tap = Ticket.objects.create(
            reference="R0000A01",
            organization=obi,
            unit=units["Flat 2B"],
            lease=chidi.leases.get(),
            tenant=chidi,
            raised_by=chidi_u,
            category="plumbing",
            priority="urgent",
            title="Kitchen tap leaking",
            description="The kitchen tap drips all night and the sink cabinet is wet.",
            status="assigned",
            approved_by=emeka,
            approved_at=at(2026, 10, 13, 9),
        )
        Job.objects.create(
            ticket=tap,
            organization=obi,
            artisan=kunle,
            status="accepted",
            offered_by=emeka,
            offer_expires_at=at(2026, 10, 14, 9),
            responded_at=at(2026, 10, 13, 12),
            scheduled_for=at(2026, 10, 16, 14),
        )
        for kind, role, actor in [
            ("created", "tenant", chidi_u),
            ("approved", "staff", emeka),
            ("assigned", "staff", emeka),
            ("accepted", "artisan", kunle_u),
        ]:
            TicketEvent.objects.create(ticket=tap, kind=kind, actor_role=role, actor=actor)
        light = Ticket.objects.create(
            reference="R0000A02",
            organization=obi,
            unit=units["Flat 3C"],
            lease=grace.leases.get(),
            tenant=grace,
            category="electrical",
            priority="normal",
            title="Bathroom light not working",
            description="The bathroom light stopped working two days ago; the bulb was changed.",
        )
        TicketEvent.objects.create(ticket=light, kind="created", actor_role="tenant")

        for key, phone, first, last, role in [
            ("staff_manager", "+2348031110020", "Bola", "Adeyemi", "manager"),
            ("staff_agent", "+2348031110021", "Yusuf", "Sani", "agent"),
            ("staff_accountant", "+2348031110022", "Ngozi", "Okeke", "accountant"),
            ("staff_viewer", "+2348031110023", "Peter", "Udo", "viewer"),
        ]:
            u = _user(b, key, phone, first, last)
            invite(org=obi, phone_number=phone, role=role, by=emeka)
            link_invites(u)

        palm4d = Listing.objects.create(
            organization=obi,
            unit=units["Flat 4D"],
            ref="LST-PALM4D",
            title="Flat 4D, Palm Court",
            description="Spacious 3-bedroom flat in Palm Court, Lekki.",
            area="Lekki",
            city="Lagos",
            address="12 Admiralty Way, Lekki",
            bedrooms=3,
            bathrooms=3,
            rent_amount=4_500_000 * N,
            rent_period="year",
            status="published",
            published_at=at(2026, 10, 1),
            contact_phone="+2348031110000",
        )
        yaba = Listing.objects.create(
            organization=sade_org,
            ref="LST-YABA2B",
            title="2-bedroom flat, Herbert Macaulay Way",
            description="2-bedroom flat on Herbert Macaulay Way, Yaba.",
            area="Yaba",
            city="Lagos",
            address="Herbert Macaulay Way, Yaba",
            bedrooms=2,
            bathrooms=2,
            rent_amount=1_800_000 * N,
            rent_period="year",
            status="published",
            published_at=at(2026, 10, 2),
            contact_phone="+2348031110010",
        )
        ikeja = Listing.objects.create(
            organization=sade_org,
            ref="LST-IKJSC",
            title="Self-contain, Opebi",
            description="Self-contain room in Opebi, Ikeja.",
            area="Ikeja",
            city="Lagos",
            address="Opebi, Ikeja",
            bedrooms=1,
            bathrooms=1,
            rent_amount=650_000 * N,
            rent_period="year",
            status="published",
            published_at=at(2026, 10, 3),
            contact_phone="+2348031110010",
        )
        b.listings.update(palm4d=palm4d, yaba=yaba, ikeja=ikeja)

        def slot(listing, start):
            return ViewingSlot.objects.create(
                listing=listing, starts_at=start, ends_at=start + timezone.timedelta(minutes=30)
            )

        taken = slot(palm4d, at(2026, 10, 18, 11))
        slot(palm4d, at(2026, 10, 18, 14))
        slot(palm4d, at(2026, 10, 19, 10))
        slot(yaba, at(2026, 10, 17, 12))
        Lead.objects.create(
            organization=obi, listing=palm4d, name="Kemi Johnson", phone_number="+2348031119998", stage="new"
        )
        ifeanyi = Lead.objects.create(
            organization=obi,
            listing=palm4d,
            name="Ifeanyi Nwosu",
            phone_number="+2348031119997",
            stage="viewing_booked",
        )
        Viewing.objects.create(lead=ifeanyi, listing=palm4d, slot=taken)
        _estate(b)
    return b


def _estate(b: Built) -> None:
    """Phase 5: Palm Grove Estate, run by its residents' association (see docs/ASSISTANT.md §6)."""
    from apps.estates import services as estates
    from apps.estates.models import Announcement, DuesPlan
    from apps.orgs.models import Membership

    osaro = _user(b, "estate_admin", "+2348031110050", "Osaro", "Idahosa")
    assoc = _org(b, "palm_grove", "Palm Grove Residents Association", osaro, "+2348031110050", payout=True)
    assoc.kind = "estate"
    assoc.save(update_fields=["kind"])
    estate = estates.create_estate(
        org=assoc, by=osaro, name="Palm Grove Estate", address="Palm Grove Estate, Lekki Phase 1, Lagos"
    )
    estate.gate_instructions = "Show the code at Gate 1."
    estate.save(update_fields=["gate_instructions"])
    estates.add_houses(estate, ["A1", "A2", "B4"])
    guard = _user(b, "guard", "+2348031110051", "Musa", "Bello")
    Membership.objects.create(organization=assoc, user=guard, role="security")
    DuesPlan.objects.create(
        estate=estate, name="Security levy", amount=15_000 * N, start_date=date(2026, 1, 1)
    )
    for key, phone, first, last, house in (
        ("resident", "+2348031110040", "Adaeze", "Nwankwo", "A1"),
        ("femi", "+2348031110041", "Femi", "Lawal", "A2"),
    ):
        u = _user(b, key, phone, first, last)
        estates.approve(estates.join(user=u, code=estate.join_code, house=house), by=osaro)
    Announcement.objects.create(
        estate=estate,
        title="Water off on Saturday",
        body="No water supply on Saturday 18 October, 9am to 1pm, for pump repairs.",
        created_by=osaro,
    )
    b.orgs["estate"] = estate


PRINCIPAL_FOR_SCENARIO = {
    "tenant_overdue": ("phone", "+2348031110001"),
    "tenant_paid_up": ("phone", "+2348031110002"),
    "tenant_two_landlords": ("phone", "+2348031110003"),
    "landlord": ("phone", "+2348031110000"),
    "staff_manager": ("phone", "+2348031110020"),
    "staff_agent": ("phone", "+2348031110021"),
    "staff_accountant": ("phone", "+2348031110022"),
    "staff_viewer": ("phone", "+2348031110023"),
    "staff": ("phone", "+2348031110020"),
    "prospect": ("phone", "+2348031119999"),
    "resident": ("phone", "+2348031110040"),
}
