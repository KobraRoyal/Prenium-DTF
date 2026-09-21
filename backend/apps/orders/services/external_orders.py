"""Création de commandes dont le visuel est transmis par un lien client."""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.services.access import AccessScopeService
from apps.auditlog.services import record_event
from apps.b2b_order_projects.models import B2BOrderProject
from apps.b2b_order_projects.services.numbering import B2BOrderProjectNumberService
from apps.orders.models import Order
from apps.orders.services.orders import OrderService
from apps.orders.services.pricing import OrderPricingService
from apps.shipping.services.methods import ShippingMethodService
from apps.uploads.models import OrderUpload
from apps.uploads.validators import normalize_external_visual_count, validate_external_url


class ExternalOrderService:
    """One external link represents one manual print order."""

    @staticmethod
    def validate_external_url(value: str) -> str:
        return validate_external_url(value)

    @staticmethod
    def _meterage(value) -> Decimal:
        try:
            meterage = Decimal(str(value).strip())
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationError("Le métrage doit être un nombre positif.") from exc
        if not meterage.is_finite() or meterage <= 0 or meterage.as_tuple().exponent < -4:
            raise ValidationError("Le métrage doit être positif avec 4 décimales maximum.")
        if meterage >= Decimal("100000000"):
            raise ValidationError("Le métrage est trop élevé.")
        return meterage

    @staticmethod
    def _optional_meterage(value) -> Decimal | None:
        if value in (None, ""):
            return None
        return ExternalOrderService._meterage(value)

    @staticmethod
    def _name(value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned or len(cleaned) > 255:
            raise ValidationError("Indiquez un libellé de fichier (255 caractères maximum).")
        return cleaned

    def create_client_order(
        self,
        *,
        customer,
        actor,
        name,
        external_url,
        customer_note: str = "",
        shipping_method_code: str | None = None,
        source: str = "client_portal",
    ) -> Order:
        membership = OrderService()._validate_customer_actor_scope(
            customer=customer,
            actor=actor,
        )
        if (
            OrderService._resolve_b2b_billing_mode_for_customer(
                customer=customer,
                billing_mode=None,
            )
            == Order.BillingMode.IMMEDIATE
        ):
            raise ValidationError(
                "Le dépôt par lien n'est pas disponible pour les commandes au paiement immédiat."
            )
        return self._create(
            customer=customer,
            actor=actor,
            name=name,
            external_url=external_url,
            customer_note=customer_note,
            shipping_method_code=shipping_method_code,
            meterage=None,
            membership=membership,
            source=source,
        )

    def create_staff_order(
        self,
        *,
        customer,
        actor,
        name,
        external_url,
        meterage_linear_m=None,
        external_visual_count=1,
        customer_note: str = "",
        shipping_method_code: str | None = None,
        source: str = "staff_portal",
    ) -> Order:
        access = AccessScopeService()
        if not all(
            access.can_access_staff_domain(actor, permission)
            for permission in ("orders.add_order", "orders.change_order", "orders.view_order")
        ):
            raise ValidationError("Vous n'êtes pas autorisé à créer cette commande.")
        if customer is None or not customer.is_active:
            raise ValidationError("Le compte client est inactif.")
        meterage = self._optional_meterage(meterage_linear_m)
        return self._create(
            customer=customer,
            actor=actor,
            name=name,
            external_url=external_url,
            customer_note=customer_note,
            shipping_method_code=shipping_method_code,
            meterage=meterage,
            external_visual_count=normalize_external_visual_count(external_visual_count),
            membership=None,
            source=source,
            assign_business_number=True,
        )

    def _attach_cmd_number(
        self, *, order: Order, actor, name: str, shipping_method_code: str
    ) -> None:
        """Attribue un N° CMD- via un projet B2B coquille déjà converti."""
        try:
            if order.source_b2b_order_project is not None:
                return
        except ObjectDoesNotExist:
            pass
        now = timezone.now()
        B2BOrderProject.objects.create(
            customer=order.customer,
            created_by=actor,
            project_number=B2BOrderProjectNumberService().next_number(),
            name=name,
            order_mode=B2BOrderProject.OrderMode.INDIVIDUAL_DESIGNS,
            status=B2BOrderProject.Status.CONVERTED,
            delivery_method=str(shipping_method_code or "").strip(),
            converted_order=order,
            converted_at=now,
            submitted_at=now,
            confirmed_at=now,
        )

    def _create(
        self,
        *,
        customer,
        actor,
        name,
        external_url,
        customer_note,
        shipping_method_code,
        meterage,
        membership,
        source,
        external_visual_count=1,
        assign_business_number: bool = False,
    ) -> Order:
        cleaned_name = self._name(name)
        cleaned_url = self.validate_external_url(external_url)
        billing_mode = OrderService._resolve_b2b_billing_mode_for_customer(
            customer=customer,
            billing_mode=None,
        )
        shipping_service = ShippingMethodService()
        method = shipping_service.resolve_method_for_customer(
            customer=customer,
            shipping_method_code=shipping_method_code,
        )
        shipping = shipping_service.snapshot_dict(method)
        with transaction.atomic():
            order = Order.objects.create(
                customer=customer,
                created_by=actor,
                status=Order.Status.DRAFT,
                source=source,
                customer_note="\n".join(
                    part for part in (cleaned_name, str(customer_note or "").strip()) if part
                ),
                billing_mode=billing_mode,
                pricing_status=Order.PricingStatus.PENDING,
                credit_hold_status=Order.CreditHoldStatus.NONE,
                shipping_method_code=str(shipping["shipping_method_code"]),
                shipping_method_name=str(shipping["shipping_method_name"]),
                shipping_amount=shipping["shipping_amount"],
                meterage_override_linear_m=meterage,
            )
            upload = OrderUpload.objects.create(
                order=order,
                uploaded_by=actor,
                file="",
                external_url=cleaned_url,
                external_visual_count=external_visual_count,
                original_filename=cleaned_name,
                mime_type="",
                size_bytes=0,
                sort_order=1,
            )
            order.status = Order.Status.SUBMITTED
            order.save(update_fields=["status", "updated_at"])

            if assign_business_number:
                self._attach_cmd_number(
                    order=order,
                    actor=actor,
                    name=cleaned_name,
                    shipping_method_code=str(shipping["shipping_method_code"]),
                )

            if meterage is not None:
                OrderPricingService().compute_and_persist_order_pricing(
                    order=order,
                    actor=actor,
                    source=source,
                )
                order.refresh_from_db()

            from apps.production.services.workflow import ProductionWorkflowService

            ProductionWorkflowService().get_or_create_for_order(order=order)
            metadata = {
                "customer_public_id": str(customer.public_id),
                "order_public_id": str(order.public_id),
                "order_upload_public_id": str(upload.public_id),
                "billing_mode": billing_mode,
                "source": source,
                "meterage_linear_m": str(meterage) if meterage is not None else None,
                "external_visual_count": external_visual_count,
                "shipping_method_code": str(shipping["shipping_method_code"]),
            }
            if membership is not None:
                metadata["customer_membership_public_id"] = str(membership.public_id)
            record_event(
                action="order.external_created",
                actor=actor,
                target=order,
                metadata=metadata,
            )

            from apps.billing.services.production_payment_gate import (
                should_defer_order_created_until_payment,
            )
            from apps.notifications.services.transactional import schedule_order_created_email
            from apps.notifications.services.workshop_push import WorkshopNotificationService

            if not should_defer_order_created_until_payment(order):
                schedule_order_created_email(order_public_id=order.public_id)
            WorkshopNotificationService().publish_order_submitted(
                order=order,
                actor=actor,
                source=source,
            )
        return order
