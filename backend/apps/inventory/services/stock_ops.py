from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from apps.auditlog.services import record_event
from apps.inventory.models import (
    SkuKind,
    StockBalance,
    StockMovement,
    StockOwnerKind,
    StorageLocation,
)
from apps.pod.models import BlankVariant
from apps.pod.services.validation import require_staff_perm, validation_message


class StockOpsService:
    view_permission = "pod.access_pod_atelier"
    manage_permission = "inventory.manage_warehouse"

    def receive_blank(
        self,
        *,
        actor,
        source: str,
        blank_variant_public_id,
        location_public_id,
        quantity: int,
    ) -> StockBalance:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="inventory.stock.permission_rejected",
        )
        if quantity < 1:
            raise ValidationError("Quantité invalide.")
        try:
            with transaction.atomic():
                variant = BlankVariant.objects.select_for_update().filter(
                    public_id=blank_variant_public_id
                ).first()
                location = StorageLocation.objects.select_for_update().filter(
                    public_id=location_public_id, is_active=True
                ).first()
                if variant is None:
                    raise ValidationError("Variante blank introuvable.")
                if location is None:
                    raise ValidationError("Emplacement introuvable.")
                balance, _ = StockBalance.objects.select_for_update().get_or_create(
                    sku_kind=SkuKind.BLANK,
                    blank_variant=variant,
                    finished_sku="",
                    location=location,
                    owner_kind=StockOwnerKind.ATELIER,
                    customer=None,
                    defaults={"qty_on_hand": 0, "qty_reserved": 0},
                )
                StockBalance.objects.filter(pk=balance.pk).update(
                    qty_on_hand=F("qty_on_hand") + quantity
                )
                balance.refresh_from_db()
                StockMovement.objects.create(
                    kind=StockMovement.Kind.RECEIPT,
                    sku_kind=SkuKind.BLANK,
                    blank_variant=variant,
                    to_location=location,
                    owner_kind=StockOwnerKind.ATELIER,
                    quantity=quantity,
                    scanned_bin_code=location.code,
                    actor=actor,
                )
                record_event(
                    action="inventory.stock.received",
                    actor=actor,
                    target=balance,
                    metadata={"source": source, "qty": quantity, "bin": location.code},
                )
                return balance
        except ValidationError as exc:
            record_event(
                action="inventory.stock.rejected",
                actor=actor,
                status="failure",
                message=validation_message(exc),
                metadata={"source": source},
            )
            raise

    def pick_blank(
        self,
        *,
        actor,
        source: str,
        blank_variant_public_id,
        scanned_bin_code: str,
        quantity: int,
    ) -> StockBalance:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="inventory.stock.permission_rejected",
        )
        bin_code = (scanned_bin_code or "").strip().upper()
        if not bin_code:
            raise ValidationError("Scan du bin obligatoire (POD-17).")
        if quantity < 1:
            raise ValidationError("Quantité invalide.")
        try:
            with transaction.atomic():
                variant = BlankVariant.objects.select_for_update().filter(
                    public_id=blank_variant_public_id
                ).first()
                location = StorageLocation.objects.select_for_update().filter(
                    code__iexact=bin_code, is_active=True
                ).first()
                if variant is None:
                    raise ValidationError("Variante blank introuvable.")
                if location is None:
                    raise ValidationError("Bin scanné introuvable.")
                balance = (
                    StockBalance.objects.select_for_update()
                    .filter(
                        sku_kind=SkuKind.BLANK,
                        blank_variant=variant,
                        location=location,
                        owner_kind=StockOwnerKind.ATELIER,
                        customer=None,
                    )
                    .first()
                )
                available = balance.qty_available if balance else 0
                if available < quantity:
                    raise ValidationError(
                        "Stock insuffisant sur ce bin (POD-18)."
                    )
                StockBalance.objects.filter(pk=balance.pk).update(
                    qty_on_hand=F("qty_on_hand") - quantity
                )
                balance.refresh_from_db()
                StockMovement.objects.create(
                    kind=StockMovement.Kind.PICK,
                    sku_kind=SkuKind.BLANK,
                    blank_variant=variant,
                    from_location=location,
                    owner_kind=StockOwnerKind.ATELIER,
                    quantity=quantity,
                    scanned_bin_code=bin_code,
                    actor=actor,
                )
                record_event(
                    action="inventory.stock.picked",
                    actor=actor,
                    target=balance,
                    metadata={"source": source, "qty": quantity, "bin": bin_code},
                )
                return balance
        except ValidationError as exc:
            record_event(
                action="inventory.stock.rejected",
                actor=actor,
                status="failure",
                message=validation_message(exc),
                metadata={"source": source},
            )
            raise

    def putaway_return(
        self,
        *,
        actor,
        source: str,
        blank_variant_public_id,
        location_public_id,
        quantity: int,
    ) -> StockBalance:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="inventory.stock.permission_rejected",
        )
        if quantity < 1:
            raise ValidationError("Quantité invalide.")
        try:
            with transaction.atomic():
                variant = BlankVariant.objects.select_for_update().filter(
                    public_id=blank_variant_public_id
                ).first()
                location = StorageLocation.objects.select_for_update().filter(
                    public_id=location_public_id, is_active=True
                ).first()
                if variant is None or location is None:
                    raise ValidationError("Blank ou emplacement introuvable.")
                if location.zone.kind != location.zone.Kind.RETURNS:
                    raise ValidationError("Putaway retour : zone RETURNS requise.")
                balance, _ = StockBalance.objects.select_for_update().get_or_create(
                    sku_kind=SkuKind.BLANK,
                    blank_variant=variant,
                    finished_sku="",
                    location=location,
                    owner_kind=StockOwnerKind.ATELIER,
                    customer=None,
                    defaults={"qty_on_hand": 0, "qty_reserved": 0},
                )
                StockBalance.objects.filter(pk=balance.pk).update(
                    qty_on_hand=F("qty_on_hand") + quantity
                )
                balance.refresh_from_db()
                StockMovement.objects.create(
                    kind=StockMovement.Kind.PUTAWAY,
                    sku_kind=SkuKind.BLANK,
                    blank_variant=variant,
                    to_location=location,
                    owner_kind=StockOwnerKind.ATELIER,
                    quantity=quantity,
                    scanned_bin_code=location.code,
                    actor=actor,
                )
                record_event(
                    action="inventory.stock.putaway",
                    actor=actor,
                    target=balance,
                    metadata={"source": source, "bin": location.code},
                )
                return balance
        except ValidationError as exc:
            record_event(
                action="inventory.stock.rejected",
                actor=actor,
                status="failure",
                message=validation_message(exc),
                metadata={"source": source},
            )
            raise
