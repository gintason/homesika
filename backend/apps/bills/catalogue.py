"""The bills catalogue. Billers are seeded (migration 0002); data bundles and TV bouquets with prices are
synced from VTU.ng (`manage.py sync_bills_catalogue`), or sample plans in development (`--sample`)."""

import logging

from django.conf import settings
from django.db import transaction

from apps.core.money import to_minor

from .models import Biller, Category, Plan
from .providers import vtung

logger = logging.getLogger(__name__)
AIRTIME_MIN, AIRTIME_MAX = 100_00, 50_000_00
ELECTRICITY_MIN, ELECTRICITY_MAX = 1_000_00, 200_000_00


def seed_billers(BillerModel=Biller, PlanModel=Plan) -> int:
    n = 0
    for i, (code, name) in enumerate(vtung.NETWORKS.items()):
        BillerModel.objects.update_or_create(
            category=Category.AIRTIME,
            code=code,
            defaults={
                "name": f"{name} airtime",
                "customer_label": "Phone number",
                "min_amount": AIRTIME_MIN,
                "max_amount": AIRTIME_MAX,
                "provider_codes": {"vtung": code},
                "sort_order": i,
            },
        )
        BillerModel.objects.update_or_create(
            category=Category.DATA,
            code=code,
            defaults={
                "name": f"{name} data",
                "customer_label": "Phone number",
                "provider_codes": {"vtung": code},
                "sort_order": i,
            },
        )
        n += 2
    for i, (code, name) in enumerate(vtung.TV.items()):
        BillerModel.objects.update_or_create(
            category=Category.CABLE_TV,
            code=code,
            defaults={
                "name": name,
                "customer_label": "Smartcard / IUC number",
                "requires_verification": code != "showmax",
                "provider_codes": {"vtung": code},
                "sort_order": i,
            },
        )
        n += 1
    for i, (code, name) in enumerate(vtung.DISCOS.items()):
        disco, _ = BillerModel.objects.update_or_create(
            category=Category.ELECTRICITY,
            code=code,
            defaults={
                "name": name,
                "customer_label": "Meter number",
                "requires_verification": True,
                "min_amount": ELECTRICITY_MIN,
                "max_amount": ELECTRICITY_MAX,
                "provider_codes": {"vtung": code},
                "sort_order": i,
            },
        )
        for j, meter in enumerate(("prepaid", "postpaid")):
            PlanModel.objects.update_or_create(
                biller=disco,
                code=meter,
                defaults={
                    "name": meter.title(),
                    "price": None,
                    "provider_codes": {"vtung": meter},
                    "sort_order": j,
                },
            )
        n += 1
    return n


def _sync(category: str, rows: list[dict], label_key: str, markup: float) -> int:
    seen = 0
    for biller in Biller.objects.filter(category=category):
        sid = biller.provider_codes.get("vtung")
        if not sid:
            continue
        keep = []
        for row in (r for r in rows if str(r.get("service_id", "")).lower() == sid):
            name = str(row.get(label_key) or row["variation_id"])
            plan, _ = Plan.objects.update_or_create(
                biller=biller,
                code=f"vtung-{row['variation_id']}",
                defaults={
                    "name": name,
                    "price": vtung._priced(row["price"], markup),
                    "provider_codes": {"vtung": str(row["variation_id"])},
                    "provider_costs": {"vtung": to_minor(str(row["price"]), "NGN")},
                    "is_active": str(row.get("availability", "Available")).lower() == "available",
                    **(vtung._plan_details(name) if category == Category.DATA else {}),
                },
            )
            keep.append(plan.pk)
            seen += 1
        biller.plans.filter(code__startswith="vtung-").exclude(pk__in=keep).update(is_active=False)
    return seen


@transaction.atomic
def sync_from_vtung() -> int:
    seed_billers()
    client = vtung.VtuNg()
    n = _sync(Category.DATA, client.variations("data"), "data_plan", settings.BILLS_DATA_MARKUP_PERCENT)
    n += _sync(
        Category.CABLE_TV, client.variations("tv"), "package_bouquet", settings.BILLS_TV_MARKUP_PERCENT
    )
    logger.info("Synced %s bill plans from VTU.ng", n)
    return n


SAMPLE = {
    Category.DATA: [
        ("sample-1gb", "1GB, 30 days (sample)", 1_000_00, 1024, 30),
        ("sample-5gb", "5GB, 30 days (sample)", 4_000_00, 5120, 30),
    ],
    Category.CABLE_TV: [
        ("sample-basic", "Basic bouquet (sample)", 4_000_00, None, 30),
        ("sample-premium", "Premium bouquet (sample)", 29_000_00, None, 30),
    ],
}


@transaction.atomic
def load_samples() -> int:
    """Development only: plausible plans so the flow can be tried with the mock provider."""
    seed_billers()
    n = 0
    for category, rows in SAMPLE.items():
        for biller in Biller.objects.filter(category=category):
            for i, (code, name, price, mb, days) in enumerate(rows):
                Plan.objects.update_or_create(
                    biller=biller,
                    code=code,
                    defaults={
                        "name": name,
                        "price": price,
                        "provider_codes": {"mock": code},
                        "data_mb": mb,
                        "validity_days": days,
                        "sort_order": i,
                    },
                )
                n += 1
    return n
