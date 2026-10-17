"""
Where Homesika operates: countries and cities. One table, so a new city or country is configuration,
not code spread across the apps.

* A country is "enabled" when listed in MARKETS_COUNTRIES (default "NG"). Ghana is fully described here but
  stays off until MARKETS_COUNTRIES includes GH: organizations can't be created there before that.
* Cities carry the neighbourhoods suggested in listing, artisan-area and property forms, and their
  electricity companies (bills catalogue codes). Lagos and Abuja are on.
* What differs per country and must be done before switching one on is listed in `launch_checklist`
  (shown in docs/MARKETS.md): payment gateways in that currency, a bills provider, ID checks, SMS sender
  ID, emergency numbers and legal review.
"""

from dataclasses import dataclass, field

from django.conf import settings


@dataclass(frozen=True)
class Country:
    code: str
    name: str
    currency: str
    calling_code: str  # without "+"
    local_length: int  # digits in a national number written with a leading 0, e.g. 0801 234 5678 = 11
    timezone: str
    emergency: str  # what the apps tell people to call; TODO(verify) per country with local authorities
    bills: bool  # airtime/data/TV/electricity (VTU) available in-country
    id_check: str  # how artisans are verified there
    launch_checklist: tuple = ()


@dataclass(frozen=True)
class City:
    slug: str
    name: str
    state: str
    country: str
    areas: tuple
    discos: tuple = field(default_factory=tuple)


COUNTRIES = {
    "NG": Country("NG", "Nigeria", "NGN", "234", 11, "Africa/Lagos", "112", bills=True, id_check="nin"),
    "GH": Country(
        "GH",
        "Ghana",
        "GHS",
        "233",
        10,
        "Africa/Accra",
        "112",
        bills=False,
        id_check="manual",
        launch_checklist=(
            "Paystack/Flutterwave settlement in GHS (and mobile money) confirmed in writing for splits",
            "A Ghana bills provider (airtime, data, ECG electricity) or keep bills off",
            "Artisan ID check: Ghana Card through a licensed provider (manual review until then)",
            "SMS sender ID registered for Ghana; WhatsApp templates approved for Ghana numbers",
            "Emergency numbers confirmed (112; police 191, fire 192, ambulance 193) — TODO(verify)",
            "Data protection: Ghana's Data Protection Act 2012 (register with the DPC)",
            "Lawyer review of terms, rent collection and estate security wording for Ghana",
        ),
    ),
}

CITIES = {
    "lagos": City(
        "lagos",
        "Lagos",
        "Lagos",
        "NG",
        areas=(
            "Ajah",
            "Gbagada",
            "Ikeja",
            "Ikeja GRA",
            "Ikoyi",
            "Lekki",
            "Lekki Phase 1",
            "Magodo",
            "Maryland",
            "Ogudu",
            "Surulere",
            "Victoria Island",
            "Yaba",
            "Ogba",
            "Festac",
            "Ikorodu",
            "Sangotedo",
            "Chevron",
        ),
        discos=("ikeja-electric", "eko-electric"),
    ),
    "abuja": City(
        "abuja",
        "Abuja",
        "FCT",
        "NG",
        areas=(
            "Apo",
            "Asokoro",
            "Durumi",
            "Garki",
            "Gwarinpa",
            "Jabi",
            "Jahi",
            "Katampe",
            "Kubwa",
            "Life Camp",
            "Lokogoma",
            "Lugbe",
            "Maitama",
            "Utako",
            "Wuse",
            "Wuse 2",
            "Wuye",
            "Guzape",
            "Gwagwalada",
            "Karu",
        ),
        discos=("abuja-electric",),
    ),
    "accra": City(
        "accra",
        "Accra",
        "Greater Accra",
        "GH",
        areas=(
            "Airport Residential",
            "Cantonments",
            "East Legon",
            "Labone",
            "Osu",
            "Spintex",
            "Tema",
            "Adenta",
            "Dzorwulu",
            "Madina",
        ),
    ),
}


def enabled_countries() -> list[Country]:
    codes = [c.strip().upper() for c in settings.MARKETS_COUNTRIES.split(",") if c.strip()]
    return [COUNTRIES[c] for c in codes if c in COUNTRIES]


def is_enabled(country: str) -> bool:
    return any(c.code == (country or "").upper() for c in enabled_countries())


def enabled_cities() -> list[City]:
    on = {c.code for c in enabled_countries()}
    slugs = [s.strip().lower() for s in settings.MARKETS_CITIES.split(",") if s.strip()]
    return [CITIES[s] for s in slugs if s in CITIES and CITIES[s].country in on]


def country(code: str) -> Country | None:
    return COUNTRIES.get((code or "").upper())


def normalise_phone(raw: str, country_code: str = "NG") -> str:
    """National or international input -> E.164, using the country's calling code for local numbers:
    NG 08012345678 -> +2348012345678; GH 0241234567 -> +233241234567."""
    c = COUNTRIES.get((country_code or "NG").upper(), COUNTRIES["NG"])
    digits = "".join(ch for ch in raw or "" if ch.isdigit() or ch == "+")
    if digits.startswith("+"):
        return digits
    if digits.startswith("00"):
        return "+" + digits[2:]
    if digits.startswith(c.calling_code) and len(digits) > c.local_length:
        return f"+{digits}"
    if digits.startswith("0") and len(digits) == c.local_length:
        return f"+{c.calling_code}{digits[1:]}"
    if len(digits) == c.local_length - 1 and c.code == "NG" and digits[:1] in "789":
        return f"+{c.calling_code}{digits}"
    return digits
