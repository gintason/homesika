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
                "unit": x.unit.label,
                "property": x.unit.property.name,
                "address": x.unit.property.address,
                "landlord": x.organization.name,
                "landlord_phone": x.organization.phone_number,
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


# ---- Registry ------------------------------------------------------------------------------------

ORG = {"type": "string", "description": "organization_id from the context"}
NULL_STR = {"type": ["string", "null"]}
TENANT_ROLES = {"tenant"}
STAFF_ROLES = {"landlord", "staff"}
ALL = {"*"}

TOOLS: list[Tool] = [
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
]
BY_NAME = {t.name: t for t in TOOLS}
RUNNERS = {
    "create_my_payment_link": run_create_my_payment_link,
    "send_payment_link": run_send_payment_link,
    "request_viewing": run_request_viewing,
}


def for_principal(p: Principal) -> list[Tool]:
    roles = p.roles
    return [t for t in TOOLS if "*" in t.roles or t.roles & roles]
