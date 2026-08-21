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


def build_shipment_form_data(*, order, submitted_data=None) -> dict[str, str]:
    if submitted_data is not None:
        return {key: submitted_data.get(key, "") for key in SHIPMENT_FORM_KEYS}
    customer = order.customer
    return {
        "recipient_name": customer.name,
        "recipient_company_name": customer.name,
        "recipient_email": customer.billing_email,
        "recipient_phone_number": "",
        "recipient_country_code": customer.shipping_country or "FR",
        "recipient_city": customer.shipping_city,
        "recipient_postal_code": customer.shipping_postal_code,
        "recipient_address_line_1": customer.shipping_address_line1,
        "recipient_address_line_2": customer.shipping_address_line2,
        "recipient_house_number": "",
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
