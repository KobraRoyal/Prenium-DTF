import pytest
from apps.b2b_order_projects.models import B2BOrderProject
from apps.b2b_order_projects.services.numbering import (
    B2BOrderProjectNumberService,
    project_number_prefix_for_order_mode,
)


@pytest.mark.parametrize(
    "order_mode",
    [
        B2BOrderProject.OrderMode.INDIVIDUAL_DESIGNS,
        B2BOrderProject.OrderMode.READY_GANG_SHEET,
        B2BOrderProject.OrderMode.REORDER,
    ],
)
def test_project_number_prefix_is_cmd_for_all_modes(order_mode):
    assert project_number_prefix_for_order_mode(order_mode) == "CMD"


@pytest.mark.django_db
def test_next_number_uses_cmd_prefix_for_gang_sheet():
    service = B2BOrderProjectNumberService()
    number = service.next_number(order_mode=B2BOrderProject.OrderMode.READY_GANG_SHEET)
    assert number.startswith("CMD-")
    year, seq = number.removeprefix("CMD-").split("-", 1)
    assert len(year) == 4
    assert len(seq) == 6 and seq.isdigit()
