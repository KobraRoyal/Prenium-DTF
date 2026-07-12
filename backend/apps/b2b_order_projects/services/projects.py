from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import models, transaction
from django.db.models import Max
from django.utils import timezone

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.b2b_order_projects.models import (
    SUPPORT_COLOR_MULTICOLOR,
    B2BOrderProject,
    B2BOrderProjectItem,
)
from apps.b2b_order_projects.services.numbering import B2BOrderProjectNumberService
from apps.b2b_order_projects.services.transitions import B2BOrderProjectTransitionPolicy


@dataclass(frozen=True)
class ProjectDomainError(Exception):
    code: str
    message: str
    details: dict[str, object] | None = None

    def __str__(self) -> str:
        return self.message


class B2BOrderProjectService:
    project_write_fields = {
        "name",
        "customer_reference",
        "end_customer_reference",
        "order_mode",
        "requested_date",
        "delivery_method",
        "shipping_address",
        "customer_comment",
    }
    item_write_fields = {
        "name",
        "customer_reference",
        "placement",
        "width_mm",
        "height_mm",
        "quantity",
        "rotation_allowed",
        "individual_cutting",
        "support_color_hex",
        "customer_comment",
    }

    def __init__(self):
        self.numbering = B2BOrderProjectNumberService()
        self.transitions = B2BOrderProjectTransitionPolicy()

    def list_customer_projects(self, customer):
        return self._base_queryset().for_customer(customer)

    def list_customer_projects_in_progress(self, customer):
        """Préparations encore ouvertes côté client (hors paniers convertis ou annulés)."""
        return (
            self.list_customer_projects(customer)
            .filter(converted_order__isnull=True)
            .exclude(
                status__in={
                    B2BOrderProject.Status.CONVERTED,
                    B2BOrderProject.Status.CANCELLED,
                }
            )
        )

    def list_staff_projects(self):
        return self._base_queryset()

    def get_customer_project(self, *, customer, project_public_id):
        return (
            self._base_queryset().for_customer(customer).filter(public_id=project_public_id).first()
        )

    def get_staff_project(self, *, project_public_id):
        return self._base_queryset().filter(public_id=project_public_id).first()

    @transaction.atomic
    def create_project(self, *, customer, actor, data: dict, source: str) -> B2BOrderProject:
        name = str(data.get("name", "")).strip()
        if not name:
            raise ProjectDomainError("PROJECT_NAME_REQUIRED", "Le nom du projet est obligatoire.")
        order_mode = data.get("order_mode") or B2BOrderProject.OrderMode.INDIVIDUAL_DESIGNS
        if order_mode not in B2BOrderProject.OrderMode.values:
            raise ProjectDomainError("INVALID_ORDER_MODE", "Le mode de commande est invalide.")

        project = B2BOrderProject.objects.create(
            customer=customer,
            created_by=actor,
            project_number=self.numbering.next_number(),
            name=name,
            customer_reference=str(data.get("customer_reference", "")).strip(),
            end_customer_reference=str(data.get("end_customer_reference", "")).strip(),
            order_mode=order_mode,
            requested_date=data.get("requested_date") or None,
            delivery_method=str(data.get("delivery_method", "")).strip(),
            shipping_address=self._normalize_shipping_address(data.get("shipping_address")),
            customer_comment=str(data.get("customer_comment", "")).strip(),
        )
        self._audit("created", project=project, actor=actor, source=source)
        return self.get_customer_project(customer=customer, project_public_id=project.public_id)

    @transaction.atomic
    def update_project(self, *, project, actor, data: dict, source: str) -> B2BOrderProject:
        locked = self._lock(project)
        self._ensure_editable(locked)
        changed = []
        for field in self.project_write_fields:
            if field not in data:
                continue
            value = data[field]
            if field == "order_mode" and value not in B2BOrderProject.OrderMode.values:
                raise ProjectDomainError("INVALID_ORDER_MODE", "Le mode de commande est invalide.")
            if field == "name":
                value = str(value).strip()
                if not value:
                    raise ProjectDomainError("PROJECT_NAME_REQUIRED", "Le nom est obligatoire.")
            elif field == "shipping_address":
                value = self._normalize_shipping_address(value)
            elif field == "requested_date":
                value = value or None
            elif isinstance(value, str):
                value = value.strip()
            if getattr(locked, field) != value:
                setattr(locked, field, value)
                changed.append(field)
        if changed:
            locked.save(update_fields=[*changed, "updated_at"])
            self._audit(
                "updated", project=locked, actor=actor, source=source, metadata={"fields": changed}
            )
        return self.get_customer_project(
            customer=locked.customer, project_public_id=locked.public_id
        )

    @transaction.atomic
    def add_item(self, *, project, actor, data: dict, source: str) -> B2BOrderProjectItem:
        locked = self._lock(project)
        self._ensure_editable(locked)
        values = self._normalize_item_data(data, require_all=True)
        next_position = (
            B2BOrderProjectItem.objects.for_project(locked).aggregate(value=Max("sort_order"))[
                "value"
            ]
            or 0
        ) + 1
        item = B2BOrderProjectItem.objects.create(
            customer=locked.customer,
            project=locked,
            sort_order=next_position,
            **values,
        )
        self._refresh_completeness(locked)
        self._audit(
            "item_added",
            project=locked,
            actor=actor,
            source=source,
            metadata={"item_public_id": str(item.public_id)},
        )
        return item

    @transaction.atomic
    def update_item(self, *, project, item_public_id, actor, data: dict, source: str):
        locked = self._lock(project)
        self._ensure_editable(locked)
        item = self._get_item(locked, item_public_id, for_update=True)
        values = self._normalize_item_data(data, require_all=False)
        changed = []
        for field, value in values.items():
            if getattr(item, field) != value:
                setattr(item, field, value)
                changed.append(field)
        if changed:
            if {"width_mm", "height_mm", "support_color_hex"}.intersection(changed):
                item.client_confirmed_asset_version = None
                item.client_confirmed_at = None
                item.client_confirmed_by = None
                changed.extend(
                    [
                        "client_confirmed_asset_version",
                        "client_confirmed_at",
                        "client_confirmed_by",
                    ]
                )
            changed = list(dict.fromkeys(changed))
            item.save(update_fields=[*changed, "updated_at"])
            self._audit(
                "item_updated",
                project=locked,
                actor=actor,
                source=source,
                metadata={"item_public_id": str(item.public_id), "fields": changed},
            )
        self._refresh_completeness(locked)
        return item

    @transaction.atomic
    def confirm_item_analysis(
        self,
        *,
        project,
        item_public_id,
        actor,
        data: dict | None = None,
        source: str,
    ):
        locked = self._lock(project)
        self._ensure_editable(locked)
        item = (
            B2BOrderProjectItem.objects.select_for_update()
            .for_project(locked)
            .filter(public_id=item_public_id)
            .first()
        )
        if item is None:
            raise ProjectDomainError("PROJECT_ITEM_NOT_FOUND", "Visuel introuvable.")
        version = getattr(getattr(item, "asset", None), "current_version", None)
        if version is None or version.analysis_status not in {"ready", "warning"}:
            raise ProjectDomainError(
                "ANALYSIS_NOT_READY",
                "L’analyse technique doit être terminée avant votre validation.",
            )

        payload = data or {}
        changed = []
        if payload:
            values = self._normalize_item_data(payload, require_all=False)
            for field, value in values.items():
                if getattr(item, field) != value:
                    setattr(item, field, value)
                    changed.append(field)

        if self._has_thin_details(version) and (
            not item.support_color_hex or item.support_color_is_multicolor
        ):
            raise ProjectDomainError(
                "SUPPORT_COLOR_REQUIRED_FOR_THIN_DETAILS",
                "Indiquez la couleur unie exacte du support pour préserver les détails fins.",
            )

        item.client_confirmed_asset_version = version
        item.client_confirmed_at = timezone.now()
        item.client_confirmed_by = actor
        changed.extend(
            [
                "client_confirmed_asset_version",
                "client_confirmed_at",
                "client_confirmed_by",
            ]
        )
        item.save(update_fields=[*dict.fromkeys(changed), "updated_at"])
        self._audit(
            "item_analysis_confirmed",
            project=locked,
            actor=actor,
            source=source,
            metadata={
                "item_public_id": str(item.public_id),
                "asset_version_public_id": str(version.public_id),
                "support_color_hex": item.support_color_hex,
            },
        )
        self._refresh_completeness(locked)
        return item

    @staticmethod
    def _has_thin_details(version) -> bool:
        analysis = getattr(version, "analysis", None)
        metadata = (analysis.metadata or {}) if analysis is not None else {}
        return bool((metadata.get("thin_zone") or {}).get("detected"))

    @transaction.atomic
    def delete_item(self, *, project, item_public_id, actor, source: str) -> None:
        locked = self._lock(project)
        self._ensure_editable(locked)
        item = self._get_item(locked, item_public_id, for_update=True)
        public_id = item.public_id
        position = item.sort_order
        item.delete()
        B2BOrderProjectItem.objects.for_project(locked).filter(sort_order__gt=position).update(
            sort_order=models.F("sort_order") - 1
        )
        self._refresh_completeness(locked)
        self._audit(
            "item_deleted",
            project=locked,
            actor=actor,
            source=source,
            metadata={"item_public_id": str(public_id)},
        )

    @transaction.atomic
    def duplicate_item(self, *, project, item_public_id, actor, source: str):
        locked = self._lock(project)
        self._ensure_editable(locked)
        source_item = self._get_item(locked, item_public_id, for_update=True)
        next_position = (
            B2BOrderProjectItem.objects.for_project(locked).aggregate(value=Max("sort_order"))[
                "value"
            ]
            or 0
        ) + 1
        duplicate = B2BOrderProjectItem.objects.create(
            customer=locked.customer,
            project=locked,
            name=f"{source_item.name} (copie)"[:255],
            customer_reference=source_item.customer_reference,
            placement=source_item.placement,
            width_mm=source_item.width_mm,
            height_mm=source_item.height_mm,
            quantity=source_item.quantity,
            rotation_allowed=source_item.rotation_allowed,
            individual_cutting=source_item.individual_cutting,
            support_color_hex=source_item.support_color_hex,
            customer_comment=source_item.customer_comment,
            status=source_item.status,
            sort_order=next_position,
        )
        self._refresh_completeness(locked)
        self._audit(
            "item_duplicated",
            project=locked,
            actor=actor,
            source=source,
            metadata={
                "source_item_public_id": str(source_item.public_id),
                "item_public_id": str(duplicate.public_id),
            },
        )
        return duplicate

    @transaction.atomic
    def reorder_items(self, *, project, ordered_public_ids: list[str], actor, source: str):
        locked = self._lock(project)
        self._ensure_editable(locked)
        items = list(B2BOrderProjectItem.objects.select_for_update().for_project(locked))
        item_map = {str(item.public_id): item for item in items}
        normalized_ids = [str(value) for value in ordered_public_ids]
        if len(normalized_ids) != len(set(normalized_ids)) or set(normalized_ids) != set(item_map):
            raise ProjectDomainError(
                "INVALID_ITEM_ORDER",
                "La liste de réorganisation doit contenir toutes les lignes "
                "du projet une seule fois.",
            )
        # Décalage temporaire pour respecter la contrainte d'unicité pendant la réorganisation.
        for index, item in enumerate(items, start=1):
            item.sort_order = 1_000_000 + index
            item.save(update_fields=["sort_order"])
        for position, public_id in enumerate(normalized_ids, start=1):
            item = item_map[public_id]
            item.sort_order = position
            item.save(update_fields=["sort_order", "updated_at"])
        self._audit("items_reordered", project=locked, actor=actor, source=source)
        return B2BOrderProjectItem.objects.for_project(locked)

    def submit(self, *, project, actor, source: str) -> B2BOrderProject:
        rejection = None
        locked = None
        with transaction.atomic():
            locked = self._lock(project)
            self._refresh_completeness(locked)
            if locked.status != B2BOrderProject.Status.READY_TO_SUBMIT:
                rejection = {
                    "current_status": locked.status,
                    "requested_status": B2BOrderProject.Status.SUBMITTED,
                }
            elif not locked.items.exists():
                rejection = {
                    "current_status": locked.status,
                    "requested_status": B2BOrderProject.Status.SUBMITTED,
                    "reason": "items_required",
                }
            else:
                self._apply_transition(locked, B2BOrderProject.Status.SUBMITTED, actor, source)
                locked.submitted_at = timezone.now()
                locked.save(update_fields=["submitted_at", "updated_at"])

        if rejection is not None:
            self._transition_rejected(locked, actor, B2BOrderProject.Status.SUBMITTED, source)
            raise ProjectDomainError(
                "INVALID_PROJECT_TRANSITION",
                "Le projet doit être complet avant transmission.",
                rejection,
            )
        return self.get_customer_project(
            customer=locked.customer, project_public_id=locked.public_id
        )

    def can_client_delete(self, project) -> bool:
        return self.transitions.can_client_delete(project)

    def attach_can_delete(self, projects):
        for project in projects:
            project.can_delete = self.can_client_delete(project)
        return projects

    def cancel(self, *, project, actor, source: str) -> B2BOrderProject:
        rejection = False
        locked = None
        with transaction.atomic():
            locked = self._lock(project)
            if not self.transitions.can_transition(locked.status, B2BOrderProject.Status.CANCELLED):
                rejection = True
            else:
                self._apply_transition(locked, B2BOrderProject.Status.CANCELLED, actor, source)
        if rejection:
            self._transition_rejected(locked, actor, B2BOrderProject.Status.CANCELLED, source)
            raise ProjectDomainError(
                "INVALID_PROJECT_TRANSITION",
                "Le projet ne peut pas être annulé dans son statut actuel.",
                {
                    "current_status": locked.status,
                    "requested_status": B2BOrderProject.Status.CANCELLED,
                },
            )
        return self.get_customer_project(
            customer=locked.customer, project_public_id=locked.public_id
        )

    @transaction.atomic
    def delete_project(self, *, project, actor, source: str) -> None:
        locked = self._lock(project)
        if not self.can_client_delete(locked):
            self._transition_rejected(locked, actor, "deleted", source)
            raise ProjectDomainError(
                "PROJECT_NOT_DELETABLE",
                "Cette commande ne peut pas être supprimée dans son statut actuel.",
                {"current_status": locked.status},
            )
        self._audit(
            "deleted",
            project=locked,
            actor=actor,
            source=source,
            metadata={
                "project_number": locked.project_number,
                "status": locked.status,
            },
        )
        locked.delete()

    def _apply_transition(self, project, target_status, actor, source):
        previous = project.status
        if not self.transitions.can_transition(previous, target_status):
            self._transition_rejected(project, actor, target_status, source)
            raise ProjectDomainError(
                "INVALID_PROJECT_TRANSITION",
                "Cette transition de projet n'est pas autorisée.",
                {"current_status": previous, "requested_status": target_status},
            )
        project.status = target_status
        project.save(update_fields=["status", "updated_at"])
        self._audit(
            "status_changed",
            project=project,
            actor=actor,
            source=source,
            metadata={"previous_status": previous, "new_status": target_status},
        )

    def _refresh_completeness(self, project):
        if project.status not in self.transitions.editable_statuses:
            return
        items = project.items.all()
        has_items = items.exists()
        has_unanalyzed_item = items.filter(
            models.Q(asset__isnull=True)
            | models.Q(asset__current_version__isnull=True)
            | models.Q(asset__current_version__analysis_status__in=("pending", "processing"))
        ).exists()
        has_analysis_problem = items.filter(
            asset__current_version__analysis_status="failed"
        ).exists()
        has_unconfirmed_item = (
            items.filter(asset__current_version__analysis_status__in=("ready", "warning"))
            .exclude(client_confirmed_asset_version=models.F("asset__current_version"))
            .exists()
        )
        if not has_items or has_unanalyzed_item:
            new_status = B2BOrderProject.Status.INCOMPLETE
        elif has_analysis_problem or has_unconfirmed_item:
            new_status = B2BOrderProject.Status.ACTION_REQUIRED
        else:
            new_status = B2BOrderProject.Status.READY_TO_SUBMIT
        if project.status != new_status:
            project.status = new_status
            project.save(update_fields=["status", "updated_at"])

    @transaction.atomic
    def refresh_completeness(self, *, project) -> B2BOrderProject:
        locked = self._lock(project)
        self._refresh_completeness(locked)
        return locked

    def _normalize_item_data(self, data, *, require_all: bool):
        normalized = {}
        fields = (
            self.item_write_fields if require_all else self.item_write_fields.intersection(data)
        )
        for field in fields:
            value = data.get(field)
            if field in {"width_mm", "height_mm"}:
                value = self._positive_decimal(value, field)
            elif field == "quantity":
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    raise ProjectDomainError(
                        "INVALID_QUANTITY", "La quantité doit être un entier positif."
                    ) from None
                if value < 1:
                    raise ProjectDomainError(
                        "INVALID_QUANTITY", "La quantité doit être un entier positif."
                    )
            elif field in {"rotation_allowed", "individual_cutting"}:
                value = self._normalize_bool(value)
            elif field == "support_color_hex":
                continue
            else:
                value = str(value or "").strip()
                if field == "name" and not value:
                    raise ProjectDomainError(
                        "ITEM_NAME_REQUIRED", "Le nom de la ligne est obligatoire."
                    )
            normalized[field] = value
        if "support_color_hex" in data or "support_color_multicolor" in data:
            normalized["support_color_hex"] = self._normalize_support_color(
                data.get("support_color_hex"),
                multicolor=self._normalize_bool(data.get("support_color_multicolor")),
            )
        if require_all:
            for required in {"name", "width_mm", "height_mm", "quantity"}:
                if required not in normalized:
                    raise ProjectDomainError(
                        "ITEM_FIELD_REQUIRED", f"Le champ {required} est obligatoire."
                    )
        return normalized

    def _positive_decimal(self, raw, field):
        try:
            value = Decimal(str(raw).replace(",", "."))
        except (InvalidOperation, TypeError):
            raise ProjectDomainError(
                "INVALID_DIMENSION", "Les dimensions doivent être positives."
            ) from None
        if value <= 0:
            raise ProjectDomainError("INVALID_DIMENSION", "Les dimensions doivent être positives.")
        return value.quantize(Decimal("0.01"))

    def _normalize_bool(self, value):
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes", "on"}

    def _normalize_support_color(self, raw, *, multicolor: bool = False) -> str:
        if multicolor or str(raw or "").strip().lower() in {
            SUPPORT_COLOR_MULTICOLOR,
            "multicolor",
            "#multicolor",
        }:
            return SUPPORT_COLOR_MULTICOLOR
        cleaned = str(raw or "").strip()
        if not cleaned:
            return ""
        if not cleaned.startswith("#"):
            cleaned = f"#{cleaned}"
        if len(cleaned) != 7:
            raise ProjectDomainError(
                "INVALID_SUPPORT_COLOR",
                "Couleur support : format #RRGGBB attendu.",
            )
        try:
            int(cleaned[1:], 16)
        except ValueError as error:
            raise ProjectDomainError(
                "INVALID_SUPPORT_COLOR",
                "Couleur support : format #RRGGBB attendu.",
            ) from error
        return cleaned.lower()

    def _normalize_shipping_address(self, value):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise ProjectDomainError("INVALID_SHIPPING_ADDRESS", "L'adresse doit être un objet.")
        return {str(key): str(item).strip() for key, item in value.items() if str(item).strip()}

    def _get_item(self, project, public_id, *, for_update=False):
        queryset = B2BOrderProjectItem.objects.for_project(project)
        if for_update:
            queryset = queryset.select_for_update()
        item = queryset.filter(public_id=public_id).first()
        if item is None:
            raise ProjectDomainError("PROJECT_ITEM_NOT_FOUND", "Ligne de projet introuvable.")
        return item

    def _lock(self, project):
        return (
            B2BOrderProject.objects.select_for_update()
            .select_related("customer")
            .get(pk=project.pk)
        )

    def _ensure_editable(self, project):
        if not self.transitions.is_editable(project.status):
            raise ProjectDomainError(
                "PROJECT_NOT_EDITABLE",
                "Le projet ne peut plus être modifié dans son statut actuel.",
                {"current_status": project.status},
            )

    def _transition_rejected(self, project, actor, target, source):
        self._audit(
            "transition_rejected",
            project=project,
            actor=actor,
            source=source,
            status=AuditLogEntry.Status.FAILURE,
            metadata={"current_status": project.status, "requested_status": target},
        )

    def _audit(
        self, event, *, project, actor, source, status=AuditLogEntry.Status.SUCCESS, metadata=None
    ):
        record_event(
            action=f"b2b_order_project.{event}",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=project,
            status=status,
            metadata={
                "customer_public_id": str(project.customer.public_id),
                "project_public_id": str(project.public_id),
                "source": source,
                **(metadata or {}),
            },
        )

    def _base_queryset(self):
        return B2BOrderProject.objects.select_related(
            "customer", "created_by", "converted_order"
        ).prefetch_related("items__asset__current_version__analysis")
