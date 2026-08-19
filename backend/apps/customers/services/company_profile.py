from __future__ import annotations

import re
from dataclasses import dataclass

from django.db import transaction

from apps.auditlog.services import record_event
from apps.customers.models import Customer

COMPANY_PROFILE_FIELDS = (
    "name",
    "billing_email",
    "siren",
    "vat_number",
    "billing_address_line1",
    "billing_address_line2",
    "billing_postal_code",
    "billing_city",
    "billing_country",
    "shipping_address_line1",
    "shipping_address_line2",
    "shipping_postal_code",
    "shipping_city",
    "shipping_country",
)

COUNTRY_LABELS = {
    "FR": "France",
    "BE": "Belgique",
    "CH": "Suisse",
    "DE": "Allemagne",
    "ES": "Espagne",
    "IT": "Italie",
    "NL": "Pays-Bas",
    "LU": "Luxembourg",
    "AT": "Autriche",
    "PT": "Portugal",
    "GB": "Royaume-Uni",
    "MA": "Maroc",
    "TN": "Tunisie",
    "CA": "Canada",
    "US": "États-Unis",
    "ZZ": "Autre pays",
}


def country_label(code: str) -> str:
    normalized = (code or "").strip().upper()
    if not normalized:
        return ""
    return COUNTRY_LABELS.get(normalized, normalized)


def format_customer_address(customer: Customer, *, kind: str) -> str:
    prefix = "billing" if kind == "billing" else "shipping"
    line1 = (getattr(customer, f"{prefix}_address_line1") or "").strip()
    line2 = (getattr(customer, f"{prefix}_address_line2") or "").strip()
    postal = (getattr(customer, f"{prefix}_postal_code") or "").strip()
    city = (getattr(customer, f"{prefix}_city") or "").strip()
    country = country_label(getattr(customer, f"{prefix}_country") or "")
    locality = " ".join(part for part in (postal, city) if part)
    parts = [part for part in (line1, line2, locality, country) if part]
    return "\n".join(parts)


def shipping_same_as_billing(customer: Customer) -> bool:
    shipping_lines = [
        (getattr(customer, field) or "").strip()
        for field in (
            "shipping_address_line1",
            "shipping_address_line2",
            "shipping_postal_code",
            "shipping_city",
        )
    ]
    if not any(shipping_lines):
        return True
    pairs = (
        ("billing_address_line1", "shipping_address_line1"),
        ("billing_address_line2", "shipping_address_line2"),
        ("billing_postal_code", "shipping_postal_code"),
        ("billing_city", "shipping_city"),
        ("billing_country", "shipping_country"),
    )
    return all(
        (getattr(customer, left) or "").strip() == (getattr(customer, right) or "").strip()
        for left, right in pairs
    )


@dataclass(frozen=True)
class CompanyProfilePresentation:
    name: str
    billing_email: str
    siren: str
    vat_number: str
    billing_address: str
    shipping_address: str
    shipping_same_as_billing: bool


class CompanyProfileService:
    def present(self, customer: Customer) -> CompanyProfilePresentation:
        same = shipping_same_as_billing(customer)
        shipping_address = format_customer_address(customer, kind="shipping")
        return CompanyProfilePresentation(
            name=(customer.name or "").strip(),
            billing_email=(customer.billing_email or "").strip(),
            siren=(customer.siren or "").strip(),
            vat_number=(customer.vat_number or "").strip(),
            billing_address=format_customer_address(customer, kind="billing"),
            shipping_address="" if same else shipping_address,
            shipping_same_as_billing=same,
        )

    @transaction.atomic
    def update(
        self,
        *,
        customer: Customer,
        cleaned_data: dict,
        actor,
    ) -> Customer:
        locked = Customer.objects.select_for_update().get(pk=customer.pk)
        values = {field: cleaned_data[field] for field in COMPANY_PROFILE_FIELDS}
        changed_fields = [
            field_name
            for field_name, value in values.items()
            if getattr(locked, field_name) != value
        ]
        if not changed_fields:
            return locked

        for field_name in changed_fields:
            setattr(locked, field_name, values[field_name])
        locked.save(update_fields=[*changed_fields, "updated_at"])
        record_event(
            action="customer.company_profile.updated",
            actor=actor,
            target=locked,
            metadata={
                "customer_public_id": str(locked.public_id),
                "fields": changed_fields,
            },
        )
        return locked


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def compact_vat(value: str) -> str:
    return re.sub(r"[\s.\-]", "", value or "").upper()
