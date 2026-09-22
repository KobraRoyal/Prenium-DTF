from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from apps.accounts.services.access import AccessScopeService
from apps.auditlog.services import record_event
from apps.orders.models import Order
from apps.orders.services.pricing import OrderPricingService
from apps.production.models import ProductionJob
from apps.uploads.models import OrderUpload
from apps.uploads.services.drive import OrderUploadDriveSyncService
from apps.uploads.services.inspections import OrderUploadInspectionService
from apps.uploads.services.validation import UploadValidationService

STAFF_UPLOAD_QUANTITY_MAX = 1000


def order_production_has_started(order: Order) -> bool:
    """True dès qu’un job Atelier a démarré (ou dépassé) l’étape « En production »."""
    try:
        job = order.production_job
    except ProductionJob.DoesNotExist:
        return False
    if job.started_at is not None:
        return True
    return job.status in {
        ProductionJob.Status.IN_PROGRESS,
        ProductionJob.Status.READY_TO_SHIP,
        ProductionJob.Status.COMPLETED,
    }


class OrderUploadService:
    def __init__(
        self,
        validation_service: UploadValidationService | None = None,
        inspection_service: OrderUploadInspectionService | None = None,
        drive_sync_service: OrderUploadDriveSyncService | None = None,
    ):
        self.access_scope_service = AccessScopeService()
        self.validation_service = validation_service or UploadValidationService()
        self.inspection_service = inspection_service or OrderUploadInspectionService()
        self.drive_sync_service = drive_sync_service or OrderUploadDriveSyncService()
        self.pricing_service = OrderPricingService()

    def get_customer_order(self, *, customer, order_public_id):
        return (
            Order.objects.for_customer(customer)
            .select_related("customer")
            .filter(public_id=order_public_id)
            .first()
        )

    def get_staff_order(self, *, order_public_id):
        return Order.objects.select_related("customer").filter(public_id=order_public_id).first()

    def list_order_uploads(self, *, order):
        return self._base_queryset().for_order(order)

    def get_order_upload(self, *, order, upload_public_id):
        return self.list_order_uploads(order=order).filter(public_id=upload_public_id).first()

    def list_customer_order_uploads(self, *, customer, order_public_id):
        order = self.get_customer_order(customer=customer, order_public_id=order_public_id)
        if order is None:
            return None, OrderUpload.objects.none()
        return order, self.list_order_uploads(order=order)

    def get_customer_order_upload(self, *, customer, order_public_id, upload_public_id):
        order = self.get_customer_order(customer=customer, order_public_id=order_public_id)
        if order is None:
            return None, None
        return order, self.get_order_upload(order=order, upload_public_id=upload_public_id)

    def get_staff_order_upload(self, *, order_public_id, upload_public_id):
        order = self.get_staff_order(order_public_id=order_public_id)
        if order is None:
            return None, None
        return order, self.get_order_upload(order=order, upload_public_id=upload_public_id)

    def create_upload(
        self,
        *,
        customer,
        actor,
        uploaded_file,
        customer_membership=None,
        order_public_id,
        source: str,
        quantity: int | None = None,
        support_color_hex: str = "",
    ) -> OrderUpload:
        order = self.get_customer_order(customer=customer, order_public_id=order_public_id)
        if order is None:
            raise ValidationError("Order not found.")

        if order.status != Order.Status.DRAFT and order.uses_atelier_pricing():
            raise ValidationError(
                "Cette commande est verrouillée : les fichiers ne peuvent plus être modifiés.",
            )

        validated_membership = self._validate_customer_actor_scope(
            customer=customer,
            actor=actor,
            customer_membership=customer_membership,
        )
        validated_upload = self.validation_service.validate_uploaded_file(uploaded_file)
        resolved_qty = self._normalize_quantity(quantity)
        color = self._normalize_support_color(support_color_hex)

        with transaction.atomic():
            next_order = (
                OrderUpload.objects.filter(order=order).aggregate(m=Max("sort_order"))["m"] or 0
            ) + 1

            order_upload = OrderUpload(
                order=order,
                uploaded_by=actor if getattr(actor, "is_authenticated", False) else None,
                original_filename=validated_upload.original_filename,
                mime_type=validated_upload.mime_type,
                size_bytes=validated_upload.size_bytes,
                sort_order=next_order,
                quantity=resolved_qty,
                support_color_hex=color,
            )
            order_upload.file.save(
                validated_upload.original_filename,
                validated_upload.uploaded_file,
                save=False,
            )
            order_upload.save()

            record_event(
                action="order_upload.created",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=order_upload,
                metadata={
                    "order_public_id": str(order.public_id),
                    "customer_public_id": str(order.customer.public_id),
                    "order_upload_public_id": str(order_upload.public_id),
                    "customer_membership_public_id": str(validated_membership.public_id),
                    "mime_type": order_upload.mime_type,
                    "size_bytes": order_upload.size_bytes,
                    "source": source,
                },
            )
            self.inspection_service.inspect_upload(
                order_upload=order_upload,
                actor=actor,
                source=source,
            )
            self.drive_sync_service.ensure_sync_record(order_upload=order_upload)
            transaction.on_commit(
                lambda: self.drive_sync_service.schedule_upload_sync(
                    order_upload=order_upload,
                    actor=actor,
                    source=source,
                )
            )

        return self.get_order_upload(order=order, upload_public_id=order_upload.public_id)

    def create_upload_from_asset_version(
        self,
        *,
        customer,
        actor,
        order,
        asset_version,
        quantity: int | None = None,
        width_mm=None,
        height_mm=None,
        support_color_hex: str = "",
        customer_membership=None,
        source: str,
    ) -> OrderUpload:
        if order.customer_id != customer.id:
            raise ValidationError("Commande introuvable.")
        if asset_version.customer_id != customer.id:
            raise ValidationError("Fichier introuvable.")
        # Un même asset peut servir plusieurs commandes (réassort), mais pas deux
        # fois dans la même commande.
        if OrderUpload.objects.filter(order=order, asset_version=asset_version).exists():
            raise ValidationError("Ce fichier est déjà rattaché à cette commande.")

        validated_membership = self._validate_customer_actor_scope(
            customer=customer,
            actor=actor,
            customer_membership=customer_membership,
        )
        resolved_qty = self._normalize_quantity(quantity)
        color = self._normalize_support_color(support_color_hex)

        with transaction.atomic():
            next_order = (
                OrderUpload.objects.filter(order=order).aggregate(m=Max("sort_order"))["m"] or 0
            ) + 1

            order_upload = OrderUpload(
                order=order,
                uploaded_by=actor if getattr(actor, "is_authenticated", False) else None,
                asset_version=asset_version,
                original_filename=asset_version.original_filename,
                mime_type=asset_version.mime_type,
                size_bytes=asset_version.size_bytes,
                sort_order=next_order,
                quantity=resolved_qty,
                width_mm=width_mm,
                height_mm=height_mm,
                support_color_hex=color,
                is_production_derivative=False,
                production_file_sha256=str(getattr(asset_version, "sha256", "") or ""),
                source_crop_metadata={},
            )
            order_upload.file.name = asset_version.file.name
            order_upload.save()

            record_event(
                action="order_upload.created",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=order_upload,
                metadata={
                    "order_public_id": str(order.public_id),
                    "customer_public_id": str(order.customer.public_id),
                    "order_upload_public_id": str(order_upload.public_id),
                    "asset_version_public_id": str(asset_version.public_id),
                    "customer_membership_public_id": str(validated_membership.public_id),
                    "mime_type": order_upload.mime_type,
                    "size_bytes": order_upload.size_bytes,
                    "source": source,
                },
            )
            self.inspection_service.inspect_upload(
                order_upload=order_upload,
                actor=actor,
                source=source,
            )
            self.drive_sync_service.ensure_sync_record(order_upload=order_upload)
            transaction.on_commit(
                lambda: self.drive_sync_service.schedule_upload_sync(
                    order_upload=order_upload,
                    actor=actor,
                    source=source,
                )
            )

        return self.get_order_upload(order=order, upload_public_id=order_upload.public_id)

    def _normalize_quantity(self, quantity: int | None) -> int:
        if quantity is None:
            return 1
        try:
            value = int(quantity)
        except (TypeError, ValueError):
            raise ValidationError("Quantité invalide.") from None
        if value < 1:
            raise ValidationError("La quantité doit être au moins 1.")
        return value

    def can_staff_edit_upload_quantity(self, *, order: Order) -> bool:
        """Encours uniquement, commande non terminée, production non démarrée."""
        return (
            order.billing_mode == Order.BillingMode.DEFERRED
            and order.status in (Order.Status.DRAFT, Order.Status.SUBMITTED)
            and not order_production_has_started(order)
        )

    @transaction.atomic
    def set_staff_upload_quantity(
        self,
        *,
        order: Order,
        upload_public_id,
        actor,
        quantity,
        source: str = "staff_portal.upload_quantity",
    ) -> OrderUpload:
        """Corrige le nombre d’exemplaires d’un visuel (encours, avant production).

        Ne recalcule pas le prix : le tarif encours reste piloté par la saisie
        métrage atelier, comme aujourd’hui.
        """
        if not self.can_staff_edit_upload_quantity(order=order):
            if order.billing_mode != Order.BillingMode.DEFERRED:
                raise ValidationError(
                    "La modification de quantité est réservée aux commandes encours."
                )
            if order_production_has_started(order):
                raise ValidationError(
                    "Impossible de modifier les quantités : la production a déjà démarré."
                )
            raise ValidationError("Statut de commande incompatible avec cette modification.")

        from apps.customers.models import Customer

        Customer.objects.select_for_update().get(pk=order.customer_id)
        order = Order.objects.select_for_update().get(pk=order.pk)
        if not self.can_staff_edit_upload_quantity(order=order):
            if order_production_has_started(order):
                raise ValidationError(
                    "Impossible de modifier les quantités : la production a déjà démarré."
                )
            raise ValidationError("Statut de commande incompatible avec cette modification.")

        order_upload = (
            OrderUpload.objects.select_for_update()
            .filter(order=order, public_id=upload_public_id)
            .first()
        )
        if order_upload is None:
            raise ValidationError("Fichier introuvable pour cette commande.")

        resolved_qty = self._normalize_quantity(quantity)
        if resolved_qty > STAFF_UPLOAD_QUANTITY_MAX:
            raise ValidationError(
                f"La quantité ne peut pas dépasser {STAFF_UPLOAD_QUANTITY_MAX}."
            )

        previous = order_upload.quantity
        if previous == resolved_qty:
            return order_upload

        order_upload.quantity = resolved_qty
        order_upload.save(update_fields=["quantity", "updated_at"])
        record_event(
            action="order_upload.quantity_updated",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=order_upload,
            metadata={
                "order_public_id": str(order.public_id),
                "customer_public_id": str(order.customer.public_id),
                "order_upload_public_id": str(order_upload.public_id),
                "previous_quantity": previous,
                "quantity": resolved_qty,
                "source": source,
            },
        )
        return order_upload

    def _normalize_support_color(self, raw: str) -> str:
        cleaned = str(raw or "").strip()
        if not cleaned:
            return ""
        if not cleaned.startswith("#"):
            cleaned = f"#{cleaned}"
        if cleaned.lower() == "#multicolor":
            return "#multicolor"
        if len(cleaned) != 7:
            raise ValidationError("Couleur support : format #RRVVBB ou multicolore attendu.")
        return cleaned.lower()

    def download_customer_order_upload(
        self,
        *,
        customer,
        actor,
        customer_membership,
        order_public_id,
        upload_public_id,
        source: str,
    ) -> OrderUpload | None:
        order, order_upload = self.get_customer_order_upload(
            customer=customer,
            order_public_id=order_public_id,
            upload_public_id=upload_public_id,
        )
        if order is None or order_upload is None:
            return None

        validated_membership = self._validate_customer_actor_scope(
            customer=customer,
            actor=actor,
            customer_membership=customer_membership,
        )
        return self.prepare_download(
            order_upload=order_upload,
            actor=actor,
            source=source,
            customer_membership_public_id=str(validated_membership.public_id),
            audience="client",
        )

    def download_staff_order_upload(
        self,
        *,
        actor,
        order_public_id,
        upload_public_id,
        source: str,
    ) -> OrderUpload | None:
        order, order_upload = self.get_staff_order_upload(
            order_public_id=order_public_id,
            upload_public_id=upload_public_id,
        )
        if order is None or order_upload is None:
            return None

        return self.prepare_download(
            order_upload=order_upload,
            actor=actor,
            source=source,
            audience="staff",
        )

    def prepare_download(
        self,
        *,
        order_upload,
        actor,
        source: str,
        audience: str,
        customer_membership_public_id: str | None = None,
    ) -> OrderUpload | None:
        if order_upload.is_external:
            return None
        metadata = {
            "order_public_id": str(order_upload.order.public_id),
            "customer_public_id": str(order_upload.order.customer.public_id),
            "order_upload_public_id": str(order_upload.public_id),
            "mime_type": order_upload.mime_type,
            "size_bytes": order_upload.size_bytes,
            "source": source,
            "audience": audience,
        }
        if customer_membership_public_id is not None:
            metadata["customer_membership_public_id"] = customer_membership_public_id

        record_event(
            action="order_upload.downloaded",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=order_upload,
            metadata=metadata,
        )
        return order_upload

    def get_customer_upload_inspection(
        self,
        *,
        customer,
        actor,
        customer_membership,
        order_public_id,
        upload_public_id,
        source: str,
    ):
        order, order_upload = self.get_customer_order_upload(
            customer=customer,
            order_public_id=order_public_id,
            upload_public_id=upload_public_id,
        )
        if order is None or order_upload is None:
            return order, order_upload, None

        if order_upload.is_external:
            return order, order_upload, None

        validated_membership = self._validate_customer_actor_scope(
            customer=customer,
            actor=actor,
            customer_membership=customer_membership,
        )
        inspection = self.inspection_service.ensure_inspection(
            order_upload=order_upload,
            actor=actor,
            source=source,
        )
        self.inspection_service.record_view_event(
            order_upload=order_upload,
            inspection=inspection,
            actor=actor,
            source=source,
            audience="client",
            customer_membership_public_id=str(validated_membership.public_id),
        )
        return order, order_upload, inspection

    def get_staff_upload_inspection(
        self,
        *,
        actor,
        order_public_id,
        upload_public_id,
        source: str,
    ):
        order, order_upload = self.get_staff_order_upload(
            order_public_id=order_public_id,
            upload_public_id=upload_public_id,
        )
        if order is None or order_upload is None:
            return order, order_upload, None

        if order_upload.is_external:
            return order, order_upload, None

        inspection = self.inspection_service.ensure_inspection(
            order_upload=order_upload,
            actor=actor,
            source=source,
        )
        self.inspection_service.record_view_event(
            order_upload=order_upload,
            inspection=inspection,
            actor=actor,
            source=source,
            audience="staff",
        )
        return order, order_upload, inspection

    def get_staff_upload_drive_sync(
        self,
        *,
        actor,
        order_public_id,
        upload_public_id,
        source: str,
    ):
        order, order_upload = self.get_staff_order_upload(
            order_public_id=order_public_id,
            upload_public_id=upload_public_id,
        )
        if order is None or order_upload is None:
            return order, order_upload, None

        if order_upload.is_external:
            return order, order_upload, None

        drive_sync = self.drive_sync_service.get_upload_sync(order_upload=order_upload)
        self.drive_sync_service.record_view_event(
            order_upload=order_upload,
            drive_sync=drive_sync,
            actor=actor,
            source=source,
        )
        return order, order_upload, drive_sync

    def _set_external_visual_count(self, *, order, actor, value):
        from apps.uploads.validators import normalize_external_visual_count

        if not self.access_scope_service.can_access_staff_domain(actor, "orders.change_order"):
            raise ValidationError("Permission de modification de commande requise.")
        count = normalize_external_visual_count(value)
        uploads = list(OrderUpload.objects.select_for_update().filter(order=order))
        if len(uploads) != 1 or not uploads[0].is_external:
            raise ValidationError("Cette saisie concerne une commande transmise par lien.")
        upload = uploads[0]
        previous = upload.external_visual_count
        upload.external_visual_count = count
        upload.save(update_fields=["external_visual_count", "updated_at"])
        if previous != count:
            record_event(
                action="order.external_visual_count_updated",
                actor=actor,
                target=order,
                metadata={"previous_count": previous, "external_visual_count": count},
            )

    @transaction.atomic
    def set_staff_external_visual_count(self, *, order: Order, actor, value) -> Order:
        """Record the contents of an external link without changing meterage."""
        from apps.customers.models import Customer

        Customer.objects.select_for_update().get(pk=order.customer_id)
        order = Order.objects.select_for_update().get(pk=order.pk)
        if not order.uses_atelier_pricing() or order.status not in (
            Order.Status.DRAFT,
            Order.Status.SUBMITTED,
        ):
            raise ValidationError("Statut incompatible avec la modification du nombre de fichiers.")
        if order.billing_mode == Order.BillingMode.IMMEDIATE and order.payments.exists():
            raise ValidationError("Le tarif est figé dès qu’un paiement a été lancé.")
        was_priced = order.pricing_status == Order.PricingStatus.PRICED
        self._set_external_visual_count(order=order, actor=actor, value=value)
        self.pricing_service.invalidate_deferred_pricing_after_meterage_change(
            order=order, actor=actor, source="staff_portal.external_visual_count"
        )
        order.refresh_from_db()
        if was_priced:
            return self.pricing_service.compute_and_persist_order_pricing(
                order=order, actor=actor, source="staff_portal.external_visual_count"
            )
        return order

    @transaction.atomic
    def set_staff_order_meterage_linear_override(
        self,
        *,
        order: Order,
        actor,
        raw_value: str | None,
        external_visual_count=None,
    ) -> Order:
        """Saisie opérateur : mètres linéaires pour toute la commande
        (laize × linéaire = m² total réparti par fichier).
        """
        from apps.customers.models import Customer

        Customer.objects.select_for_update().get(pk=order.customer_id)
        order = Order.objects.select_for_update().get(pk=order.pk)
        from apps.orders.services.meterage import (
            order_meterage_is_resolved,
            order_pricing_is_payment_frozen,
        )

        raw = (raw_value or "").strip()
        if order_pricing_is_payment_frozen(order):
            # Tarif figé : confirmation vide OK si métrage déjà résolu (ex. Gang Sheet).
            if order_meterage_is_resolved(order) and raw == "" and external_visual_count is None:
                return order
            raise ValidationError("Le tarif est figé dès qu’un paiement a été lancé.")
        if external_visual_count is not None:
            self._set_external_visual_count(order=order, actor=actor, value=external_visual_count)
        if raw:
            try:
                dec = Decimal(raw.replace(",", "."))
                if not dec.is_finite() or dec <= 0 or dec >= Decimal("100000000"):
                    raise InvalidOperation
                dec = dec.quantize(Decimal("0.0001"))
                if dec <= 0:
                    raise InvalidOperation
            except (InvalidOperation, TypeError):
                raise ValidationError("Indiquez un métrage linéaire positif valide.") from None

        if not order.uses_atelier_pricing():
            raise ValidationError(
                "La saisie manuelle du métrage concerne les commandes atelier "
                "(encours ou comptant CB)."
            )
        if order.status not in (Order.Status.DRAFT, Order.Status.SUBMITTED):
            raise ValidationError("Statut de commande incompatible avec la saisie du métrage.")

        self.pricing_service.invalidate_deferred_pricing_after_meterage_change(
            order=order,
            actor=actor,
            source="staff_portal.order_meterage_linear",
        )
        order.refresh_from_db()

        if raw == "":
            with transaction.atomic():
                locked = Order.objects.select_for_update().get(pk=order.pk)
                locked.meterage_override_linear_m = None
                locked.save(update_fields=["meterage_override_linear_m", "updated_at"])
            record_event(
                action="order.meterage_linear_override_cleared",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=order,
                metadata={"order_public_id": str(order.public_id)},
            )
            order.refresh_from_db()
            return order

        with transaction.atomic():
            locked = Order.objects.select_for_update().get(pk=order.pk)
            locked.meterage_override_linear_m = dec
            locked.save(update_fields=["meterage_override_linear_m", "updated_at"])
            OrderUpload.objects.filter(order=locked).update(
                meterage_override_linear_m=None,
                meterage_override_sqm=None,
            )

        record_event(
            action="order.meterage_linear_override_set",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=order,
            metadata={
                "order_public_id": str(order.public_id),
                "meterage_override_linear_m": str(dec),
            },
        )
        order.refresh_from_db()
        if order.status == Order.Status.SUBMITTED and order.uploads.exists():
            return self.pricing_service.compute_and_persist_order_pricing(
                order=order,
                actor=actor,
                source="staff_portal.order_meterage_linear_auto",
            )
        return order

    def set_staff_meterage_override(
        self,
        *,
        order: Order,
        upload_public_id,
        actor,
        raw_value: str | None,
    ) -> OrderUpload:
        """Saisie opérateur : mètres linéaires sur la laize (par exemplaire) —
        prioritaire sur l'inspection.

        Surface facturée = linéaire × DTF_LAIZE_CM × quantité. Efface
        l'ancienne saisie m² le cas échéant. Autorisé en facturation différée,
        brouillon ou soumis, tant que la commande n'est pas tarifée.
        """
        order_upload = self.get_order_upload(order=order, upload_public_id=upload_public_id)
        if order_upload is None:
            raise ValidationError("Fichier introuvable pour cette commande.")
        if not order.uses_atelier_pricing():
            raise ValidationError(
                "La saisie manuelle du métrage concerne les commandes atelier "
                "(encours ou comptant CB)."
            )
        if order.status not in (Order.Status.DRAFT, Order.Status.SUBMITTED):
            raise ValidationError("Statut de commande incompatible avec la saisie du métrage.")
        if order.pricing_status == Order.PricingStatus.PRICED:
            raise ValidationError("La commande est déjà tarifée.")

        raw = (raw_value or "").strip()
        if raw == "":
            with transaction.atomic():
                locked = OrderUpload.objects.select_for_update().get(pk=order_upload.pk)
                locked.meterage_override_linear_m = None
                locked.meterage_override_sqm = None
                locked.save(
                    update_fields=[
                        "meterage_override_linear_m",
                        "meterage_override_sqm",
                        "updated_at",
                    ]
                )
            record_event(
                action="upload.meterage_override_cleared",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=order_upload,
                metadata={"order_public_id": str(order.public_id)},
            )
            order_upload.refresh_from_db()
            return order_upload

        try:
            dec = Decimal(raw.replace(",", "."))
        except (InvalidOperation, TypeError):
            raise ValidationError("Indiquez un nombre valide (mètres linéaires).") from None
        if dec <= 0:
            raise ValidationError("Le métrage linéaire doit être strictement positif.")
        dec = dec.quantize(Decimal("0.0001"))

        with transaction.atomic():
            order_locked = Order.objects.select_for_update().get(pk=order.pk)
            if order_locked.meterage_override_linear_m is not None:
                order_locked.meterage_override_linear_m = None
                order_locked.save(update_fields=["meterage_override_linear_m", "updated_at"])
            locked = OrderUpload.objects.select_for_update().get(pk=order_upload.pk)
            locked.meterage_override_linear_m = dec
            locked.meterage_override_sqm = None
            locked.save(
                update_fields=["meterage_override_linear_m", "meterage_override_sqm", "updated_at"]
            )

        record_event(
            action="upload.meterage_override_set",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=order_upload,
            metadata={
                "order_public_id": str(order.public_id),
                "meterage_override_linear_m": str(dec),
            },
        )
        order_upload.refresh_from_db()
        return order_upload

    def _base_queryset(self):
        return OrderUpload.objects.select_related(
            "order",
            "order__customer",
            "uploaded_by",
            "inspection",
            "atelier_review",
            "atelier_review__reviewed_by",
            "drive_sync",
            "asset_version",
            "asset_version__analysis",
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
