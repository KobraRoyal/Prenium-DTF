import pytest
from apps.processing_time.forms_staff import (
    StaffCustomerProcessingTimeOverridesForm,
    StaffProcessingTimeSettingsForm,
)
from apps.processing_time.models import ProcessingTimeOption
from apps.processing_time.services.options import ProcessingTimeOptionService
from apps.processing_time.services.staff_ui import (
    build_customer_override_cards,
    build_global_settings_cards,
    preview_text_for_settings_card,
)


@pytest.mark.django_db
def test_build_global_settings_cards_binds_fields_and_preview():
    ProcessingTimeOptionService().ensure_default_options()
    options = list(ProcessingTimeOption.objects.order_by("display_order"))
    form = StaffProcessingTimeSettingsForm(options=tuple(options))

    cards = build_global_settings_cards(form=form, options=options)

    assert len(cards) == 3
    standard = next(card for card in cards if card["option"].code == "standard")
    assert standard["inactive"] is False
    assert "markup_percent" in standard["fields"]
    assert standard["preview_text"] == preview_text_for_settings_card(
        option=standard["option"],
        fields=standard["fields"],
    )


@pytest.mark.django_db
def test_build_customer_override_cards_marks_disabled_rows():
    ProcessingTimeOptionService().ensure_default_options()
    express = ProcessingTimeOption.objects.get(code="express")
    rows = [
        {
            "option": express,
            "override": None,
            "is_enabled": False,
            "markup_percent": None,
            "flat_fee_eur": None,
        }
    ]
    form = StaffCustomerProcessingTimeOverridesForm(rows=rows)

    cards = build_customer_override_cards(form=form, rows=rows)

    assert len(cards) == 1
    assert cards[0]["inactive"] is True
    assert cards[0]["fields"]["is_enabled"].name.endswith("__is_enabled")
