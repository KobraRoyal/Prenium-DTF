from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.b2b_order_projects.models import B2BOrderProject
from apps.b2b_order_projects.services.projects import B2BOrderProjectService, ProjectDomainError
from apps.orders.services.orders import OrderService
from apps.uploads.services.drive import OrderDriveFolderService
from apps.uploads.services.uploads import OrderUploadService


class B2BOrderProjectCheckoutService:
    def __init__(
        self,
        *,
        project_service: B2BOrderProjectService | None = None,
        order_service: OrderService | None = None,
        upload_service: OrderUploadService | None = None,
    ):
        self.project_service = project_service or B2BOrderProjectService()
        self.order_service = order_service or OrderService()
        self.upload_service = upload_service or OrderUploadService()

    @transaction.atomic
    def checkout_project(
        self,
        *,
        project,
        actor,
        customer_membership,
        source: str = "client_portal.b2b_checkout",
    ):
        locked = self.project_service._lock(project)
        self.project_service._refresh_completeness(locked)
        locked.refresh_from_db()

        if locked.converted_order_id:
            existing = (
                self.order_service.list_customer_orders(locked.customer)
                .filter(pk=locked.converted_order_id)
                .first()
            )
            if existing is not None:
                return existing

        if locked.status not in {
            B2BOrderProject.Status.READY_TO_SUBMIT,
            B2BOrderProject.Status.SUBMITTED,
        }:
            raise ProjectDomainError(
                "INVALID_PROJECT_TRANSITION",
                "Le projet doit être complet avant transmission.",
                {
                    "current_status": locked.status,
                    "requested_status": B2BOrderProject.Status.CONVERTED,
                },
            )
        if (
            locked.status == B2BOrderProject.Status.SUBMITTED
            and locked.converted_order_id is not None
        ):
            raise ProjectDomainError(
                "PROJECT_ALREADY_CONVERTED",
                "Cette préparation a déjà été convertie en commande.",
            )

        items = list(
            locked.items.select_related(
                "asset__current_version",
                "client_confirmed_asset_version",
            ).order_by("sort_order", "created_at")
        )
        if not items:
            raise ProjectDomainError(
                "PROJECT_ITEMS_REQUIRED",
                "Ajoutez au moins un visuel avant transmission.",
            )

        for item in items:
            version = getattr(getattr(item, "asset", None), "current_version", None)
            if version is None:
                raise ProjectDomainError(
                    "PROJECT_ITEM_INCOMPLETE",
                    "Chaque visuel doit avoir un fichier analysé.",
                    {"item_public_id": str(item.public_id)},
                )
            if item.client_confirmed_asset_version_id != version.id:
                raise ProjectDomainError(
                    "PROJECT_ITEM_NOT_CONFIRMED",
                    "Validez chaque visuel avant transmission.",
                    {"item_public_id": str(item.public_id)},
                )

        order = self.order_service.create_b2b_deferred_order(
            customer=locked.customer,
            actor=actor,
            customer_note=self._build_order_note(locked),
            customer_membership=customer_membership,
            source=source,
        )

        for item in items:
            version = item.asset.current_version
            self.upload_service.create_upload_from_asset_version(
                customer=locked.customer,
                actor=actor,
                customer_membership=customer_membership,
                order=order,
                asset_version=version,
                quantity=item.quantity,
                support_color_hex=self._order_upload_support_color(item),
                source=source,
            )

        if settings.GOOGLE_DRIVE_SYNC_ENABLED:
            OrderDriveFolderService().ensure_order_folder(
                order=order,
                actor=actor,
                source=source,
            )

        order = self.order_service.submit_b2b_deferred_order(
            customer=locked.customer,
            actor=actor,
            customer_membership=customer_membership,
            order_public_id=order.public_id,
            source=source,
        )

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
            action="b2b_order_project.converted",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=locked,
            metadata={
                "customer_public_id": str(locked.customer.public_id),
                "project_public_id": str(locked.public_id),
                "order_public_id": str(order.public_id),
                "item_count": len(items),
                "source": source,
            },
        )
        self.project_service._audit(
            "converted",
            project=locked,
            actor=actor,
            source=source,
            metadata={"order_public_id": str(order.public_id)},
        )
        return order

    def _build_order_note(self, project) -> str:
        parts = [project.name.strip()]
        if project.project_number:
            parts.append(f"Préparation {project.project_number}")
        if project.customer_comment.strip():
            parts.append(project.customer_comment.strip())
        if project.requested_date:
            parts.append(f"Date souhaitée : {project.requested_date.isoformat()}")
        return "\n".join(part for part in parts if part)

    def _order_upload_support_color(self, item) -> str:
        if item.support_color_is_multicolor:
            return ""
        return item.support_color_hex or ""
