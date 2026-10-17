"""
The assistant's tools (docs/ASSISTANT.md §3). Each tool is a strict JSON schema plus an executor that
runs with the *principal's* permissions, through the same services the REST API uses. Action tools never
act: they return a proposal, and our code runs it only after the person says yes.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.core.money import to_major, to_minor
from apps.leasing import services as leasing
from apps.leasing.models import Charge, Lease, TenantProfile
from apps.listings import services as listings
from apps.listings.models import Lead, Listing, Viewing
from apps.payments import services as payments
from apps.payments.models import Payment, SettlementAccount

from .principal import Principal

logger = logging.getLogger(__name__)


class ToolError(Exception):
    """Shown to the model as an error result; the message is safe to repeat to the user."""


@dataclass
class Tool:
    name: str
    description: str
    properties: dict
    roles: set  # which roles get the tool: tenant, landlord, staff, prospect ("*" = all)
    handler: Callable
    action: bool = False

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": self.properties,
                "required": list(self.properties),
                "additionalProperties": False,
            },
        }


def money(amount: int, currency: str = "NGN") -> str:
    return str(to_major(amount, currency))


def _today():
    return timezone.localdate()


# ---- Tenant tools ---------------------------------------------------------------------------------------


def _owed_now(qs):
    return qs.filter(status__in=Charge.OUTSTANDING, due_date__lte=_today())


def get_my_rent_summary(p: Principal, ctx) -> dict:
    out = []
    for org in p.landlord_orgs():
        charges = Charge.objects.filter(
            tenant__in=[t for t in p.tenant_profiles if t.organization_id == org.pk]
        ).exclude(status="void")
        now = list(_owed_now(charges).order_by("due_date"))
        upcoming = charges.filter(status__in=Charge.OUTSTANDING, due_date__gt=_today()).order_by("due_date")
        nxt = upcoming.first()
        next_amount = sum(c.balance for c in upcoming.filter(due_date=nxt.due_date)) if nxt else 0
        out.append(
            {
                "organization_id": str(org.pk),
                "landlord": org.name,
                "currency": org.currency,
                "owed_now": money(sum(c.balance for c in now), org.currency),
                "overdue_since": str(now[0].due_date) if now else None,
                "items_owed_now": [
                    {
                        "charge_id": str(c.pk),
                        "description": c.description or c.get_kind_display(),
                        "due_date": str(c.due_date),
                        "balance": money(c.balance, c.currency),
                        "status": c.status,
                    }
                    for c in now
                ],
                "next_due_date": str(nxt.due_date) if nxt else None,
                "next_due_amount": money(next_amount, org.currency) if nxt else None,
                "can_pay_online": SettlementAccount.objects.filter(
                    organization=org, status="active"
                ).exists(),
            }
        )
    return {"today": str(_today()), "landlords": out}


def list_my_charges(p: Principal, ctx, include_paid: bool) -> dict:
    qs = Charge.objects.filter(
        tenant__in=p.tenant_profiles, due_date__lte=_today() + timedelta(days=62)
    ).exclude(status="void")
    if not include_paid:
        qs = qs.filter(status__in=Charge.OUTSTANDING)
    rows = qs.select_related("organization", "unit").order_by("-due_date")[:24]
    return {
        "today": str(_today()),
        "charges": [
            {
                "charge_id": str(c.pk),
                "landlord": c.organization.name,
                "unit": c.unit.label,
                "description": c.description or c.get_kind_display(),
                "due_date": str(c.due_date),
                "amount": money(c.amount, c.currency),
                "paid": money(c.amount_paid, c.currency),
                "balance": money(c.balance, c.currency),
                "status": c.status,
                "overdue": c.is_overdue,
            }
            for c in sorted(rows, key=lambda c: c.due_date)
        ],
    }


def list_my_payments(p: Principal, ctx) -> dict:
    rows = (
        Payment.objects.filter(tenant__in=p.tenant_profiles, status="succeeded")
        .select_related("organization", "receipt", "payment_link")
        .order_by("-paid_at")[:10]
    )
    return {
        "payments": [
            {
                "date": str(timezone.localtime(x.paid_at).date()),
                "landlord": x.organization.name,
                "amount": money(x.amount, x.currency),
                "channel": x.channel or x.gateway,
                "receipt_number": getattr(getattr(x, "receipt", None), "number", None),
                "receipt_link": payments.receipt_url(x) if hasattr(x, "receipt") else None,
            }
            for x in rows
        ]
    }


def get_my_lease(p: Principal, ctx) -> dict:
    leases = Lease.objects.filter(tenant__in=p.tenant_profiles, status="active").select_related(
        "unit__property", "organization"
    )
    return {
        "leases": [
            {
                "lease_id": str(x.pk),
                "unit": x.unit.label,
                "property": x.unit.property.name,
                "address": x.unit.property.address,
                "landlord": x.organization.name,
                "landlord_phone": x.organization.phone_number,
                "meter_number": x.unit.meter_number,
                "disco": x.unit.disco,
                "rent": money(x.rent_amount, x.currency),
                "frequency": x.rent_frequency,
                "service_charge": money(x.service_charge_amount, x.currency),
                "start_date": str(x.start_date),
                "end_date": str(x.end_date),
            }
            for x in leases
        ]
    }


def _tenant_charges_for_link(p: Principal, charge_ids: list, organization_id) -> tuple:
    profiles = p.tenant_profiles
    if organization_id:
        profiles = [t for t in profiles if str(t.organization_id) == str(organization_id)]
        if not profiles:
            raise ToolError("That landlord isn't one of yours.")
    if charge_ids:
        try:
            charges = list(
                Charge.objects.filter(pk__in=charge_ids, tenant__in=profiles, status__in=Charge.OUTSTANDING)
            )
        except Exception as exc:  # malformed ids
            raise ToolError("I couldn't find those charges.") from exc
        if len(charges) != len(set(charge_ids)):
            raise ToolError("Some of those charges aren't yours or are already paid.")
    else:
        charges = list(_owed_now(Charge.objects.filter(tenant__in=profiles)))
        if not charges:
            raise ToolError(
                "Nothing is owed right now. Ask the person which upcoming charge they want to pay."
            )
    orgs = {c.organization_id for c in charges}
    if len(orgs) > 1:
        raise ToolError("These charges are for different landlords. Ask which landlord to pay first.")
    org_id = orgs.pop()
    if not SettlementAccount.objects.filter(organization_id=org_id, status="active").exists():
        raise ToolError(
            "This landlord hasn't set up online payment yet; the person should pay them directly."
        )
    return charges, org_id


def create_my_payment_link(p: Principal, ctx, charge_ids: list, organization_id) -> dict:
    charges, org_id = _tenant_charges_for_link(p, charge_ids, organization_id)
    total = sum(c.balance for c in charges)
    org = charges[0].organization
    return ctx.propose(
        "create_my_payment_link",
        {"charge_ids": [str(c.pk) for c in charges], "organization_id": str(org_id)},
        f"Create a payment link for {money(total, org.currency)} {org.currency} to {org.name} "
        f"({', '.join(c.description or c.get_kind_display() for c in charges)[:150]})",
    )


def run_create_my_payment_link(p: Principal, ctx, charge_ids: list, organization_id) -> dict:
    charges, _ = _tenant_charges_for_link(p, charge_ids, organization_id)
    link = payments.create_link(
        org=charges[0].organization, tenant=charges[0].tenant, charge_ids=[c.pk for c in charges], by=p.user
    )
    return {
        "pay_url": payments.pay_url(link),
        "amount": money(link.amount, link.currency),
        "landlord": link.organization.name,
    }


# ---- Staff tools ------------------------------------------------------------------------------------------


def _org(p: Principal, organization_id: str, capability: str):
    m = p.memberships.get(str(organization_id))
    if m is None:
        raise ToolError("You are not a team member of that organization.")
    if not p.can(organization_id, capability):
        raise ToolError(f"Your role ({m.role}) can't do this. Ask the owner.")
    return m.organization


def get_portfolio_summary(p: Principal, ctx, organization_id: str) -> dict:
    org = _org(p, organization_id, "org.view")
    s = leasing.org_summary(org)
    from apps.properties.models import Unit

    vacant = Unit.objects.filter(property__organization=org, status="vacant").select_related("property")
    return {
        "organization": org.name,
        "currency": org.currency,
        "units": s["units"],
        "occupied_units": s["occupied_units"],
        "vacant_units": [f"{u.label}, {u.property.name}" for u in vacant],
        "overdue_amount": money(s["overdue_amount"], org.currency)
        if p.can(organization_id, "payment.view")
        else "not visible to your role",
        "due_next_30_days": money(s["due_next_30_days"], org.currency)
        if p.can(organization_id, "payment.view")
        else "not visible to your role",
        "published_listings": Listing.objects.filter(organization=org, status="published").count(),
    }


def list_arrears(p: Principal, ctx, organization_id: str) -> dict:
    org = _org(p, organization_id, "payment.view")
    by_tenant: dict = {}
    for r in leasing.arrears_by_lease(org):
        t = by_tenant.setdefault(
            r["tenant_id"],
            {
                "tenant_id": str(r["tenant_id"]),
                "tenant": r["tenant__full_name"],
                "units": [],
                "owed": 0,
                "days_overdue": 0,
            },
        )
        t["units"].append(f"{r['unit__label']}, {r['unit__property__name']}")
        t["owed"] += r["owed"]
        t["days_overdue"] = max(t["days_overdue"], r["days_overdue"])
    rows = sorted(by_tenant.values(), key=lambda t: -t["days_overdue"])
    total = sum(t["owed"] for t in rows)
    for t in rows:
        t["owed"] = money(t["owed"], org.currency)
    return {
        "organization": org.name,
        "today": str(_today()),
        "total_overdue": money(total, org.currency),
        "tenants": rows,
    }


def find_tenant(p: Principal, ctx, organization_id: str, query: str) -> dict:
    org = _org(p, organization_id, "tenant.view")
    q = query.strip()
    qs = (
        TenantProfile.objects.filter(organization=org)
        .filter(
            Q(full_name__icontains=q)
            | Q(phone_number__icontains=q.lstrip("0"))
            | Q(leases__unit__label__icontains=q)
        )
        .distinct()[:5]
    )
    return {
        "tenants": [
            {
                "tenant_id": str(t.pk),
                "name": t.full_name,
                "phone": t.phone_number,
                "units": [
                    f"{x.unit.label}, {x.unit.property.name}"
                    for x in t.leases.filter(status="active").select_related("unit__property")
                ],
            }
            for t in qs
        ]
    }


def _tenant(org, tenant_id):
    try:
        return TenantProfile.objects.get(organization=org, pk=tenant_id)
    except Exception as exc:
        raise ToolError("No such tenant in this organization. Use find_tenant first.") from exc


def get_tenant_account(p: Principal, ctx, organization_id: str, tenant_id: str) -> dict:
    org = _org(p, organization_id, "payment.view")
    _org(p, organization_id, "tenant.view")
    t = _tenant(org, tenant_id)
    charges = Charge.objects.filter(tenant=t).exclude(status="void")
    now = list(_owed_now(charges).order_by("due_date"))
    pays = (
        Payment.objects.filter(tenant=t, status="succeeded")
        .select_related("receipt")
        .order_by("-paid_at")[:5]
    )
    return {
        "tenant": t.full_name,
        "owed_now": money(sum(c.balance for c in now), org.currency),
        "items_owed_now": [
            {
                "charge_id": str(c.pk),
                "description": c.description or c.get_kind_display(),
                "due_date": str(c.due_date),
                "balance": money(c.balance, c.currency),
            }
            for c in now
        ],
        "recent_payments": [
            {
                "date": str(timezone.localtime(x.paid_at).date()),
                "amount": money(x.amount, x.currency),
                "channel": x.channel or x.gateway,
                "receipt_number": getattr(getattr(x, "receipt", None), "number", None),
            }
            for x in pays
        ],
    }


def list_recent_payments(p: Principal, ctx, organization_id: str, days: int) -> dict:
    org = _org(p, organization_id, "payment.view")
    days = max(1, min(int(days), 90))
    rows = (
        Payment.objects.filter(
            organization=org, status="succeeded", paid_at__gte=timezone.now() - timedelta(days=days)
        )
        .select_related("tenant", "receipt")
        .order_by("-paid_at")[:30]
    )
    total = rows and sum(x.amount for x in rows)
    return {
        "days": days,
        "total": money(total or 0, org.currency),
        "payments": [
            {
                "date": str(timezone.localtime(x.paid_at).date()),
                "tenant": x.tenant.full_name,
                "amount": money(x.amount, x.currency),
                "channel": x.channel or x.gateway,
                "receipt_number": getattr(getattr(x, "receipt", None), "number", None),
            }
            for x in rows
        ],
    }


def _staff_link_charges(org, t, charge_ids):
    if charge_ids:
        charges = list(Charge.objects.filter(tenant=t, pk__in=charge_ids, status__in=Charge.OUTSTANDING))
        if len(charges) != len(set(charge_ids)):
            raise ToolError("Some of those charges aren't this tenant's or are already paid.")
    else:
        charges = list(_owed_now(Charge.objects.filter(tenant=t)))
        if not charges:
            raise ToolError("This tenant owes nothing right now.")
    if not SettlementAccount.objects.filter(organization=org, status="active").exists():
        raise ToolError("Add a payout bank account in the dashboard before sending payment links.")
    return charges


def send_payment_link(p: Principal, ctx, organization_id: str, tenant_id: str, charge_ids: list) -> dict:
    org = _org(p, organization_id, "payment.link")
    t = _tenant(org, tenant_id)
    charges = _staff_link_charges(org, t, charge_ids)
    total = sum(c.balance for c in charges)
    return ctx.propose(
        "send_payment_link",
        {"organization_id": str(org.pk), "tenant_id": str(t.pk), "charge_ids": [str(c.pk) for c in charges]},
        f"Send {t.full_name} a payment link for {money(total, org.currency)} "
        f"{org.currency} by WhatsApp or SMS",
    )


def run_send_payment_link(p: Principal, ctx, organization_id: str, tenant_id: str, charge_ids: list) -> dict:
    org = _org(p, organization_id, "payment.link")
    t = _tenant(org, tenant_id)
    charges = _staff_link_charges(org, t, charge_ids)
    link = payments.create_link(org=org, tenant=t, charge_ids=[c.pk for c in charges], by=p.user)
    from apps.notifications.services import notify

    amount = f"{org.currency} {to_major(link.amount, link.currency):,.2f}"
    notify(
        to=t.phone_number,
        kind="payment_link",
        user=t.user,
        organization=org,
        wa_params=[t.full_name.split(" ")[0], amount, org.name, payments.pay_url(link)],
        body=(
            f"Hi {t.full_name.split(' ')[0]}, {org.name} sent you a payment link for "
            f"{amount}: {payments.pay_url(link)}"
        ),
    )
    return {
        "sent_to": t.full_name,
        "amount": money(link.amount, link.currency),
        "pay_url": payments.pay_url(link),
    }


def list_leads(p: Principal, ctx, organization_id: str, stage) -> dict:
    org = _org(p, organization_id, "listing.view")
    qs = Lead.objects.filter(organization=org).select_related("listing")
    if stage:
        qs = qs.filter(stage=stage)
    return {
        "leads": [
            {
                "name": x.name,
                "phone": x.phone_number,
                "listing": x.listing.title if x.listing else None,
                "stage": x.stage,
                "created": str(timezone.localtime(x.created_at).date()),
            }
            for x in qs[:20]
        ]
    }


def list_viewings(p: Principal, ctx, organization_id: str, days: int) -> dict:
    org = _org(p, organization_id, "listing.view")
    days = max(1, min(int(days), 30))
    qs = Viewing.objects.filter(
        listing__organization=org,
        status="booked",
        slot__starts_at__gte=timezone.now(),
        slot__starts_at__lte=timezone.now() + timedelta(days=days),
    ).select_related("lead", "listing", "slot")
    return {
        "viewings": [
            {
                "when": timezone.localtime(v.slot.starts_at).strftime("%Y-%m-%d %H:%M"),
                "listing": v.listing.title,
                "name": v.lead.name,
                "phone": v.lead.phone_number,
            }
            for v in qs
        ]
    }


# ---- Common tools ------------------------------------------------------------------------------------------


def search_help(p: Principal, ctx, query: str) -> dict:
    from .kb import search

    return {"articles": search(query, roles=p.roles, language=ctx.language, organization_ids=ctx.org_ids)}


def search_listings(p: Principal, ctx, area, max_rent, bedrooms) -> dict:
    limit = None
    if max_rent:
        try:
            limit = to_minor(Decimal(str(max_rent).replace(",", "").replace("₦", "").strip()), "NGN")
        except (InvalidOperation, ValueError):
            limit = None
    rows = listings.search(area=area, max_rent=limit, bedrooms=bedrooms)
    return {
        "listings": [
            {
                "listing_ref": x.ref,
                "title": x.title,
                "area": x.area,
                "bedrooms": x.bedrooms,
                "price": money(x.rent_amount, x.currency),
                "period": x.rent_period,
                "landlord": x.organization.name,
            }
            for x in rows
        ]
    }


def _listing(ref) -> Listing:
    x = listings.published().select_related("organization").filter(ref__iexact=str(ref).strip()).first()
    if x is None:
        raise ToolError("No published listing with that reference.")
    return x


def get_listing(p: Principal, ctx, listing_ref: str) -> dict:
    x = _listing(listing_ref)
    if str(x.organization_id) not in p.memberships and p.phone:
        listings.capture_lead(
            listing=x, phone=p.phone, name=p.name, source=ctx.channel_source, contact=p.contact
        )
        ctx.remember(last_listing_org=str(x.organization_id))
    return {
        "listing_ref": x.ref,
        "title": x.title,
        "description": x.description[:1200],
        "features": x.features,
        "area": x.area,
        "city": x.city,
        "bedrooms": x.bedrooms,
        "bathrooms": x.bathrooms,
        "price": money(x.rent_amount, x.currency),
        "period": x.rent_period,
        "landlord": x.organization.name,
        "open_viewing_slots": [
            {"slot_id": str(s.pk), "starts": timezone.localtime(s.starts_at).strftime("%Y-%m-%d %H:%M")}
            for s in listings.open_slots(x)
        ],
    }


def _slot_ok(x: Listing, slot_id):
    if not any(str(s.pk) == str(slot_id) for s in listings.open_slots(x)):
        raise ToolError("That viewing time isn't available. Offer the open slots from get_listing.")


def request_viewing(p: Principal, ctx, listing_ref: str, slot_id: str, name: str) -> dict:
    x = _listing(listing_ref)
    _slot_ok(x, slot_id)
    if not name.strip():
        raise ToolError("Ask for the person's name first.")
    when = next(
        timezone.localtime(s.starts_at).strftime("%a %d %b %Y, %H:%M")
        for s in listings.open_slots(x)
        if str(s.pk) == str(slot_id)
    )
    return ctx.propose(
        "request_viewing",
        {"listing_ref": x.ref, "slot_id": str(slot_id), "name": name.strip()[:120]},
        f"Book a viewing of {x.title} on {when} for {name.strip()[:60]}",
    )


def run_request_viewing(p: Principal, ctx, listing_ref: str, slot_id: str, name: str) -> dict:
    x = _listing(listing_ref)
    v = listings.book_viewing(
        listing=x, slot_id=slot_id, phone=p.phone, name=name, source=ctx.channel_source, contact=p.contact
    )
    return {
        "booked": True,
        "when": timezone.localtime(v.slot.starts_at).strftime("%a %d %b %Y, %H:%M"),
        "address": x.address or x.area,
        "contact": x.contact_phone or x.organization.phone_number,
    }


def escalate_to_human(p: Principal, ctx, reason: str, summary: str) -> dict:
    esc = ctx.escalate(reason, summary)
    who = esc.organization.name if esc.organization_id else "Homesika support"
    return {
        "status": "escalated",
        "handled_by": who,
        "hours": settings.SUPPORT_HOURS,
        "reference": str(esc.pk)[:8].upper(),
    }


# ---- Bills (airtime, data, TV, electricity): pay-per-transaction by link ----------------------------------


def _biller(category: str, biller_code: str):
    from apps.bills.models import Biller

    b = Biller.objects.filter(category=category, code=biller_code, is_active=True).first()
    if b is None:
        raise ToolError("Unknown service. Use list_bill_options to see the codes.")
    return b


def _plan(biller, plan_code):
    if not plan_code:
        return None
    plan = biller.plans.filter(code=plan_code, is_active=True).first()
    if plan is None:
        raise ToolError("Unknown plan. Use list_bill_options to see the plan codes.")
    return plan


def list_bill_options(p: Principal, ctx, category: str, biller_code) -> dict:
    from apps.bills.models import Biller

    qs = Biller.objects.filter(category=category, is_active=True).prefetch_related("plans")
    if biller_code:
        qs = qs.filter(code=biller_code)
    return {
        "billers": [
            {
                "biller_code": b.code,
                "name": b.name,
                "number_label": b.customer_label,
                "min_amount": money(b.min_amount) if b.min_amount else None,
                "max_amount": money(b.max_amount) if b.max_amount else None,
                "plans": [
                    {
                        "plan_code": x.code,
                        "name": x.name,
                        "price": money(x.price) if x.price else "you choose the amount",
                    }
                    for x in b.plans.all()
                    if x.is_active
                ][: (25 if biller_code else 5)],
            }
            for b in qs[:15]
        ]
    }


def check_meter_or_card(p: Principal, ctx, category: str, biller_code: str, plan_code, number: str) -> dict:
    from apps.bills import services as bills

    biller = _biller(category, biller_code)
    plan = _plan(biller, plan_code)
    try:
        cid = bills.normalise_customer(biller, number)
        found = bills.verify_customer(biller, plan, cid)
    except Exception as exc:
        raise ToolError(str(getattr(exc, "detail", "") or exc)[:200]) from exc
    return {"number": cid, "name": found["name"], "details": found.get("details", {})}


def _bill_quote(category, biller_code, plan_code, number, amount):
    from apps.bills import services as bills

    biller = _biller(category, biller_code)
    plan = _plan(biller, plan_code)
    try:
        cid = bills.normalise_customer(biller, number)
        kobo = (
            to_minor(Decimal(str(amount).replace(",", "").replace("₦", "").strip()), "NGN")
            if amount
            else None
        )
        value, fee, total = bills.quote(biller, plan, kobo)
    except (InvalidOperation, ValueError) as exc:
        raise ToolError("Give the amount in naira, e.g. 1000.") from exc
    except Exception as exc:
        raise ToolError(str(getattr(exc, "detail", "") or exc)[:200]) from exc
    return biller, plan, cid, value, fee, total


def buy_bill(p: Principal, ctx, category: str, biller_code: str, plan_code, number: str, amount) -> dict:
    biller, plan, cid, value, fee, total = _bill_quote(category, biller_code, plan_code, number, amount)
    what = plan.name if plan and plan.price else f"{money(value)} NGN"
    fee_text = f" + {money(fee)} NGN fee" if fee else ""
    return ctx.propose(
        "buy_bill",
        {
            "category": category,
            "biller_code": biller_code,
            "plan_code": plan_code,
            "number": cid,
            "amount": str(to_major(value, "NGN")) if not (plan and plan.price) else None,
        },
        f"Buy {biller.name} {what} for {cid}{fee_text}. Total {money(total)} NGN, paid by a secure link",
    )


def run_buy_bill(p: Principal, ctx, category: str, biller_code: str, plan_code, number: str, amount) -> dict:
    from apps.bills import services as bills

    biller, plan, cid, value, _fee, _total = _bill_quote(category, biller_code, plan_code, number, amount)
    order = bills.create_order(
        user=p.user,
        phone=p.phone,
        biller=biller,
        plan=plan,
        customer_id=cid,
        amount=None if plan and plan.price else value,
        channel=ctx.channel_source,
    )
    order = bills.start_checkout(order)
    return {"pay_url": order.checkout_url, "total": money(order.total), "what": bills.describe(order)}


def my_bill_orders(p: Principal, ctx) -> dict:
    from apps.bills.models import Order

    qs = Order.objects.filter(phone_number=p.phone).select_related("biller", "plan")[:8]
    return {
        "orders": [
            {
                "reference": o.reference,
                "what": f"{o.biller.name} {o.plan.name if o.plan_id else ''}".strip(),
                "number": o.customer_id,
                "total": money(o.total),
                "status": o.status,
                "receipt_number": o.receipt_number or None,
                "token": o.token if o.status == "delivered" else None,
                "date": str(timezone.localtime(o.created_at).date()),
            }
            for o in qs
        ]
    }


# ---- Repairs (Phase 4) -------------------------------------------------------------------------------

REPAIR_CATEGORIES = [
    "plumbing",
    "electrical",
    "carpentry",
    "painting",
    "ac",
    "generator",
    "roofing",
    "tiling",
    "welding",
    "appliance",
    "pest",
    "cleaning",
    "locksmith",
    "other",
]


def _repair_lease(p: Principal, lease_id):
    leases = list(
        Lease.objects.filter(tenant__in=p.tenant_profiles, status="active").select_related(
            "unit__property", "organization", "tenant"
        )
    )
    if lease_id:
        lease = next((x for x in leases if str(x.pk) == str(lease_id)), None)
        if lease is None:
            raise ToolError("That isn't one of the person's current homes.")
        return lease
    if not leases:
        raise ToolError("The person has no active lease, so a repair can't be reported here.")
    if len(leases) > 1:
        raise ToolError("The person rents more than one place. Ask which one (lease_id from get_my_lease).")
    return leases[0]


def _repair_text(title: str, description: str) -> tuple[str, str]:
    title, description = " ".join(title.split())[:120], description.strip()[:2000]
    if len(title) < 3 or len(description) < 10:
        raise ToolError("Ask the person to describe the problem a little more (what, where, since when).")
    return title, description


def report_repair(
    p: Principal, ctx, lease_id, category: str, priority: str, title: str, description: str
) -> dict:
    lease = _repair_lease(p, lease_id)
    title, description = _repair_text(title, description)
    if category not in REPAIR_CATEGORIES or priority not in ("low", "normal", "urgent", "emergency"):
        raise ToolError("Unknown category or priority.")
    return ctx.propose(
        "report_repair",
        {
            "lease_id": str(lease.pk),
            "category": category,
            "priority": priority,
            "title": title,
            "description": description,
        },
        f"Send a {priority} repair request to {lease.organization.name} for {lease.unit.label}: {title}",
    )


def run_report_repair(
    p: Principal, ctx, lease_id, category: str, priority: str, title: str, description: str
) -> dict:
    from apps.maintenance import services as maintenance

    lease = _repair_lease(p, lease_id)
    title, description = _repair_text(title, description)
    ticket = maintenance.report_for_lease(
        lease,
        user=p.user,
        category=category,
        priority=priority,
        title=title,
        description=description,
        channel="whatsapp" if ctx.channel_source == "whatsapp" else "app",
    )
    return {"reference": ticket.reference, "landlord": lease.organization.name}


def _repair_row(t) -> dict:
    job = t.current_job or next((j for j in t.jobs.all() if j.status == "confirmed"), None)
    return {
        "reference": t.reference,
        "title": t.title,
        "unit": t.unit.label,
        "status": t.status,
        "priority": t.priority,
        "reported": str(timezone.localtime(t.created_at).date()),
        "artisan": job.artisan.display_name if job else None,
        "artisan_verified": job.artisan.is_verified if job else None,
        "visit": timezone.localtime(job.scheduled_for).strftime("%a %d %b %I:%M %p")
        if job and job.scheduled_for
        else None,
        "reason": t.closed_reason or None,
    }


def my_repairs(p: Principal, ctx) -> dict:
    from apps.maintenance.models import Ticket

    qs = (
        Ticket.objects.filter(tenant__in=p.tenant_profiles)
        .select_related("unit")
        .prefetch_related("jobs__artisan")
        .order_by("-created_at")[:8]
    )
    return {"repairs": [_repair_row(t) for t in qs]}


def list_repairs(p: Principal, ctx, organization_id: str, status) -> dict:
    from apps.maintenance.models import Ticket

    org = _org(p, organization_id, "maintenance.view")
    qs = (
        Ticket.objects.filter(organization=org)
        .select_related("unit", "tenant")
        .prefetch_related("jobs__artisan")
    )
    if status in (None, "", "open"):
        qs = qs.filter(status__in=Ticket.OPEN)
    elif status != "all":
        qs = qs.filter(status=status)
    rows = []
    for t in qs.order_by("-created_at")[:20]:
        row = _repair_row(t)
        row["tenant"] = t.tenant.full_name if t.tenant_id else None
        rows.append(row)
    return {
        "repairs": rows,
        "awaiting_approval": Ticket.objects.filter(organization=org, status="awaiting_approval").count(),
        "dashboard": f"{settings.WEB_APP_URL.rstrip('/')}/repairs",
    }


# ---- Estates (Phase 5) ---------------------------------------------------------------------------


def _estate_member(p: Principal, estate_id):
    members = p.estate_members
    if estate_id:
        m = next((x for x in members if str(x.estate_id) == str(estate_id)), None)
        if m is None:
            raise ToolError("The person isn't a verified resident of that estate.")
        return m
    if not members:
        raise ToolError(
            "The person isn't a verified resident of an estate on Homesika. They can join with the code "
            "from their estate office in the app (Estate > Join)."
        )
    if len(members) > 1:
        raise ToolError("The person lives in more than one estate. Ask which one.")
    return members[0]


def my_estate(p: Principal, ctx, estate_id) -> dict:
    from apps.estates.models import Announcement, GatePass

    m = _estate_member(p, estate_id)
    dues = Charge.objects.filter(dues_link__member=m, status__in=Charge.OUTSTANDING).order_by("due_date")
    news = Announcement.objects.filter(estate=m.estate, audience="all").order_by("-created_at")[:3]
    return {
        "estate_id": str(m.estate_id),
        "estate": m.estate.name,
        "house": m.unit.label if m.unit_id else m.house_label,
        "dues_owed": money(sum(c.balance for c in dues)),
        "dues": [
            {
                "description": c.description,
                "amount": money(c.balance),
                "due_date": str(c.due_date),
                "overdue": c.is_overdue,
            }
            for c in dues[:6]
        ],
        "pay_dues": "Dues are paid like rent: with create_my_payment_link, or in the app under Charges.",
        "announcements": [
            {"title": a.title, "body": a.body[:300], "date": str(timezone.localtime(a.created_at).date())}
            for a in news
        ],
        "active_gate_passes": GatePass.objects.filter(
            host=m, status="active", valid_to__gt=timezone.now()
        ).count(),
        "panic_button": m.estate.panic_enabled,
    }


def _pass_args(visitor_name: str, visitor_phone, hours: int, max_uses: int):
    from apps.accounts.validators import normalise_phone

    name = " ".join((visitor_name or "").split())[:120]
    if len(name) < 2:
        raise ToolError("Ask for the visitor's name.")
    if not 1 <= int(hours) <= 168 or not 1 <= int(max_uses) <= 50:
        raise ToolError("A pass lasts 1 to 168 hours and allows 1 to 50 entries.")
    return name, normalise_phone(visitor_phone) if visitor_phone else "", int(hours), int(max_uses)


def create_gate_pass(
    p: Principal, ctx, estate_id, visitor_name: str, visitor_phone, hours: int, max_uses: int
) -> dict:
    m = _estate_member(p, estate_id)
    name, phone, hours, max_uses = _pass_args(visitor_name, visitor_phone, hours, max_uses)
    sms = f", and text the code to {phone}" if phone else ""
    return ctx.propose(
        "create_gate_pass",
        {
            "estate_id": str(m.estate_id),
            "visitor_name": name,
            "visitor_phone": phone or None,
            "hours": hours,
            "max_uses": max_uses,
        },
        f"Create a gate pass at {m.estate.name} for {name}, valid {hours} hours from now "
        f"for {max_uses} entr{'y' if max_uses == 1 else 'ies'}{sms}",
    )


def run_create_gate_pass(
    p: Principal, ctx, estate_id, visitor_name: str, visitor_phone, hours: int, max_uses: int
) -> dict:
    from apps.estates import services as estates

    m = _estate_member(p, estate_id)
    name, phone, hours, max_uses = _pass_args(visitor_name, visitor_phone, hours, max_uses)
    gp = estates.create_pass(member=m, visitor_name=name, visitor_phone=phone, hours=hours, max_uses=max_uses)
    return {
        "code": gp.code,
        "visitor": gp.visitor_name,
        "valid_until": timezone.localtime(gp.valid_to).strftime("%a %d %b %I:%M %p"),
        "sent_note": " We've texted it to them." if phone else " Share it with your visitor.",
    }


PANIC_KINDS = ["help", "robbery", "kidnapping", "fire", "medical", "suspicious_person"]


def raise_panic_alert(p: Principal, ctx, estate_id, kind: str) -> dict:
    m = _estate_member(p, estate_id)
    if not m.estate.panic_enabled:
        raise ToolError("Panic alerts are turned off for this estate. Tell them to call 112 now.")
    if kind not in PANIC_KINDS:
        kind = "help"
    return ctx.propose(
        "raise_panic_alert",
        {"estate_id": str(m.estate_id), "kind": kind},
        f"Send an EMERGENCY alert ({kind.replace('_', ' ')}) to {m.estate.name} security and neighbours for "
        f"house {m.unit.label if m.unit_id else m.house_label}",
    )


def run_raise_panic_alert(p: Principal, ctx, estate_id, kind: str) -> dict:
    from apps.security import services as security

    m = _estate_member(p, estate_id)
    alert, _created = security.raise_alert(
        user=p.user,
        member=m,
        estate=m.estate,
        kind=kind if kind in PANIC_KINDS else "help",
        channel="whatsapp" if ctx.channel_source == "whatsapp" else "app",
    )
    return {
        "alert_sent": True,
        "status": alert.status,
        "estate": m.estate.name,
        "reminder": "Security has been alerted. They should still call 112 if they can.",
    }


def list_estate_alerts(p: Principal, ctx, organization_id: str) -> dict:
    from apps.security.models import PanicAlert

    org = _org(p, organization_id, "security.view")
    rows = []
    for a in PanicAlert.objects.filter(estate__organization=org, status__in=PanicAlert.OPEN).select_related(
        "estate", "member__unit"
    )[:10]:
        rows.append(
            {
                "estate": a.estate.name,
                "kind": a.kind,
                "status": a.status,
                "house": (a.member.unit.label if a.member.unit_id else a.member.house_label)
                if a.member_id
                else None,
                "raised": timezone.localtime(a.created_at).strftime("%a %d %b %I:%M %p"),
            }
        )
    return {"open_alerts": rows, "desk": f"{settings.WEB_APP_URL.rstrip('/')}/security"}


# ---- Registry ------------------------------------------------------------------------------------

ORG = {"type": "string", "description": "organization_id from the context"}
NULL_STR = {"type": ["string", "null"]}
TENANT_ROLES = {"tenant"}
STAFF_ROLES = {"landlord", "staff"}
ALL = {"*"}
RESIDENT_ROLES = {"resident"}

TOOLS: list[Tool] = [
    Tool(
        "list_bill_options",
        "Networks, TV services and electricity companies with their plan codes and "
        "prices (for buying airtime, data, cable TV or electricity).",
        {
            "category": {"type": "string", "enum": ["airtime", "data", "cable_tv", "electricity"]},
            "biller_code": NULL_STR,
        },
        ALL,
        list_bill_options,
    ),
    Tool(
        "check_meter_or_card",
        "Look up the owner of a meter or TV smartcard before buying. For electricity, "
        "plan_code is prepaid or postpaid.",
        {
            "category": {"type": "string", "enum": ["airtime", "data", "cable_tv", "electricity"]},
            "biller_code": {"type": "string"},
            "plan_code": NULL_STR,
            "number": {"type": "string"},
        },
        ALL,
        check_meter_or_card,
    ),
    Tool(
        "buy_bill",
        "Propose buying airtime, data, cable TV or electricity (the person must confirm, "
        "then pays by a secure link). amount in naira for airtime and electricity; "
        "null when the plan has a price.",
        {
            "category": {"type": "string", "enum": ["airtime", "data", "cable_tv", "electricity"]},
            "biller_code": {"type": "string"},
            "plan_code": NULL_STR,
            "number": {"type": "string"},
            "amount": NULL_STR,
        },
        ALL,
        buy_bill,
        action=True,
    ),
    Tool(
        "my_bill_orders",
        "The person's recent airtime, data, TV and electricity orders, with status, "
        "receipts and electricity tokens.",
        {},
        ALL,
        my_bill_orders,
    ),
    Tool(
        "search_help",
        "Search Homesika's help articles (how things work, fees, policies). Use before "
        "answering how-to questions.",
        {"query": {"type": "string"}},
        ALL,
        search_help,
    ),
    Tool(
        "search_listings",
        'Find published rental listings. max_rent is in naira, e.g. "2000000".',
        {"area": NULL_STR, "max_rent": NULL_STR, "bedrooms": {"type": ["integer", "null"]}},
        ALL,
        search_listings,
    ),
    Tool(
        "get_listing",
        "Details and open viewing slots of one listing.",
        {"listing_ref": {"type": "string"}},
        ALL,
        get_listing,
    ),
    Tool(
        "request_viewing",
        "Propose booking a viewing slot (the person must confirm).",
        {"listing_ref": {"type": "string"}, "slot_id": {"type": "string"}, "name": {"type": "string"}},
        ALL,
        request_viewing,
        action=True,
    ),
    Tool(
        "escalate_to_human",
        "Hand the conversation to a person.",
        {
            "reason": {
                "type": "string",
                "enum": [
                    "dispute",
                    "payment_problem",
                    "emergency",
                    "user_request",
                    "complaint",
                    "low_confidence",
                ],
            },
            "summary": {"type": "string", "description": "One or two sentences for the person taking over"},
        },
        ALL,
        escalate_to_human,
    ),
    Tool(
        "get_my_rent_summary",
        "What the person owes now, since when, and what is due next, per landlord.",
        {},
        TENANT_ROLES,
        get_my_rent_summary,
    ),
    Tool(
        "list_my_charges",
        "The person's charges (rent, service charge, deposit) with status and balance.",
        {"include_paid": {"type": "boolean"}},
        TENANT_ROLES,
        list_my_charges,
    ),
    Tool(
        "list_my_payments",
        "The person's recent payments with receipt numbers and links.",
        {},
        TENANT_ROLES,
        list_my_payments,
    ),
    Tool("get_my_lease", "The person's active leases.", {}, TENANT_ROLES, get_my_lease),
    Tool(
        "create_my_payment_link",
        "Propose a payment link for the person's charges (empty charge_ids = everything "
        "owed now to one landlord).",
        {"charge_ids": {"type": "array", "items": {"type": "string"}}, "organization_id": NULL_STR},
        TENANT_ROLES,
        create_my_payment_link,
        action=True,
    ),
    Tool(
        "get_portfolio_summary",
        "Units, occupancy, vacant units and money overview of an organization.",
        {"organization_id": ORG},
        STAFF_ROLES,
        get_portfolio_summary,
    ),
    Tool(
        "list_arrears",
        "Tenants who owe, oldest debt first.",
        {"organization_id": ORG},
        STAFF_ROLES,
        list_arrears,
    ),
    Tool(
        "find_tenant",
        "Find tenants by name, phone or unit.",
        {"organization_id": ORG, "query": {"type": "string"}},
        STAFF_ROLES,
        find_tenant,
    ),
    Tool(
        "get_tenant_account",
        "One tenant's charges owed now and recent payments.",
        {"organization_id": ORG, "tenant_id": {"type": "string"}},
        STAFF_ROLES,
        get_tenant_account,
    ),
    Tool(
        "list_recent_payments",
        "Payments received in the last N days (1-90).",
        {"organization_id": ORG, "days": {"type": "integer"}},
        STAFF_ROLES,
        list_recent_payments,
    ),
    Tool(
        "send_payment_link",
        "Propose sending a tenant a payment link (empty charge_ids = everything owed now).",
        {
            "organization_id": ORG,
            "tenant_id": {"type": "string"},
            "charge_ids": {"type": "array", "items": {"type": "string"}},
        },
        STAFF_ROLES,
        send_payment_link,
        action=True,
    ),
    Tool(
        "list_leads",
        "Enquiries from listings. stage: new, contacted, viewing_booked, viewed, "
        "applied, won, lost, or null for all.",
        {"organization_id": ORG, "stage": NULL_STR},
        STAFF_ROLES,
        list_leads,
    ),
    Tool(
        "list_viewings",
        "Upcoming viewings in the next N days (1-30).",
        {"organization_id": ORG, "days": {"type": "integer"}},
        STAFF_ROLES,
        list_viewings,
    ),
    Tool(
        "report_repair",
        "Propose sending the landlord a repair request for one of the person's homes. lease_id from "
        "get_my_lease, or null if they rent only one place. Photos can only be added in the app.",
        {
            "lease_id": NULL_STR,
            "category": {"type": "string", "enum": REPAIR_CATEGORIES},
            "priority": {"type": "string", "enum": ["low", "normal", "urgent", "emergency"]},
            "title": {"type": "string", "description": "A few words, e.g. 'Kitchen tap leaking'"},
            "description": {"type": "string", "description": "What, where, since when"},
        },
        TENANT_ROLES,
        report_repair,
        action=True,
    ),
    Tool(
        "my_repairs",
        "The person's recent repair requests: status, artisan and visit time.",
        {},
        TENANT_ROLES,
        my_repairs,
    ),
    Tool(
        "list_repairs",
        "Repair requests for an organization. status: open (default), all, or one of awaiting_approval, "
        "approved, assigned, in_progress, done, confirmed, rejected, cancelled.",
        {"organization_id": ORG, "status": NULL_STR},
        STAFF_ROLES,
        list_repairs,
    ),
    Tool(
        "my_estate",
        "The person's estate: house, estate dues owed, recent announcements, active gate passes. estate_id "
        "from the context, or null if they live in only one estate.",
        {"estate_id": NULL_STR},
        RESIDENT_ROLES,
        my_estate,
    ),
    Tool(
        "create_gate_pass",
        "Propose a gate pass for a visitor to the person's estate. The code is shown after they confirm "
        "and, if visitor_phone is given, texted to the visitor. hours: 1-168 (default 12); max_uses: 1-50.",
        {
            "estate_id": NULL_STR,
            "visitor_name": {"type": "string"},
            "visitor_phone": NULL_STR,
            "hours": {"type": "integer"},
            "max_uses": {"type": "integer"},
        },
        RESIDENT_ROLES,
        create_gate_pass,
        action=True,
    ),
    Tool(
        "raise_panic_alert",
        "Propose sending an emergency alert to the estate's security and neighbours. Only when the person "
        "says they or someone at their house is in danger now. Always tell them to call 112 too.",
        {"estate_id": NULL_STR, "kind": {"type": "string", "enum": PANIC_KINDS}},
        RESIDENT_ROLES,
        raise_panic_alert,
        action=True,
    ),
    Tool(
        "list_estate_alerts",
        "Open panic alerts in the organization's estates (security desk and managers).",
        {"organization_id": ORG},
        STAFF_ROLES,
        list_estate_alerts,
    ),
]
BY_NAME = {t.name: t for t in TOOLS}
RUNNERS = {
    "create_gate_pass": run_create_gate_pass,
    "raise_panic_alert": run_raise_panic_alert,
    "report_repair": run_report_repair,
    "buy_bill": run_buy_bill,
    "create_my_payment_link": run_create_my_payment_link,
    "send_payment_link": run_send_payment_link,
    "request_viewing": run_request_viewing,
}


def for_principal(p: Principal) -> list[Tool]:
    roles = p.roles
    return [t for t in TOOLS if "*" in t.roles or t.roles & roles]
