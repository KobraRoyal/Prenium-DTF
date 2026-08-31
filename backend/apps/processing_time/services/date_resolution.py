from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone


def completion_date(*, order_date: date, business_days: int) -> date:
    """Date d'expédition estimée si la commande est passée à order_date."""
    if business_days <= 0:
        return _next_business_day(order_date)
    current = order_date
    added = 0
    while added < business_days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def option_meets_requested_date(
    *,
    order_date: date,
    requested_date: date,
    business_days: int,
) -> bool:
    if requested_date < order_date:
        return False
    return completion_date(order_date=order_date, business_days=business_days) <= requested_date


def resolve_slowest_qualifying_code(
    *,
    options,
    order_date: date,
    requested_date: date,
) -> str | None:
    """Retourne le code le plus lent (donc le moins cher) qui respecte la date souhaitée."""
    qualifying = [
        option
        for option in options
        if option_meets_requested_date(
            order_date=order_date,
            requested_date=requested_date,
            business_days=int(option.business_days),
        )
    ]
    if not qualifying:
        return None
    best = max(qualifying, key=lambda option: int(option.business_days))
    return str(best.code)


def _next_business_day(value: date) -> date:
    current = value + timedelta(days=1)
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current


def reference_order_date(reference_date: date | None = None) -> date:
    return reference_date or timezone.localdate()
