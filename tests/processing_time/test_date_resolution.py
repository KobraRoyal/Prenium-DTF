from datetime import date

import pytest
from apps.customers.models import Customer
from apps.processing_time.services.date_resolution import (
    completion_date,
    option_meets_requested_date,
    resolve_slowest_qualifying_code,
)
from apps.processing_time.services.options import ProcessingTimeOptionService


@pytest.mark.parametrize(
    ("order_date", "business_days", "expected"),
    [
        (date(2026, 8, 31), 0, date(2026, 9, 1)),
        (date(2026, 8, 31), 2, date(2026, 9, 2)),
        (date(2026, 8, 31), 3, date(2026, 9, 3)),
        (date(2026, 8, 28), 0, date(2026, 8, 31)),
    ],
)
def test_completion_date_skips_weekends(order_date, business_days, expected):
    assert completion_date(order_date=order_date, business_days=business_days) == expected


@pytest.mark.parametrize(
    ("requested_date", "expected_code"),
    [
        (date(2026, 9, 5), "standard"),
        (date(2026, 9, 3), "standard"),
        (date(2026, 9, 2), "fast"),
        (date(2026, 9, 1), "express"),
        (date(2026, 8, 31), "express"),
    ],
)
@pytest.mark.django_db
def test_resolve_code_for_requested_date_picks_cheapest_compatible(
    requested_date,
    expected_code,
):
    customer = Customer.objects.create(name="Date delay client")
    service = ProcessingTimeOptionService()
    service.ensure_default_options()
    order_date = date(2026, 8, 31)
    assert (
        service.resolve_code_for_requested_date(
            customer=customer,
            requested_date=requested_date,
            reference_date=order_date,
        )
        == expected_code
    )


@pytest.mark.django_db
def test_resolve_slowest_qualifying_code_returns_none_when_date_too_tight():
    customer = Customer.objects.create(name="Tight date client")
    service = ProcessingTimeOptionService()
    service.ensure_default_options()
    options = service.list_active_options_for_customer(customer)
    assert (
        resolve_slowest_qualifying_code(
            options=options,
            order_date=date(2026, 8, 31),
            requested_date=date(2026, 8, 30),
        )
        is None
    )
    assert not option_meets_requested_date(
        order_date=date(2026, 8, 31),
        requested_date=date(2026, 8, 30),
        business_days=3,
    )
