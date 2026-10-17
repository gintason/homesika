"""Knowledge-base retrieval: Postgres full-text search (simple dictionary, so Pidgin words match too), and
a plain word match on SQLite (tests)."""

import re

from django.db import connection
from django.db.models import Q

from .models import KbArticle

STOP = {
    "the",
    "a",
    "an",
    "is",
    "i",
    "my",
    "to",
    "for",
    "of",
    "and",
    "how",
    "do",
    "can",
    "what",
    "dey",
    "na",
    "wetin",
}


def _visible(roles: set, organization_ids: list):
    qs = KbArticle.objects.filter(status="published").filter(
        Q(organization__isnull=True) | Q(organization_id__in=organization_ids)
    )
    return [a for a in qs if not a.audience or set(a.audience) & roles]


def search(
    query: str, *, roles: set, language: str = "en", organization_ids=(), limit: int = 3
) -> list[dict]:
    words = [w for w in re.findall(r"[\w']+", query.lower()) if w not in STOP and len(w) > 2][:12]
    if not words:
        return []
    candidates = _visible(roles, list(organization_ids))
    ids = [a.pk for a in candidates]
    if connection.vendor == "postgresql":
        from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

        vector = SearchVector("title", weight="A", config="simple") + SearchVector(
            "body", weight="B", config="simple"
        )
        q = SearchQuery(" | ".join(words), search_type="raw", config="simple")
        ranked = list(
            KbArticle.objects.filter(pk__in=ids)
            .annotate(rank=SearchRank(vector, q))
            .filter(rank__gt=0)
            .order_by("-rank")[:10]
        )
    else:

        def score(a):
            text = f"{a.title} {a.title} {a.body}".lower()
            return sum(text.count(w) for w in words)

        ranked = sorted((a for a in candidates if score(a)), key=score, reverse=True)[:10]
    # Prefer the person's language, then the other one.
    ranked.sort(key=lambda a: a.language != language)
    return [
        {
            "title": a.title,
            "body": a.body[:1500],
            "language": a.language,
            "source": "organization" if a.organization_id else "Homesika",
        }
        for a in ranked[:limit]
    ]
