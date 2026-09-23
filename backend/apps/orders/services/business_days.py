from __future__ import annotations

from datetime import date, timedelta


def add_business_days(start_date: date, days: int) -> date:
    """Return a Monday–Friday deadline, excluding Saturdays and Sundays."""
    if days < 0:
        raise ValueError("Business-day offsets cannot be negative.")

    current_date = start_date
    remaining_days = days
    while remaining_days:
        current_date += timedelta(days=1)
        if current_date.weekday() < 5:
            remaining_days -= 1
    return current_date
