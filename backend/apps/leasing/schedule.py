"""Rent schedule maths: pure functions, no database, fully unit-tested."""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal


def add_months(d: date, months: int) -> date:
    """Same day N months later, clamped to the month's end (Jan 31 + 1 month = Feb 28/29)."""
    month_index = d.month - 1 + months
    year, month = d.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


@dataclass(frozen=True)
class Period:
    start: date
    end: date  # inclusive
    fraction: Decimal  # 1 for a full period; less for a short final period


def periods(start: date, end: date, months: int) -> list[Period]:
    """Billing periods from start up to end (inclusive). Rent is due at the start of each period (in
    advance, the Nigerian norm). A final period cut short by the lease end is pro-rated by days."""
    out, cursor, n = [], start, 0
    while cursor <= end:
        n += 1
        full_next = add_months(start, months * n)  # anchor on the start date so month-ends don't drift
        period_end = min(full_next - timedelta(days=1), end)
        full_days = (full_next - cursor).days
        used_days = (period_end - cursor).days + 1
        fraction = Decimal(1) if used_days >= full_days else Decimal(used_days) / Decimal(full_days)
        out.append(Period(cursor, period_end, fraction))
        cursor = full_next
    return out


def prorate(amount_minor: int, fraction: Decimal) -> int:
    if fraction == 1:
        return amount_minor
    return int((Decimal(amount_minor) * fraction).quantize(Decimal(1), rounding=ROUND_HALF_UP))
