"""Livraison checkout portail — préremplissage fiche client + application POST."""

from __future__ import annotations

from django.core.exceptions import ValidationError

from apps.customers.services.company_profile import (
    COUNTRY_LABELS,
    CompanyProfileService,
    format_customer_address,
    shipping_same_as_billing,
)


def checkout_delivery_context(*, customer, shipping_snapshot: dict | None = None) -> dict:
    """Contexte template partagé (studio + commande au fichier)."""
    defaults = CompanyProfileService().checkout_delivery_defaults(
        customer,
        shipping_snapshot if isinstance(shipping_snapshot, dict) else None,
    )
    return {
        "studio_billing_address": format_customer_address(customer, kind="billing"),
        "studio_shipping_address": format_customer_address(customer, kind="shipping"),
        "studio_shipping_same_as_billing": shipping_same_as_billing(customer),
        "studio_billing_complete": bool(
            (customer.billing_address_line1 or "").strip()
            and (customer.billing_postal_code or "").strip()
            and (customer.billing_city or "").strip()
        ),
        "studio_country_choices": list(COUNTRY_LABELS.items()),
        "studio_shipping_contact_name": defaults["name"],
        "studio_shipping_email": defaults["email"],
        "studio_shipping_phone": defaults["phone"],
        "studio_shipping_company": defaults["company_name"],
        "studio_shipping_house_number": defaults["house_number"],
    }


def apply_checkout_delivery_from_request(
    *,
    request,
    customer,
    source: str,
):
    """Applique l’adresse POST. Retourne (customer, snapshot|None). Skip si retrait."""
    shipping_code = (request.POST.get("shipping_method_code") or "").strip() or None
    from apps.shipping.services.methods import ShippingMethodService

    method = ShippingMethodService().resolve_method_for_customer(
        customer=customer,
        shipping_method_code=shipping_code,
    )
    if getattr(method, "is_pickup", False) or method.code == "pickup":
        return customer, None

    delivery_destination = (request.POST.get("delivery_destination") or "billing").strip().lower()
    same_as_billing = delivery_destination != "other"
    recipient_payload = {
        "name": request.POST.get("shipping_contact_name", ""),
        "email": request.POST.get("shipping_email", ""),
        "phone": request.POST.get("shipping_phone", ""),
        "company_name": request.POST.get("shipping_company_name", ""),
        "house_number": request.POST.get("shipping_house_number", ""),
    }
    delivery_payload = {
        "shipping_address_line1": request.POST.get("shipping_address_line1", ""),
        "shipping_address_line2": request.POST.get("shipping_address_line2", ""),
        "shipping_postal_code": request.POST.get("shipping_postal_code", ""),
        "shipping_city": request.POST.get("shipping_city", ""),
        "shipping_country": request.POST.get("shipping_country", ""),
        "phone": recipient_payload["phone"],
    }
    profile = CompanyProfileService()
    updated = profile.apply_checkout_delivery(
        customer=customer,
        actor=request.user,
        same_as_billing=same_as_billing,
        payload=delivery_payload,
        source=source,
    )
    snapshot = profile.build_checkout_delivery_snapshot(
        customer=updated,
        payload=recipient_payload,
    )
    return updated, snapshot


def persist_project_delivery_snapshot(*, project, snapshot: dict | None) -> None:
    if not snapshot:
        return
    from apps.b2b_order_projects.services.projects import B2BOrderProjectService

    service = B2BOrderProjectService()
    project.shipping_address = service._normalize_shipping_address(snapshot)
    project.save(update_fields=["shipping_address", "updated_at"])


def delivery_error_query(error: ValidationError) -> str:
    codes = [
        getattr(error, "code", None),
        *[getattr(item, "code", None) for item in getattr(error, "error_list", [])],
    ]
    if "delivery_recipient_required" in codes or "delivery_phone_required" in codes:
        return "delivery_recipient_required"
    if "delivery_address_required" in codes:
        return "delivery_address_required"
    return "validation"
