from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction

from apps.accounts.services.access import AccessScopeService
from apps.auditlog.services import record_event
from apps.catalog.services.catalog import CatalogQueryService
from apps.catalog.services.pricing import PricingService
from apps.orders.models import Order, OrderLine


@dataclass(frozen=True)
class OrderLineInput:
    service_public_id: str
    quantity: object


class OrderService:
    def __init__(self):
        self.access_scope_service = AccessScopeService()
        self.catalog_query_service = CatalogQueryService()
        self.pricing_service = PricingService()

    def list_customer_orders(self, customer):
        return (
            Order.objects.for_customer(customer)
            .select_related("customer", "created_by")
            .prefetch_related("items", "items__service")
            .order_by("-created_at")
        )

    def get_customer_order(self, customer, order_public_id):
        return (
            Order.objects.for_customer(customer)
            .select_related("customer", "created_by")
            .prefetch_related("items", "items__service", "uploads", "uploads__inspection")
            .filter(public_id=order_public_id)
            .first()
        )

    def list_staff_orders(self):
        return (
            Order.objects.select_related("customer", "created_by")
            .prefetch_related("items", "items__service")
            .order_by("-created_at")
        )

    def get_staff_order(self, order_public_id):
        return (
            Order.objects.select_related("customer", "created_by")
            .prefetch_related("items", "items__service", "uploads", "uploads__inspection")
            .filter(public_id=order_public_id)
            .first()
        )

    def paginate_orders(self, queryset, *, page_number, page_size):
        paginator = Paginator(queryset, page_size)
        return paginator.get_page(page_number)

    def create_order(
        self,
        *,
        customer,
        actor,
        items,
        customer_note: str = "",
        customer_membership=None,
        source: str = "client_api",
    ) -> Order:
        validated_membership = self._validate_customer_actor_scope(
            customer=customer,
            actor=actor,
            customer_membership=customer_membership,
        )

        line_inputs = self._normalize_items(items)
        service_map = self.catalog_query_service.get_active_service_map(
            [line.service_public_id for line in line_inputs]
        )

        if len(service_map) != len({line.service_public_id for line in line_inputs}):
            raise ValidationError("One or more services are unavailable.")

        priced_lines = []
        currencies = set()
        for line_input in line_inputs:
            service = service_map[line_input.service_public_id]
            quote = self.pricing_service.price_service(service, line_input.quantity)
            priced_lines.append(quote)
            currencies.add(service.currency)

        if len(currencies) != 1:
            raise ValidationError("All order lines must use the same currency.")

        currency = currencies.pop()
        subtotal = sum((quote.line_total for quote in priced_lines), Decimal("0.00"))

        with transaction.atomic():
            order = Order.objects.create(
                customer=customer,
                created_by=actor if getattr(actor, "is_authenticated", False) else None,
                status=Order.Status.SUBMITTED,
                currency=currency,
                subtotal_amount=subtotal,
                total_amount=subtotal,
                customer_note=customer_note.strip(),
                source=source,
                billing_mode=Order.BillingMode.IMMEDIATE,
                pricing_status=Order.PricingStatus.PRICED,
                credit_hold_status=Order.CreditHoldStatus.NONE,
            )

            OrderLine.objects.bulk_create(
                [
                    OrderLine(
                        order=order,
                        service=quote.service,
                        position=index,
                        service_code=quote.service.code,
                        service_name=quote.service.name,
                        service_type=quote.service.service_type,
                        unit=quote.service.unit,
                        quantity=quote.quantity,
                        unit_price=quote.unit_price,
                        line_total=quote.line_total,
                    )
                    for index, quote in enumerate(priced_lines, start=1)
                ]
            )

            from apps.production.services.workflow import ProductionWorkflowService

            ProductionWorkflowService().get_or_create_for_order(order=order)

            record_event(
                action="order.created",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=order,
                metadata={
                    "customer_public_id": str(customer.public_id),
                    "customer_membership_public_id": str(validated_membership.public_id),
                    "item_count": len(priced_lines),
                    "currency": currency,
                    "source": source,
                },
            )

            from apps.notifications.services.transactional import schedule_order_created_email

            schedule_order_created_email(order_public_id=order.public_id)

        return self.get_customer_order(customer, order.public_id)

    def create_b2b_deferred_order(
        self,
        *,
        customer,
        actor,
        customer_note: str = "",
        customer_membership=None,
        source: str = "client_portal",
    ) -> Order:
        validated_membership = self._validate_customer_actor_scope(
            customer=customer,
            actor=actor,
            customer_membership=customer_membership,
        )

        with transaction.atomic():
            order = Order.objects.create(
                customer=customer,
                created_by=actor if getattr(actor, "is_authenticated", False) else None,
                status=Order.Status.DRAFT,
                currency="EUR",
                subtotal_amount=Decimal("0.00"),
                total_amount=Decimal("0.00"),
                customer_note=customer_note.strip(),
                source=source,
                billing_mode=Order.BillingMode.DEFERRED,
                pricing_status=Order.PricingStatus.PENDING,
                credit_hold_status=Order.CreditHoldStatus.NONE,
            )

            record_event(
                action="order.created_b2b_deferred",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=order,
                metadata={
                    "customer_public_id": str(customer.public_id),
                    "customer_membership_public_id": str(validated_membership.public_id),
                    "source": source,
                },
            )

        return self.get_customer_order(customer, order.public_id)

    def submit_b2b_deferred_order(
        self,
        *,
        customer,
        actor,
        order_public_id,
        customer_membership=None,
        source: str = "client_portal",
    ) -> Order:
        validated_membership = self._validate_customer_actor_scope(
            customer=customer,
            actor=actor,
            customer_membership=customer_membership,
        )
        order = self.get_customer_order(customer, order_public_id)
        if order is None:
            raise ValidationError("Commande introuvable.")
        if order.billing_mode != Order.BillingMode.DEFERRED:
            raise ValidationError("Cette commande n'est pas en facturation différée.")
        if order.status != Order.Status.DRAFT:
            raise ValidationError("La commande a déjà été soumise.")
        if not order.uploads.exists():
            raise ValidationError("Ajoutez au moins un fichier avant de soumettre.")

        with transaction.atomic():
            order_locked = Order.objects.select_for_update().get(pk=order.pk)
            order_locked.status = Order.Status.SUBMITTED
            order_locked.save(update_fields=["status", "updated_at"])

            from apps.production.services.workflow import ProductionWorkflowService

            ProductionWorkflowService().get_or_create_for_order(order=order_locked)

            record_event(
                action="order.submitted_b2b",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=order_locked,
                metadata={
                    "customer_public_id": str(customer.public_id),
                    "customer_membership_public_id": str(validated_membership.public_id),
                    "source": source,
                },
            )

            from apps.notifications.services.transactional import schedule_b2b_order_submitted_email

            schedule_b2b_order_submitted_email(order_public_id=order_locked.public_id)

        return self.get_customer_order(customer, order_locked.public_id)

    def _validate_customer_actor_scope(
        self,
        *,
        customer,
        actor,
        customer_membership=None,
    ):
        if not customer.is_active:
            raise ValidationError("Customer is inactive.")

        membership = self.access_scope_service.get_customer_membership_for_customer(actor, customer)
        if membership is None:
            raise ValidationError("Actor is not allowed for this customer.")

        if customer_membership is not None and membership.pk != customer_membership.pk:
            raise ValidationError("Actor is not allowed for this customer.")

        return membership

    def _normalize_items(self, items) -> list[OrderLineInput]:
        if not isinstance(items, list) or not items:
            raise ValidationError("At least one order item is required.")

        normalized_items: list[OrderLineInput] = []
        for item in items:
            if not isinstance(item, dict):
                raise ValidationError("Each order item must be an object.")

            service_public_id = str(item.get("service_public_id", "")).strip()
            if not service_public_id:
                raise ValidationError("Each order item must include a service_public_id.")

            normalized_items.append(
                OrderLineInput(
                    service_public_id=service_public_id,
                    quantity=item.get("quantity"),
                )
            )

        return normalized_items
