from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from apps.auditlog.services import record_event
from apps.inventory.models import SkuKind, StockBalance, StockMovement, StockOwnerKind


class BlankStockReservationService:
    """Atomic atelier-stock reservation primitives for one POD blank unit."""

    @transaction.atomic
    def reserve_atelier_blank(
        self,
        *,
        actor,
        source: str,
        blank_variant,
        location_code: str,
    ) -> StockBalance:
        code = (location_code or "").strip().upper()
        if not code:
            raise ValidationError("Aucun bin atelier configuré pour ce blank.")
        balance = (
            StockBalance.objects.select_for_update()
            .select_related("location", "blank_variant__blank")
            .filter(
                sku_kind=SkuKind.BLANK,
                blank_variant=blank_variant,
                blank_variant__is_active=True,
                blank_variant__blank__is_active=True,
                finished_sku="",
                location__code__iexact=code,
                location__is_active=True,
                location__zone__is_active=True,
                location__zone__warehouse__is_active=True,
                owner_kind=StockOwnerKind.ATELIER,
                customer__isnull=True,
            )
            .first()
        )
        if balance is None or balance.qty_available < 1:
            raise ValidationError(f"Stock atelier insuffisant sur le bin {code} (POD-18).")
        StockBalance.objects.filter(pk=balance.pk).update(qty_reserved=F("qty_reserved") + 1)
        balance.refresh_from_db()
        record_event(
            action="inventory.stock.reserved",
            actor=actor,
            target=balance,
            metadata={
                "source": source,
                "qty": 1,
                "bin": code,
                "owner": StockOwnerKind.ATELIER,
            },
        )
        return balance

    @transaction.atomic
    def consume_atelier_reservation(
        self,
        *,
        actor,
        source: str,
        balance_public_id,
        scanned_bin_code: str,
        note: str = "",
    ) -> StockBalance:
        code = (scanned_bin_code or "").strip().upper()
        if not code:
            raise ValidationError("Scan du bin obligatoire (POD-17).")
        balance = (
            StockBalance.objects.select_for_update()
            .select_related("location")
            .filter(
                public_id=balance_public_id,
                sku_kind=SkuKind.BLANK,
                owner_kind=StockOwnerKind.ATELIER,
                customer__isnull=True,
            )
            .first()
        )
        if balance is None:
            raise ValidationError("Réservation de stock atelier introuvable.")
        if balance.location.code.upper() != code:
            raise ValidationError(
                f"Bin incorrect : scannez {balance.location.code.upper()} pour cette pièce."
            )
        if balance.qty_reserved < 1 or balance.qty_on_hand < 1:
            raise ValidationError("Réservation de stock invalide ou déjà consommée.")
        StockBalance.objects.filter(pk=balance.pk).update(
            qty_on_hand=F("qty_on_hand") - 1,
            qty_reserved=F("qty_reserved") - 1,
        )
        balance.refresh_from_db()
        StockMovement.objects.create(
            kind=StockMovement.Kind.PICK,
            sku_kind=SkuKind.BLANK,
            blank_variant=balance.blank_variant,
            finished_sku="",
            from_location=balance.location,
            owner_kind=StockOwnerKind.ATELIER,
            quantity=1,
            scanned_bin_code=code,
            note=(note or "")[:255],
            actor=actor,
        )
        record_event(
            action="inventory.stock.reservation_picked",
            actor=actor,
            target=balance,
            metadata={
                "source": source,
                "qty": 1,
                "bin": code,
                "owner": StockOwnerKind.ATELIER,
            },
        )
        return balance

    @transaction.atomic
    def release_atelier_reservation(
        self,
        *,
        actor,
        source: str,
        balance_public_id,
        reason: str = "",
    ) -> StockBalance:
        balance = (
            StockBalance.objects.select_for_update()
            .select_related("location")
            .filter(
                public_id=balance_public_id,
                sku_kind=SkuKind.BLANK,
                owner_kind=StockOwnerKind.ATELIER,
                customer__isnull=True,
            )
            .first()
        )
        if balance is None:
            raise ValidationError("Réservation de stock atelier introuvable.")
        if balance.qty_reserved < 1:
            raise ValidationError("Aucune unité réservée à libérer.")
        StockBalance.objects.filter(pk=balance.pk).update(qty_reserved=F("qty_reserved") - 1)
        balance.refresh_from_db()
        record_event(
            action="inventory.stock.reservation_released",
            actor=actor,
            target=balance,
            metadata={
                "source": source,
                "qty": 1,
                "bin": balance.location.code,
                "owner": StockOwnerKind.ATELIER,
                "reason": (reason or "")[:120],
            },
        )
        return balance
