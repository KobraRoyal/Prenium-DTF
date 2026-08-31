from __future__ import annotations

from apps.processing_time.models import ProcessingTimeOption

SETTINGS_OPTION_FIELD_NAMES = (
    "name",
    "eta_label",
    "disclaimer",
    "business_days",
    "markup_percent",
    "flat_fee_eur",
    "is_default",
    "is_active",
    "display_order",
)

CUSTOMER_OVERRIDE_FIELD_NAMES = (
    "is_enabled",
    "markup_percent",
    "flat_fee_eur",
)


def option_field_prefix(code: str) -> str:
    return code.replace("-", "_")


def bind_option_fields(form, *, option: ProcessingTimeOption, field_names: tuple[str, ...]) -> dict:
    prefix = option_field_prefix(option.code)
    return {name: form[f"{prefix}__{name}"] for name in field_names}


def preview_text_for_settings_card(*, option: ProcessingTimeOption, fields: dict) -> str:
    eta = (fields["eta_label"].value() or option.eta_label or "").strip()
    disclaimer = (fields["disclaimer"].value() or option.disclaimer or "").strip()
    if disclaimer:
        return f"{eta} — {disclaimer}"
    return eta


def build_global_settings_cards(*, form, options) -> list[dict]:
    cards: list[dict] = []
    for option in options:
        fields = bind_option_fields(
            form,
            option=option,
            field_names=SETTINGS_OPTION_FIELD_NAMES,
        )
        cards.append(
            {
                "option": option,
                "inactive": not option.is_active,
                "fields": fields,
                "preview_text": preview_text_for_settings_card(option=option, fields=fields),
            }
        )
    return cards


def build_customer_override_cards(*, form, rows: list[dict]) -> list[dict]:
    cards: list[dict] = []
    for row in rows:
        option = row["option"]
        cards.append(
            {
                "option": option,
                "row": row,
                "inactive": not row["is_enabled"],
                "fields": bind_option_fields(
                    form,
                    option=option,
                    field_names=CUSTOMER_OVERRIDE_FIELD_NAMES,
                ),
            }
        )
    return cards
