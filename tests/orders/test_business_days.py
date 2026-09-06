from datetime import date

import pytest
from apps.orders.services.business_days import add_business_days


@pytest.mark.parametrize(
    ("start_date", "days", "expected"),
    [
        (date(2026, 9, 4), 1, date(2026, 9, 7)),
        (date(2026, 9, 4), 3, date(2026, 9, 9)),
        (date(2026, 9, 7), 1, date(2026, 9, 8)),
    ],
)
def test_add_business_days_skips_weekends(start_date, days, expected):
    assert add_business_days(start_date, days) == expected
