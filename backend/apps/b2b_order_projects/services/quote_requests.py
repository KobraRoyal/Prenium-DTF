"""Demandes de devis sans commande, jusqu’à la validation client."""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.b2b_order_projects.models import B2BOrderProject
from apps.b2b_order_projects.services.projects import B2BOrderProjectService
from apps.customers.services.volume_discounts import sqm_from_linear_meters
from apps.orders.services.external_orders import ExternalOrderService
from apps.orders.services.pricing import OrderPricingService

PLACEHOLDER_MM = Decimal("10.00")
MAX_METERAGE_M = Decimal("10000")


def quote_visual_lines(project) -> str:
    lines = [f"- {item.name} × {item.quantity}" for item in project.items.all()]
    return "\n".join(lines) or "- Aucun visuel indiqué"


def open_quote_requests():
    return (
        B2BOrderProject.objects.filter(
            price_confirmation_required=True,
            converted_order__isnull=True,
        )
        .exclude(
            status__in=(
                B2BOrderProject.Status.CANCELLED,
                B2BOrderProject.Status.CONVERTED,
            )
        )
        .select_related("customer")
        .prefetch_related("items")
        .order_by("-updated_at")
    )


def get_open_quote_request(*, project_public_id):
    return open_quote_requests().filter(public_id=project_public_id).first()


@transaction.atomic
def create_link_quote(*, customer, actor, cleaned_data: dict, shipping_method_code: str | None):
    visuals = list(cleaned_data.get("visuals") or [])
    if not visuals:
        raise ValidationError("Ajoutez au moins un visuel au lien.")
    service = B2BOrderProjectService()
    project = service.create_project(
        customer=customer,
        actor=actor,
        data={
            "name": cleaned_data.get("name") or "Commande par lien",
            "order_mode": B2BOrderProject.OrderMode.INDIVIDUAL_DESIGNS,
            "requested_date": cleaned_data.get("requested_date"),
            "delivery_method": (shipping_method_code or "").strip(),
            "customer_comment": cleaned_data.get("customer_note")
            or cleaned_data.get("project_comment")
            or "",
        },
        source="client_portal.link_quote",
    )
    for visual in visuals:
        service.add_item(
            project=project,
            actor=actor,
            data={
                "name": visual.get("file_name") or "Visuel",
                "width_mm": PLACEHOLDER_MM,
                "height_mm": PLACEHOLDER_MM,
                "quantity": visual.get("quantity") or 1,
                "support_color_hex": visual.get("support_color_hex") or "",
            },
            source="client_portal.link_quote",
        )
    project.external_url = cleaned_data["external_url"]
    project.price_confirmation_required = True
    project.save(update_fields=["external_url", "price_confirmation_required", "updated_at"])
    record_event(
        action="b2b_order_project.link_quote_requested",
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        target=project,
        metadata={
            "customer_public_id": str(customer.public_id),
            "project_public_id": str(project.public_id),
            "shipping_method_code": project.delivery_method,
            "visual_count": len(visuals),
        },
    )
    from apps.notifications.services.transactional import schedule_quote_requested_emails

    schedule_quote_requested_emails(project_public_id=project.public_id)
    return project


def parse_meterage(raw) -> Decimal:
    try:
        value = Decimal(str(raw or "").replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        raise ValidationError("Indiquez un métrage en mètres.") from None
    if value <= 0 or value > MAX_METERAGE_M:
        raise ValidationError("Indiquez un métrage en mètres, supérieur à zéro.")
    return value.quantize(Decimal("0.0001"))


def price_quote_from_meterage(*, project, meterage_linear_m: Decimal):
    file_count = max(project.items.count(), 1)
    surface = sqm_from_linear_meters(meterage_linear_m)
    return OrderPricingService().estimate_gang_sheet_quote(
        customer=project.customer,
        surface_sqm=surface,
        quantity=1,
        file_count=file_count,
        shipping_method_code=project.delivery_method or None,
        billing_mode=project.customer.default_billing_mode,
    )


@transaction.atomic
def price_quote_request(*, project, actor, raw_meterage: str):
    locked = B2BOrderProject.objects.select_for_update().get(pk=project.pk)
    if locked.converted_order_id or not locked.price_confirmation_required:
        raise ValidationError("Cette demande de devis n’est plus ouverte.")
    meterage = parse_meterage(raw_meterage)
    quote = price_quote_from_meterage(project=locked, meterage_linear_m=meterage)
    locked.quote_meterage_linear_m = meterage
    locked.quote_priced_at = timezone.now()
    locked.estimated_subtotal = quote["subtotal_eur"]
    locked.estimated_tax = quote["tax_amount_eur"]
    locked.estimated_total = quote["total_eur"]
    locked.estimated_length_mm = int((meterage * Decimal("1000")).quantize(Decimal("1")))
    if quote.get("shipping_method_code"):
        locked.delivery_method = quote["shipping_method_code"]
    locked.save(
        update_fields=[
            "quote_meterage_linear_m",
            "quote_priced_at",
            "estimated_subtotal",
            "estimated_tax",
            "estimated_total",
            "estimated_length_mm",
            "delivery_method",
            "updated_at",
        ]
    )
    record_event(
        action="b2b_order_project.quote_priced",
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        target=locked,
        metadata={
            "customer_public_id": str(locked.customer.public_id),
            "project_public_id": str(locked.public_id),
            "meterage_linear_m": f"{meterage:.4f}",
            "total_ht": f"{quote['total_eur']:.2f}",
        },
    )
    from apps.notifications.services.transactional import schedule_quote_priced_email

    schedule_quote_priced_email(project_public_id=locked.public_id)
    return locked


def apply_validated_quote_meterage(*, order, project, actor, source: str):
    if not project.quote_meterage_linear_m:
        return order
    if project.order_mode != B2BOrderProject.OrderMode.INDIVIDUAL_DESIGNS:
        return order
    order.meterage_override_linear_m = project.quote_meterage_linear_m
    order.save(update_fields=["meterage_override_linear_m", "updated_at"])
    return OrderPricingService().compute_and_persist_order_pricing(
        order=order,
        actor=actor,
        source=f"{source}.quote_meterage",
    )


@transaction.atomic
def accept_link_quote(*, project, customer, actor):
    locked = (
        B2BOrderProject.objects.select_for_update().select_related("customer").get(pk=project.pk)
    )
    if locked.customer_id != customer.id or not locked.external_url:
        raise ValidationError("Cette demande ne peut pas être validée.")
    if locked.converted_order_id:
        return locked.converted_order
    if not locked.quote_priced_at or not locked.quote_meterage_linear_m:
        raise ValidationError("Le devis n’est pas encore tarifé.")
    visuals = [
        {
            "file_name": item.name,
            "quantity": item.quantity,
            "support_color_hex": item.support_color_hex,
        }
        for item in locked.items.all()
    ]
    order = ExternalOrderService().create_client_order(
        customer=customer,
        actor=actor,
        name=locked.name,
        external_url=locked.external_url,
        customer_note=locked.customer_comment,
        shipping_method_code=locked.delivery_method or None,
        source="client_portal.link_quote_accept",
        visuals=visuals,
        requested_date=locked.requested_date,
    )
    order = apply_validated_quote_meterage(
        order=order,
        project=locked,
        actor=actor,
        source="client_portal.link_quote_accept",
    )
    shadow = B2BOrderProject.objects.filter(converted_order=order).exclude(pk=locked.pk).first()
    if shadow is not None:
        shadow.converted_order = None
        shadow.save(update_fields=["converted_order", "updated_at"])
        shadow.delete()
    now = timezone.now()
    locked.converted_order = order
    locked.converted_at = now
    locked.submitted_at = now
    locked.status = B2BOrderProject.Status.CONVERTED
    locked.save(
        update_fields=[
            "converted_order",
            "converted_at",
            "submitted_at",
            "status",
            "updated_at",
        ]
    )
    record_event(
        action="b2b_order_project.quote_accepted",
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        target=locked,
        metadata={
            "customer_public_id": str(customer.public_id),
            "project_public_id": str(locked.public_id),
            "order_public_id": str(order.public_id),
        },
    )
    return order


def quote_request_is_waiting(project) -> bool:
    return bool(
        project.price_confirmation_required
        and not project.quote_priced_at
        and not project.converted_order_id
        and project.order_mode == B2BOrderProject.OrderMode.INDIVIDUAL_DESIGNS
    )
