"""Guardrails enforced in code: length, rate and cost limits, yes/no detection, language detection, and
the output filter that strips contact details and account numbers that aren't the person's own."""

import re
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db.models import Sum
from django.utils import timezone

MAX_INPUT_CHARS = 2000

YES = {
    "yes",
    "y",
    "yeah",
    "yep",
    "ok",
    "okay",
    "confirm",
    "confirmed",
    "go ahead",
    "proceed",
    "oya",
    "ehen",
    "na so",
    "do am",
    "send am",
    "yes please",
    "yes pls",
    "sure",
    "correct",
    "abeg do am",
    "i confirm",
}
NO = {
    "no",
    "n",
    "nope",
    "cancel",
    "stop",
    "no thanks",
    "don't",
    "dont",
    "no o",
    "abeg no",
    "leave am",
    "wait",
}

PIDGIN_MARKERS = re.compile(
    r"\b(abeg|wetin|dey|una|wahala|abi|sabi|comot|oga|pikin|e don|don pay|how far|no vex|wey|make i|"
    r"na im|na so|shey|sha|biko|oya|ehen|fit|small small|wan|abi na|chop|kpatakpata|i no|no be)\b",
    re.I,
)


def normalise(text: str) -> str:
    return re.sub(r"[\s!.?,]+", " ", text.strip().lower()).strip()


def is_yes(text: str) -> bool:
    return normalise(text) in YES


def is_no(text: str) -> bool:
    return normalise(text) in NO


def detect_language(text: str, current: str = "en") -> str:
    t = text.lower()
    if re.search(r"\b(english please|in english|speak english)\b", t):
        return "en"
    if re.search(r"\b(speak pidgin|in pidgin|pidgin please|talk pidgin)\b", t):
        return "pcm"
    hits = len(PIDGIN_MARKERS.findall(t))
    if hits >= 2 or (hits == 1 and len(t.split()) <= 6):
        return "pcm"
    if hits == 0 and len(t.split()) >= 3:
        return "en"
    return current


def rate_limited(sender_key: str) -> bool:
    count, seconds = (int(x) for x in settings.ASSISTANT_RATE_LIMIT.split("/"))
    key = f"assistant:rate:{sender_key}"
    if cache.add(key, 1, timeout=seconds):
        return False
    try:
        return cache.incr(key) > count
    except ValueError:
        cache.set(key, 1, timeout=seconds)
        return False


def over_budget(*, sender_key: str, organization_id=None) -> str | None:
    """Returns which cap is hit ('user', 'organization', 'platform') or None."""
    from .models import AssistantTurn

    now = timezone.now()
    day = now - timedelta(days=1)
    spent = lambda qs: qs.aggregate(s=Sum("cost_usd"))["s"] or Decimal(0)  # noqa: E731
    if spent(AssistantTurn.objects.filter(sender=sender_key, created_at__gte=day)) >= Decimal(
        settings.ASSISTANT_USER_DAILY_CAP_USD
    ):
        return "user"
    if organization_id and spent(
        AssistantTurn.objects.filter(
            organization_id=organization_id, created_at__gte=now - timedelta(days=30)
        )
    ) >= Decimal(settings.ASSISTANT_ORG_MONTHLY_CAP_USD):
        return "organization"
    if spent(AssistantTurn.objects.filter(created_at__gte=day)) >= Decimal(
        settings.ASSISTANT_PLATFORM_DAILY_CAP_USD
    ):
        return "platform"
    return None


PHONE_RE = re.compile(r"(?<![\w/])(?:\+?234|0)[789][01]\d[\s-]?\d{3}[\s-]?\d{4}(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
LONG_DIGITS_RE = re.compile(r"(?<![\w/=-])\d(?:[ -]?\d){9,18}(?![\w/])")  # account / card numbers


def _digits(s: str) -> str:
    d = re.sub(r"\D", "", s)
    return "234" + d[1:] if d.startswith("0") else d


def filter_output(text: str, *, allowed_phones=(), allowed_emails=()) -> tuple[str, bool]:
    """Remove phone numbers, emails and long digit runs that aren't on the allow list. URLs are kept."""
    allowed = {_digits(p) for p in allowed_phones if p}
    emails = {e.lower() for e in allowed_emails if e}
    changed = False

    def phone(m):
        nonlocal changed
        if _digits(m.group(0)) in allowed:
            return m.group(0)
        changed = True
        return "[number removed]"

    def email(m):
        nonlocal changed
        if m.group(0).lower() in emails:
            return m.group(0)
        changed = True
        return "[email removed]"

    def digits(m):
        nonlocal changed
        if _digits(m.group(0)) in allowed:
            return m.group(0)
        changed = True
        return "[number removed]"

    out = PHONE_RE.sub(phone, text)
    out = EMAIL_RE.sub(email, out)
    out = LONG_DIGITS_RE.sub(digits, out)
    return out, changed
