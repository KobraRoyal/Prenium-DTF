from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.auditlog.services import record_event
from apps.inventory.models import (
    ProductLocationRule,
    SkuKind,
    StockBalance,
    StockOwnerKind,
    StorageLocation,
    Warehouse,
    WarehouseZone,
)
from apps.pod.models import BlankVariant
from apps.pod.services.validation import (
    clean_location_code,
    require_staff_perm,
    validation_message,
)

DEFAULT_WAREHOUSE_CODE = "atl-01"
DEFAULT_ZONES = (
    ("blanks", "Vierges POD", WarehouseZone.Kind.BLANKS),
    ("finished", "Produits finis", WarehouseZone.Kind.FINISHED),
    ("returns", "Retours", WarehouseZone.Kind.RETURNS),
    ("prod", "Staging production", WarehouseZone.Kind.PRODUCTION),
    ("client", "Stock client", WarehouseZone.Kind.CLIENT),
)


def _is_checked(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "on", "yes"}


class WarehouseLayoutService:
    view_permission = "pod.access_pod_atelier"
    manage_permission = "inventory.manage_warehouse"

    def ensure_default_layout(self, *, actor) -> Warehouse:
        require_staff_perm(
            actor,
            self.view_permission,
            source="inventory.warehouse",
            action="inventory.warehouse.permission_rejected",
        )
        warehouse, _created = Warehouse.objects.get_or_create(
            code=DEFAULT_WAREHOUSE_CODE,
            defaults={"name": "Atelier Prenium", "is_active": True},
        )
        for code, name, kind in DEFAULT_ZONES:
            WarehouseZone.objects.get_or_create(
                warehouse=warehouse,
                code=code,
                defaults={"name": name, "kind": kind, "is_active": True},
            )
        return warehouse

    def list_zones(self, *, actor):
        require_staff_perm(
            actor,
            self.view_permission,
            source="inventory.warehouse",
            action="inventory.warehouse.permission_rejected",
        )
        return WarehouseZone.objects.filter(
            warehouse__code=DEFAULT_WAREHOUSE_CODE,
        ).prefetch_related("locations")

    def get_location(self, *, actor, location_public_id) -> StorageLocation:
        require_staff_perm(
            actor,
            self.view_permission,
            source="inventory.location",
            action="inventory.warehouse.permission_rejected",
        )
        location = (
            StorageLocation.objects.select_related("zone", "zone__warehouse")
            .filter(public_id=location_public_id)
            .first()
        )
        if location is None:
            raise ValidationError("Emplacement introuvable.")
        return location

    def location_contents(self, *, actor, location: StorageLocation):
        require_staff_perm(
            actor,
            self.manage_permission,
            source="inventory.location",
            action="inventory.warehouse.permission_rejected",
        )
        return {
            "rules": location.product_rules.select_related("blank_variant", "customer"),
            "balances": location.stock_balances.select_related("blank_variant", "customer"),
        }

    def create_location(self, *, actor, source: str, data: dict) -> StorageLocation:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="inventory.warehouse.permission_rejected",
        )
        try:
            code = clean_location_code(data.get("code", ""))
            label = (data.get("label") or "").strip()
            with transaction.atomic():
                zone = (
                    WarehouseZone.objects.select_for_update()
                    .filter(
                        public_id=data.get("zone_public_id"),
                        warehouse__code=DEFAULT_WAREHOUSE_CODE,
                        warehouse__is_active=True,
                        is_active=True,
                    )
                    .first()
                )
                if zone is None:
                    raise ValidationError("Zone introuvable.")
                location = StorageLocation(zone=zone, code=code, label=label)
                location.full_clean()
                location.save()
                record_event(
                    action="inventory.location.created",
                    actor=actor,
                    target=location,
                    metadata={"source": source, "code": location.code},
                )
                return location
        except IntegrityError as exc:
            error = ValidationError("Ce code emplacement existe déjà.")
            record_event(
                action="inventory.location.create_rejected",
                actor=actor,
                status="failure",
                message=validation_message(error),
                metadata={"source": source},
            )
            raise error from exc
        except ValidationError as exc:
            record_event(
                action="inventory.location.create_rejected",
                actor=actor,
                status="failure",
                message=validation_message(exc),
                metadata={"source": source},
            )
            raise

    def update_location(
        self, *, actor, source: str, location_public_id, data: dict
    ) -> StorageLocation:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="inventory.warehouse.permission_rejected",
        )
        try:
            with transaction.atomic():
                location = (
                    StorageLocation.objects.select_for_update()
                    .select_related("zone", "zone__warehouse")
                    .filter(public_id=location_public_id)
                    .first()
                )
                if location is None:
                    raise ValidationError("Emplacement introuvable.")
                requested_active = _is_checked(data.get("is_active"))
                if location.is_active and not requested_active:
                    rule_count = len(
                        list(
                            ProductLocationRule.objects.select_for_update()
                            .filter(location=location)
                            .values_list("pk", flat=True)
                        )
                    )
                    balances = list(
                        StockBalance.objects.select_for_update().filter(
                            location=location,
                        )
                    )
                    stocked_count = sum(
                        1
                        for balance in balances
                        if balance.qty_on_hand > 0 or balance.qty_reserved > 0
                    )
                    if rule_count or stocked_count:
                        raise ValidationError(
                            "Désactivation impossible : déplacez le stock et réaffectez "
                            "les règles avant désactivation."
                        )
                if requested_active and (
                    not location.zone.is_active or not location.zone.warehouse.is_active
                ):
                    raise ValidationError(
                        "Réactivation impossible : la zone ou l’entrepôt est inactif."
                    )
                previous = {
                    "label": location.label,
                    "is_active": location.is_active,
                }
                location.label = (data.get("label") or "").strip()
                location.is_active = requested_active
                location.full_clean()
                location.save(update_fields=["label", "is_active", "updated_at"])
                record_event(
                    action="inventory.location.updated",
                    actor=actor,
                    target=location,
                    metadata={
                        "source": source,
                        "previous": previous,
                        "changes": {
                            "label": location.label,
                            "is_active": location.is_active,
                        },
                    },
                )
                return location
        except ValidationError as exc:
            record_event(
                action="inventory.location.update_rejected",
                actor=actor,
                status="failure",
                message=validation_message(exc),
                metadata={"source": source},
            )
            raise

    def set_blank_default_location(
        self,
        *,
        actor,
        source: str,
        variant_public_id,
        location_public_id,
        blank_public_id=None,
    ) -> ProductLocationRule:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="inventory.warehouse.permission_rejected",
        )
        try:
            with transaction.atomic():
                variant = (
                    BlankVariant.objects.select_for_update()
                    .filter(
                        public_id=variant_public_id,
                        is_active=True,
                        blank__is_active=True,
                    )
                    .first()
                )
                location = (
                    StorageLocation.objects.select_for_update()
                    .filter(
                        public_id=location_public_id,
                        is_active=True,
                        zone__is_active=True,
                        zone__warehouse__is_active=True,
                    )
                    .first()
                )
                if variant is None:
                    raise ValidationError("Variante blank introuvable.")
                if blank_public_id is not None and str(variant.blank.public_id) != str(
                    blank_public_id
                ):
                    raise ValidationError("Variante blank introuvable pour ce support.")
                if location is None:
                    raise ValidationError("Emplacement introuvable.")
                rule, _created = ProductLocationRule.objects.update_or_create(
                    sku_kind=SkuKind.BLANK,
                    blank_variant=variant,
                    finished_sku="",
                    owner_kind=StockOwnerKind.ATELIER,
                    customer=None,
                    defaults={"location": location},
                )
                record_event(
                    action="inventory.location_rule.saved",
                    actor=actor,
                    target=rule,
                    metadata={
                        "source": source,
                        "variant": str(variant.public_id),
                        "location": location.code,
                    },
                )
                return rule
        except ValidationError as exc:
            record_event(
                action="inventory.location_rule.save_rejected",
                actor=actor,
                status="failure",
                message=validation_message(exc),
                metadata={"source": source},
            )
            raise

    def available_qty_for_blank(self, *, actor, variant: BlankVariant, owner_kind: str) -> int:
        require_staff_perm(
            actor,
            self.view_permission,
            source="inventory.stock",
            action="inventory.warehouse.permission_rejected",
        )
        total = 0
        for balance in StockBalance.objects.filter(
            sku_kind=SkuKind.BLANK,
            blank_variant=variant,
            owner_kind=owner_kind,
        ):
            total += balance.qty_available
        return total
