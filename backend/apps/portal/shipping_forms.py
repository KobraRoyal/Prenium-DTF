from __future__ import annotations

SHIPMENT_FORM_KEYS = (
    "recipient_name",
    "recipient_company_name",
    "recipient_email",
    "recipient_phone_number",
    "recipient_country_code",
    "recipient_city",
    "recipient_postal_code",
    "recipient_address_line_1",
    "recipient_address_line_2",
    "recipient_house_number",
    "parcel_weight_value",
)


def _project_shipping_snapshot(order) -> dict:
    project = getattr(order, "source_b2b_order_project", None)
    raw = getattr(project, "shipping_address", None) or {}
    return raw if isinstance(raw, dict) else {}


def build_shipment_form_data(*, order, submitted_data=None) -> dict[str, str]:
    if submitted_data is not None:
        return {key: submitted_data.get(key, "") for key in SHIPMENT_FORM_KEYS}
    customer = order.customer
    snapshot = _project_shipping_snapshot(order)
    country = (
        str(snapshot.get("country") or customer.shipping_country or "FR").strip().upper() or "FR"
    )
    return {
        "recipient_name": snapshot.get("name") or customer.name or "",
        "recipient_company_name": snapshot.get("company_name") or customer.name or "",
        "recipient_email": snapshot.get("email") or customer.billing_email or "",
        "recipient_phone_number": snapshot.get("phone") or snapshot.get("phone_number") or "",
        "recipient_country_code": country[:2],
        "recipient_city": snapshot.get("city") or customer.shipping_city or "",
        "recipient_postal_code": snapshot.get("postal_code") or customer.shipping_postal_code or "",
        "recipient_address_line_1": snapshot.get("line1") or customer.shipping_address_line1 or "",
        "recipient_address_line_2": snapshot.get("line2") or customer.shipping_address_line2 or "",
        "recipient_house_number": snapshot.get("house_number") or "",
        "parcel_weight_value": "1.0",
    }


def build_shipment_payload(submitted_data) -> dict[str, object]:
    return {
        "recipient": {
            "name": submitted_data.get("recipient_name", ""),
            "address_line_1": submitted_data.get("recipient_address_line_1", ""),
            "house_number": submitted_data.get("recipient_house_number", ""),
            "postal_code": submitted_data.get("recipient_postal_code", ""),
            "city": submitted_data.get("recipient_city", ""),
            "country_code": submitted_data.get("recipient_country_code", ""),
            "email": submitted_data.get("recipient_email", ""),
            "company_name": submitted_data.get("recipient_company_name", ""),
            "address_line_2": submitted_data.get("recipient_address_line_2", ""),
            "phone_number": submitted_data.get("recipient_phone_number", ""),
        },
        "parcel": {
            "weight": {
                "value": submitted_data.get("parcel_weight_value", ""),
                "unit": "kg",
            }
        },
    }
