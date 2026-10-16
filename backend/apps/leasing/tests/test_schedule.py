from datetime import date
from decimal import Decimal

from apps.leasing.schedule import add_months, periods, prorate


def test_add_months_clamps_to_month_end():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)


def test_annual_lease_is_one_full_period():
    (p,) = periods(date(2026, 11, 1), date(2027, 10, 31), 12)
    assert (p.start, p.end, p.fraction) == (date(2026, 11, 1), date(2027, 10, 31), Decimal(1))


def test_monthly_periods_anchor_on_start_day_without_drift():
    ps = periods(date(2026, 1, 31), date(2026, 5, 30), 1)
    assert [p.start for p in ps] == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
    ]
    assert all(p.fraction == 1 for p in ps)


def test_short_final_period_is_prorated_by_days():
    ps = periods(date(2026, 1, 1), date(2026, 2, 14), 1)
    assert len(ps) == 2 and ps[1].end == date(2026, 2, 14)
    assert ps[1].fraction == Decimal(14) / Decimal(28)
    assert prorate(28_000_00, ps[1].fraction) == 14_000_00
