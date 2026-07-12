from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone

from apps.b2b_order_projects.models import B2BOrderProject, B2BOrderProjectItem
from apps.b2b_order_projects.permissions import b2b_order_projects_enabled_for_customer
from apps.b2b_order_projects.services.projects import B2BOrderProjectService, ProjectDomainError
from apps.core.public_refs import short_public_ref
from apps.orders.references import order_client_reference
from apps.uploads.services.assets import AssetService
from apps.uploads.services.uploads import OrderUploadService

DEFAULT_REORDER_DIMENSION_MM = Decimal("100.00")


class B2BOrderReorderService:
    def __init__(
        self,
        project_service: B2BOrderProjectService | None = None,
        upload_service: OrderUploadService | None = None,
        asset_service: AssetService | None = None,
    ):
        self.project_service = project_service or B2BOrderProjectService()
        self.upload_service = upload_service or OrderUploadService()
        self.asset_service = asset_service or AssetService()

    @transaction.atomic
    def create_reorder_from_order(self, *, customer, order, actor, source: str) -> B2BOrderProject:
        if order.customer_id != customer.id:
            raise ProjectDomainError("ORDER_NOT_FOUND", "Commande introuvable.")
        if not b2b_order_projects_enabled_for_customer(customer):
            raise ProjectDomainError(
                "FEATURE_DISABLED",
                "La fonctionnalité de recommande n'est pas disponible pour ce compte.",
            )

        uploads = list(
            self.upload_service.list_order_uploads(order=order).select_related(
                "asset_version",
                "asset_version__asset",
                "asset_version__analysis",
                "inspection",
            )
        )
        if not uploads:
            raise ProjectDomainError(
                "ORDER_HAS_NO_UPLOADS",
                "Aucun visuel disponible pour préparer une recommande.",
            )

        order_ref = order_client_reference(order) or short_public_ref(order.public_id)
        project = self.project_service.create_project(
            customer=customer,
            actor=actor,
            data={
                "name": f"Réassort — {order_ref}",
                "order_mode": B2BOrderProject.OrderMode.REORDER,
                "customer_reference": f"REORDER-{short_public_ref(order.public_id)}",
            },
            source=source,
        )

        source_items_by_version_id = self._source_items_by_version_id(order)
        for upload in uploads:
            source_item = source_items_by_version_id.get(upload.asset_version_id)
            width_mm, height_mm = self._resolve_dimensions(upload, source_item)
            item = self.project_service.add_item(
                project=project,
                actor=actor,
                data={
                    "name": self._item_name(upload),
                    "width_mm": width_mm,
                    "height_mm": height_mm,
                    "quantity": upload.quantity,
                    "support_color_hex": upload.support_color_hex or "",
                },
                source=source,
            )
            if upload.asset_version_id:
                self._link_existing_asset(
                    project=project,
                    item=item,
                    asset=upload.asset_version.asset,
                    actor=actor,
                    source=source,
                )
                self._confirm_item_if_ready(item=item, actor=actor)
            else:
                self._attach_legacy_upload(
                    project=project,
                    item=item,
                    upload=upload,
                    actor=actor,
                    source=source,
                )
            item.refresh_from_db()
            self._confirm_item_if_ready(item=item, actor=actor)

        self.project_service.refresh_completeness(project=project)
        return self.project_service.get_customer_project(
            customer=customer,
            project_public_id=project.public_id,
        )

    def _source_items_by_version_id(self, order) -> dict[int, B2BOrderProjectItem]:
        source_project = getattr(order, "source_b2b_order_project", None)
        if source_project is None:
            return {}
        mapping: dict[int, B2BOrderProjectItem] = {}
        for item in source_project.items.select_related("asset__current_version"):
            version = getattr(getattr(item, "asset", None), "current_version", None)
            if version is not None:
                mapping[version.id] = item
        return mapping

    def _resolve_dimensions(
        self,
        upload,
        source_item: B2BOrderProjectItem | None,
    ) -> tuple[Decimal, Decimal]:
        if source_item is not None:
            return source_item.width_mm, source_item.height_mm

        version = upload.asset_version
        analysis = getattr(version, "analysis", None) if version is not None else None
        if analysis is not None and analysis.image_width and analysis.image_height:
            dpi = float(analysis.dpi_x or analysis.dpi_y or 300)
            if dpi > 0:
                width_mm = Decimal(analysis.image_width / dpi * 25.4).quantize(Decimal("0.01"))
                height_mm = Decimal(analysis.image_height / dpi * 25.4).quantize(Decimal("0.01"))
                if width_mm > 0 and height_mm > 0:
                    return width_mm, height_mm

        inspection = getattr(upload, "inspection", None)
        if inspection is not None and inspection.image_width and inspection.image_height:
            dpi = 300.0
            width_mm = Decimal(inspection.image_width / dpi * 25.4).quantize(Decimal("0.01"))
            height_mm = Decimal(inspection.image_height / dpi * 25.4).quantize(Decimal("0.01"))
            if width_mm > 0 and height_mm > 0:
                return width_mm, height_mm

        return DEFAULT_REORDER_DIMENSION_MM, DEFAULT_REORDER_DIMENSION_MM

    @staticmethod
    def _item_name(upload) -> str:
        stem = Path(upload.original_filename).stem.strip()
        return stem or upload.original_filename

    def _link_existing_asset(self, *, project, item, asset, actor, source: str) -> None:
        self.asset_service.link_existing_asset_to_item(
            project=project,
            item_public_id=item.public_id,
            asset=asset,
            actor=actor,
            source=source,
        )

    def _attach_legacy_upload(self, *, project, item, upload, actor, source: str) -> None:
        upload.file.open("rb")
        try:
            content = upload.file.read()
        finally:
            upload.file.close()
        uploaded_file = SimpleUploadedFile(
            upload.original_filename,
            content,
            content_type=upload.mime_type,
        )
        self.asset_service.attach_project_item_file(
            project=project,
            item_public_id=item.public_id,
            actor=actor,
            uploaded_file=uploaded_file,
            source=source,
        )

    @staticmethod
    def _confirm_item_if_ready(*, item, actor) -> None:
        version = getattr(getattr(item, "asset", None), "current_version", None)
        if version is None or version.analysis_status not in {"ready", "warning"}:
            return
        item.client_confirmed_asset_version = version
        item.client_confirmed_at = timezone.now()
        item.client_confirmed_by = actor if getattr(actor, "is_authenticated", False) else None
        item.save(
            update_fields=[
                "client_confirmed_asset_version",
                "client_confirmed_at",
                "client_confirmed_by",
                "updated_at",
            ]
        )
