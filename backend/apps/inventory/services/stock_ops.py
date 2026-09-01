from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from apps.auditlog.services import record_event
from apps.customers.models import Customer
from apps.inventory.models import (
    SkuKind,
    StockBalance,
    StockMovement,
    StockOwnerKind,
    StorageLocation,
    WarehouseZone,
)
from apps.pod.models import BlankVariant
from apps.pod.services.validation import clean_sku, require_staff_perm, validation_message


class StockOpsService:
    view_permission = "pod.access_pod_atelier"
    manage_permission = "inventory.manage_warehouse"

    def eligible_customers(self, *, actor):
        require_staff_perm(
            actor,
            self.view_permission,
            source="inventory.stock",
            action="inventory.stock.permission_rejected",
        )
        if not actor.has_perm("customers.view_customer"):
            return Customer.objects.none()
        return Customer.objects.filter(is_active=True).order_by("name")

    def receive_blank(
        self,
        *,
        actor,
        source: str,
        blank_variant_public_id,
        location_public_id,
        quantity: int,
        owner_kind: str = StockOwnerKind.ATELIER,
        customer_public_id=None,
    ) -> StockBalance:
        return self._move(
            actor=actor,
            source=source,
            kind=StockMovement.Kind.RECEIPT,
            sku_kind=SkuKind.BLANK,
            blank_variant_public_id=blank_variant_public_id,
            finished_sku="",
            location_public_id=location_public_id,
            scanned_bin_code="",
            quantity=quantity,
            owner_kind=owner_kind,
            customer_public_id=customer_public_id,
            delta=+1,
        )

    def pick_blank(
        self,
        *,
        actor,
        source: str,
        blank_variant_public_id,
        scanned_bin_code: str,
        quantity: int,
        owner_kind: str = StockOwnerKind.ATELIER,
        customer_public_id=None,
    ) -> StockBalance:
        return self._move(
            actor=actor,
            source=source,
            kind=StockMovement.Kind.PICK,
            sku_kind=SkuKind.BLANK,
            blank_variant_public_id=blank_variant_public_id,
            finished_sku="",
            location_public_id=None,
            scanned_bin_code=scanned_bin_code,
            quantity=quantity,
            owner_kind=owner_kind,
            customer_public_id=customer_public_id,
            delta=-1,
        )

    def putaway_return(
        self,
        *,
        actor,
        source: str,
        blank_variant_public_id,
        location_public_id,
        quantity: int,
        owner_kind: str = StockOwnerKind.ATELIER,
        customer_public_id=None,
    ) -> StockBalance:
        return self._move(
            actor=actor,
            source=source,
            kind=StockMovement.Kind.PUTAWAY,
            sku_kind=SkuKind.BLANK,
            blank_variant_public_id=blank_variant_public_id,
            finished_sku="",
            location_public_id=location_public_id,
            scanned_bin_code="",
            quantity=quantity,
            owner_kind=owner_kind,
            customer_public_id=customer_public_id,
            delta=+1,
        )

    def receive_finished(
        self,
        *,
        actor,
        source: str,
        finished_sku: str,
        location_public_id,
        quantity: int,
        owner_kind: str = StockOwnerKind.ATELIER,
        customer_public_id=None,
    ) -> StockBalance:
        return self._move(
            actor=actor,
            source=source,
            kind=StockMovement.Kind.RECEIPT,
            sku_kind=SkuKind.FINISHED,
            blank_variant_public_id=None,
            finished_sku=finished_sku,
            location_public_id=location_public_id,
            scanned_bin_code="",
            quantity=quantity,
            owner_kind=owner_kind,
            customer_public_id=customer_public_id,
            delta=+1,
        )

    def pick_finished(
        self,
        *,
        actor,
        source: str,
        finished_sku: str,
        scanned_bin_code: str,
        quantity: int,
        owner_kind: str = StockOwnerKind.ATELIER,
        customer_public_id=None,
    ) -> StockBalance:
        return self._move(
            actor=actor,
            source=source,
            kind=StockMovement.Kind.PICK,
            sku_kind=SkuKind.FINISHED,
            blank_variant_public_id=None,
            finished_sku=finished_sku,
            location_public_id=None,
            scanned_bin_code=scanned_bin_code,
            quantity=quantity,
            owner_kind=owner_kind,
            customer_public_id=customer_public_id,
            delta=-1,
        )

    def _resolve_owner(self, *, owner_kind: str, customer_public_id):
        kind = (owner_kind or StockOwnerKind.ATELIER).strip().lower()
        if kind == StockOwnerKind.CUSTOMER:
            customer = Customer.objects.filter(public_id=customer_public_id, is_active=True).first()
            if customer is None:
                raise ValidationError("Client introuvable pour le stock propriétaire.")
            return StockOwnerKind.CUSTOMER, customer
        if kind != StockOwnerKind.ATELIER:
            raise ValidationError("Type de propriétaire stock invalide.")
        return StockOwnerKind.ATELIER, None

    def _assert_zone(
        self, *, kind: str, owner_kind: str, sku_kind: str, location: StorageLocation
    ) -> None:
        zone_kind = location.zone.kind
        if kind == StockMovement.Kind.PUTAWAY and zone_kind != WarehouseZone.Kind.RETURNS:
            raise ValidationError("Putaway retour : zone RETURNS requise.")
        if kind != StockMovement.Kind.RECEIPT:
            return
        if sku_kind == SkuKind.FINISHED and zone_kind != WarehouseZone.Kind.FINISHED:
            raise ValidationError("SKU fini : zone FINISHED requise.")
        if sku_kind == SkuKind.BLANK and zone_kind == WarehouseZone.Kind.FINISHED:
            raise ValidationError("Blank : zone FINISHED interdite.")
        if sku_kind == SkuKind.BLANK:
            if owner_kind == StockOwnerKind.CUSTOMER and zone_kind != WarehouseZone.Kind.CLIENT:
                raise ValidationError("Stock client : zone CLIENT requise.")
            if owner_kind == StockOwnerKind.ATELIER and zone_kind == WarehouseZone.Kind.CLIENT:
                raise ValidationError("Stock atelier : zone CLIENT interdite.")

    def _move(
        self,
        *,
        actor,
        source: str,
        kind: str,
        sku_kind: str,
        blank_variant_public_id,
        finished_sku: str,
        location_public_id,
        scanned_bin_code: str,
        quantity: int,
        owner_kind: str,
        customer_public_id,
        delta: int,
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
                resolved_owner, customer = self._resolve_owner(
                    owner_kind=owner_kind, customer_public_id=customer_public_id
                )
                variant = None
                sku = ""
                if sku_kind == SkuKind.FINISHED:
                    sku = clean_sku(finished_sku, field_label="SKU fini")
                else:
                    variant = (
                        BlankVariant.objects.select_for_update()
                        .filter(public_id=blank_variant_public_id)
                        .first()
                    )
                    if variant is None:
                        raise ValidationError("Variante blank introuvable.")
                if kind == StockMovement.Kind.PICK:
                    bin_code = (scanned_bin_code or "").strip().upper()
                    if not bin_code:
                        raise ValidationError("Scan du bin obligatoire (POD-17).")
                    location = (
                        StorageLocation.objects.select_for_update()
                        .filter(code__iexact=bin_code, is_active=True)
                        .first()
                    )
                    if location is None:
                        raise ValidationError("Bin scanné introuvable.")
                    scanned = bin_code
                else:
                    location = (
                        StorageLocation.objects.select_for_update()
                        .filter(public_id=location_public_id, is_active=True)
                        .first()
                    )
                    if location is None:
                        raise ValidationError("Emplacement introuvable.")
                    scanned = location.code
                    self._assert_zone(
                        kind=kind,
                        owner_kind=resolved_owner,
                        sku_kind=sku_kind,
                        location=location,
                    )
                balance, _ = StockBalance.objects.select_for_update().get_or_create(
                    sku_kind=sku_kind,
                    blank_variant=variant,
                    finished_sku=sku,
                    location=location,
                    owner_kind=resolved_owner,
                    customer=customer,
                    defaults={"qty_on_hand": 0, "qty_reserved": 0},
                )
                if delta < 0 and balance.qty_available < quantity:
                    raise ValidationError("Stock insuffisant sur ce bin (POD-18).")
                StockBalance.objects.filter(pk=balance.pk).update(
                    qty_on_hand=F("qty_on_hand") + (quantity if delta > 0 else -quantity)
                )
                balance.refresh_from_db()
                StockMovement.objects.create(
                    kind=kind,
                    sku_kind=sku_kind,
                    blank_variant=variant,
                    finished_sku=sku,
                    from_location=location if delta < 0 else None,
                    to_location=location if delta > 0 else None,
                    owner_kind=resolved_owner,
                    quantity=quantity,
                    scanned_bin_code=scanned,
                    actor=actor,
                )
                action = {
                    StockMovement.Kind.RECEIPT: "inventory.stock.received",
                    StockMovement.Kind.PICK: "inventory.stock.picked",
                    StockMovement.Kind.PUTAWAY: "inventory.stock.putaway",
                }[kind]
                record_event(
                    action=action,
                    actor=actor,
                    target=balance,
                    metadata={
                        "source": source,
                        "qty": quantity,
                        "bin": scanned,
                        "owner": resolved_owner,
                    },
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
