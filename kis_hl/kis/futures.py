"""KOSPI200 index futures contract-code helpers for read-only reference quotes."""
from __future__ import annotations

from datetime import date, timedelta

QUARTERLY_MONTHS = (3, 6, 9, 12)


def second_thursday(year: int, month: int) -> date:
    first = date(year, month, 1)
    first_thursday = first + timedelta(days=(3 - first.weekday()) % 7)
    return first_thursday + timedelta(days=7)


def kospi200_front_future_code(today: date) -> str:
    """Return the KIS short code of the front quarterly KOSPI200 future.

    Format verified live: ``A01`` + last year digit + two-digit month, for example
    ``A01612`` for December 2026. Rolls after the nominal second-Thursday expiry;
    exchange holiday shifts of the last trading day are not modelled, so callers
    must check ``futs_last_tr_date`` in the quote response.
    """
    year = today.year
    while True:
        for month in QUARTERLY_MONTHS:
            if (year, month) < (today.year, today.month):
                continue
            if today <= second_thursday(year, month):
                return f"A01{year % 10}{month:02d}"
        year += 1
