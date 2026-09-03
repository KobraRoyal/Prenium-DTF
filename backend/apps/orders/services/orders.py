from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import CharField, Q
from django.db.models.functions import Cast

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
            .select_related(
                "customer",
                "created_by",
                "source_b2b_order_project",
                "production_job",
                "shipment",
            )
            .prefetch_related("items", "items__service", "uploads")
            .order_by("-created_at")
        )

    def get_customer_order(self, customer, order_public_id):
        return (
            Order.objects.for_customer(customer)
            .select_related("customer", "created_by", "source_b2b_order_project", "shipment")
            .prefetch_related("items", "items__service", "uploads", "uploads__inspection")
            .filter(public_id=order_public_id)
            .first()
        )

    def list_staff_orders(self, *, include_cancelled: bool = False):
        queryset = Order.objects.select_related(
            "customer",
            "created_by",
            "source_b2b_order_project",
            "production_job",
            "shipment",
        ).prefetch_related(
            "items",
            "items__service",
        )
        if not include_cancelled:
            queryset = queryset.exclude(status=Order.Status.CANCELLED)
        return queryset.order_by("-created_at")

    def get_staff_order(self, order_public_id):
        return (
            Order.objects.select_related(
                "customer",
                "created_by",
                "cancelled_by",
                "source_b2b_order_project",
            )
            .prefetch_related(
                "items",
                "items__service",
                "uploads",
                "uploads__inspection",
                "uploads__atelier_review",
                "uploads__drive_sync",
            )
            .filter(public_id=order_public_id)
            .first()
        )

    def update_estimated_handover_date(
        self,
        *,
        order_public_id,
        value: date | str | None,
        actor,
        source: str,
    ) -> Order | None:
        """Update the staff-managed client handover date with an audit trail."""
        if isinstance(value, date):
            normalized_date = value
        elif value is None or not str(value).strip():
            normalized_date = None
        else:
            try:
                normalized_date = date.fromisoformat(str(value).strip())
            except ValueError as exc:
                raise ValidationError("La date prévisionnelle est invalide.") from exc

        with transaction.atomic():
            order = (
                Order.objects.select_for_update()
                .select_related("customer")
                .filter(public_id=order_public_id)
                .first()
            )
            if order is None:
                return None
            previous_date = order.estimated_handover_date
            if previous_date == normalized_date:
                return order
            order.estimated_handover_date = normalized_date
            order.save(update_fields=("estimated_handover_date", "updated_at"))
            record_event(
                action="order.estimated_handover_date_updated",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=order,
                metadata={
                    "customer_public_id": str(order.customer.public_id),
                    "order_public_id": str(order.public_id),
                    "previous_date": previous_date.isoformat() if previous_date else None,
                    "estimated_handover_date": (
                        normalized_date.isoformat() if normalized_date else None
                    ),
                    "shipping_method_code": order.shipping_method_code,
                    "source": source,
                },
            )
        return order

    def staff_delete_block_reason(self, order: Order) -> str | None:
        """Motif métier empêchant la suppression Atelier, ou None si autorisée."""
        if order.status == Order.Status.CANCELLED:
            return "Cette commande est déjà supprimée de la file Atelier."
        if order.billing_statement_id is not None:
            return (
                "Impossible de supprimer : la commande appartient déjà à un "
                "récapitulatif de facturation."
            )

        from apps.billing.models import Invoice, Payment
        from apps.production.models import ProductionJob
        from apps.shipping.models import Shipment

        if Payment.objects.filter(
            order_id=order.pk,
            status=Payment.Status.CAPTURED,
        ).exists():
            return "Impossible de supprimer : un paiement a déjà été capturé."

        if Payment.objects.filter(
            order_id=order.pk,
            status__in={Payment.Status.PENDING, Payment.Status.APPROVED},
        ).exists():
            return "Impossible de supprimer : un paiement en ligne est encore en cours."

        if Invoice.objects.filter(order_id=order.pk).exists():
            return "Impossible de supprimer : un justificatif ou une facture existe déjà."

        try:
            production_job = order.production_job
        except ProductionJob.DoesNotExist:
            production_job = None
        if production_job is not None and production_job.status != ProductionJob.Status.QUEUED:
            return (
                "Impossible de supprimer : la production a déjà démarré "
                f"({production_job.get_status_display()})."
            )
        if production_job is not None and production_job.started_at is not None:
            return "Impossible de supprimer : la production a déjà démarré."

        if Shipment.objects.filter(order_id=order.pk).exists():
            return "Impossible de supprimer : une expédition est déjà associée."

        return None

    def can_staff_delete_order(self, order: Order) -> bool:
        return self.staff_delete_block_reason(order) is None

    def delete_staff_order(
        self,
        *,
        order_public_id,
        actor,
        source: str,
        reason: str = "",
    ) -> Order:
        """Retire la commande de la file Atelier (soft-cancel), sans hard-delete."""
        cleaned_reason = str(reason or "").strip()[:255]
        order = Order.objects.select_related("customer").filter(public_id=order_public_id).first()
        if order is None:
            raise ValidationError("Commande introuvable.")

        block_reason = self.staff_delete_block_reason(order)
        if block_reason is not None:
            record_event(
                action="order.delete_rejected",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=order,
                metadata={
                    "order_public_id": str(order.public_id),
                    "customer_public_id": str(order.customer.public_id),
                    "reason": block_reason,
                    "source": source,
                },
            )
            raise ValidationError(block_reason)

        with transaction.atomic():
            order = (
                Order.objects.select_for_update()
                .select_related("customer")
                .filter(public_id=order_public_id)
                .first()
            )
            if order is None:
                raise ValidationError("Commande introuvable.")

            block_reason = self.staff_delete_block_reason(order)
            if block_reason is not None:
                raise ValidationError(block_reason)

            from django.utils import timezone

            from apps.billing.models import Payment

            now = timezone.now()
            previous_status = order.status
            order.status = Order.Status.CANCELLED
            order.cancelled_at = now
            order.cancelled_by = actor if getattr(actor, "is_authenticated", False) else None
            order.cancellation_reason = cleaned_reason
            order.save(
                update_fields=[
                    "status",
                    "cancelled_at",
                    "cancelled_by",
                    "cancellation_reason",
                    "updated_at",
                ]
            )
            Payment.objects.filter(
                order_id=order.pk,
                status__in={Payment.Status.PENDING, Payment.Status.APPROVED},
            ).update(status=Payment.Status.CANCELLED, updated_at=now)

            record_event(
                action="order.deleted_atelier",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=order,
                metadata={
                    "order_public_id": str(order.public_id),
                    "customer_public_id": str(order.customer.public_id),
                    "cancellation_reason": cleaned_reason,
                    "source": source,
                    "previous_status": previous_status,
                },
            )

        if (
            order.billing_mode == Order.BillingMode.DEFERRED
            and order.pricing_status == Order.PricingStatus.PRICED
        ):
            from apps.orders.services.pricing import OrderPricingService

            OrderPricingService().reprice_deferred_month(
                customer=order.customer,
                month=timezone.localtime(order.created_at).date(),
                actor=actor,
                source=f"{source}.order_cancelled",
            )

        return self.get_staff_order(order_public_id)

    def paginate_orders(self, queryset, *, page_number, page_size):
        paginator = Paginator(queryset, page_size)
        return paginator.get_page(page_number)

    def filter_customer_orders(self, queryset, *, query: str):
        cleaned = str(query or "").strip()
        if not cleaned:
            return queryset

        filters = (
            Q(customer_note__icontains=cleaned)
            | Q(source_b2b_order_project__name__icontains=cleaned)
            | Q(source_b2b_order_project__customer_reference__icontains=cleaned)
            | Q(source_b2b_order_project__project_number__icontains=cleaned)
        )

        normalized = cleaned.replace("-", "").replace(" ", "").lower()
        if normalized:
            filters |= Q(
                public_id_text__icontains=normalized,
            )

        lowered = cleaned.lower()
        status_aliases = {
            "soumise": Order.Status.SUBMITTED,
            "submitted": Order.Status.SUBMITTED,
            "brouillon": Order.Status.DRAFT,
            "draft": Order.Status.DRAFT,
        }
        if lowered in status_aliases:
            filters |= Q(status=status_aliases[lowered])

        return queryset.annotate(
            public_id_text=Cast("public_id", CharField(max_length=36)),
        ).filter(filters)

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
        billing_mode: str | None = None,
        shipping_method_code: str | None = None,
    ) -> Order:
        validated_membership = self._validate_customer_actor_scope(
            customer=customer,
            actor=actor,
            customer_membership=customer_membership,
        )
        resolved_mode = self._resolve_b2b_billing_mode_for_customer(
            customer=customer,
            billing_mode=billing_mode,
        )
        from apps.shipping.services.methods import ShippingMethodService

        shipping_service = ShippingMethodService()
        shipping_method = shipping_service.resolve_method_for_customer(
            customer=customer,
            shipping_method_code=shipping_method_code,
        )
        shipping_snap = shipping_service.snapshot_dict(shipping_method)

        with transaction.atomic():
            order = Order.objects.create(
                customer=customer,
                created_by=actor if getattr(actor, "is_authenticated", False) else None,
                status=Order.Status.DRAFT,
                currency="EUR",
                subtotal_amount=Decimal("0.00"),
                shipping_method_code=str(shipping_snap["shipping_method_code"]),
                shipping_method_name=str(shipping_snap["shipping_method_name"]),
                shipping_amount=shipping_snap["shipping_amount"],
                tax_rate=Decimal("0.00"),
                tax_amount=Decimal("0.00"),
                total_amount=Decimal("0.00"),
                customer_note=customer_note.strip(),
                source=source,
                billing_mode=resolved_mode,
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
                    "billing_mode": resolved_mode,
                    "shipping_method_code": order.shipping_method_code,
                    "shipping_amount": f"{order.shipping_amount:.2f}",
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
        billing_mode: str | None = None,
        shipping_method_code: str | None = None,
    ) -> Order:
        validated_membership = self._validate_customer_actor_scope(
            customer=customer,
            actor=actor,
            customer_membership=customer_membership,
        )
        order = self.get_customer_order(customer, order_public_id)
        if order is None:
            raise ValidationError("Commande introuvable.")
        if not order.uses_atelier_pricing():
            raise ValidationError("Cette commande n'est pas un dépôt atelier B2B.")
        if order.status != Order.Status.DRAFT:
            raise ValidationError("La commande a déjà été soumise.")
        if not order.uploads.exists():
            raise ValidationError("Ajoutez au moins un fichier avant de soumettre.")

        resolved_mode = self._resolve_b2b_billing_mode_for_customer(
            customer=customer,
            billing_mode=billing_mode if billing_mode is not None else order.billing_mode,
        )

        shipping_snap = None
        if shipping_method_code is not None:
            from apps.shipping.services.methods import ShippingMethodService

            method = ShippingMethodService().resolve_method_for_customer(
                customer=customer,
                shipping_method_code=shipping_method_code,
            )
            shipping_snap = ShippingMethodService().snapshot_dict(method)

        with transaction.atomic():
            order_locked = Order.objects.select_for_update().get(pk=order.pk)
            order_locked.status = Order.Status.SUBMITTED
            update_fields = ["status", "updated_at"]
            if order_locked.billing_mode != resolved_mode:
                order_locked.billing_mode = resolved_mode
                update_fields.append("billing_mode")
            if shipping_snap is not None:
                order_locked.shipping_method_code = str(shipping_snap["shipping_method_code"])
                order_locked.shipping_method_name = str(shipping_snap["shipping_method_name"])
                order_locked.shipping_amount = shipping_snap["shipping_amount"]
                update_fields.extend(
                    [
                        "shipping_method_code",
                        "shipping_method_name",
                        "shipping_amount",
                    ]
                )
            order_locked.save(update_fields=update_fields)

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
                    "billing_mode": order_locked.billing_mode,
                    "shipping_method_code": order_locked.shipping_method_code,
                },
            )

            from apps.billing.services.production_payment_gate import (
                should_defer_order_created_until_payment,
            )
            from apps.notifications.services.transactional import schedule_order_created_email

            if not should_defer_order_created_until_payment(order_locked):
                schedule_order_created_email(order_public_id=order_locked.public_id)

        return self.get_customer_order(customer, order_locked.public_id)

    @classmethod
    def _resolve_b2b_billing_mode_for_customer(
        cls,
        *,
        customer,
        billing_mode: str | None,
    ) -> str:
        """Applique le verrou compte : comptant CB interdit l'encours."""
        account_default = getattr(
            customer,
            "default_billing_mode",
            Order.BillingMode.DEFERRED,
        )
        if account_default == Order.BillingMode.IMMEDIATE:
            if billing_mode is not None:
                requested = cls._normalize_b2b_billing_mode(billing_mode)
                if requested != Order.BillingMode.IMMEDIATE:
                    raise ValidationError(
                        "Ce compte est en règlement comptant carte bancaire : "
                        "l’encours n’est pas disponible."
                    )
            return Order.BillingMode.IMMEDIATE
        if billing_mode is None:
            return cls._normalize_b2b_billing_mode(account_default)
        return cls._normalize_b2b_billing_mode(billing_mode)

    @staticmethod
    def _normalize_b2b_billing_mode(billing_mode: str) -> str:
        value = str(billing_mode or "").strip().lower()
        if value in {Order.BillingMode.DEFERRED, "encours", "deferred_credit"}:
            return Order.BillingMode.DEFERRED
        if value in {Order.BillingMode.IMMEDIATE, "card", "carte", "cb", "stripe"}:
            return Order.BillingMode.IMMEDIATE
        raise ValidationError(
            "Choisissez un mode de règlement : encours ou paiement comptant par carte bancaire."
        )

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
