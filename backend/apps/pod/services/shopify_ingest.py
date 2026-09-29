from __future__ import annotations

import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.pod.models import (
    PodRipWorkItem,
    PodShopifyOrder,
    PodUnit,
    ShopifyStore,
    ShopifyVariant,
    ShopifyWebhookReceipt,
)
from apps.pod.services.rip_lots import PodRipLotService
from apps.pod.services.shopify_webhook_security import authenticate_shopify_webhook
from apps.pod.services.variant_config import CONFIG_STATUS_POD, VariantConfigService

SUPPORTED_TOPICS = frozenset(
    {
        "orders/create",
        "orders/updated",
        "orders/cancelled",
    }
)


class ShopifyFulfillmentIngestService:
    def accept_delivery(
        self,
        *,
        raw_body: bytes,
        hmac_header: str,
        shop_domain: str,
        webhook_id: str,
        topic: str,
    ) -> tuple[ShopifyWebhookReceipt, bool]:
        """Persist a verified delivery before acknowledging it to Shopify."""
        store = authenticate_shopify_webhook(
            raw_body=raw_body,
            hmac_header=hmac_header,
            shop_domain=shop_domain,
        )
        event_id = (webhook_id or "").strip()
        if not event_id:
            raise ValidationError("Identifiant de livraison Shopify manquant.")
        topic_key = (topic or "orders/create").strip().lower()
        if topic_key not in SUPPORTED_TOPICS:
            raise ValidationError("Topic Shopify non pris en charge.")
        with transaction.atomic():
            ShopifyStore.objects.select_for_update().get(pk=store.pk)
            return ShopifyWebhookReceipt.objects.get_or_create(
                webhook_id=event_id,
                defaults={
                    "shop_domain": store.shop_domain,
                    "topic": topic_key,
                    "raw_body": raw_body,
                    "status": ShopifyWebhookReceipt.Status.PENDING,
                },
            )

    def process_receipt(self, *, receipt_public_id: str) -> dict:
        receipt = ShopifyWebhookReceipt.objects.filter(public_id=receipt_public_id).first()
        if receipt is None:
            raise ValidationError("Livraison Shopify introuvable.")
        if receipt.status == ShopifyWebhookReceipt.Status.PROCESSED:
            return {
                "queued": 0,
                "skipped": 0,
                "updated": 0,
                "cancelled": 0,
                "order": "",
                "duplicate": True,
            }
        return self.ingest(
            raw_body=bytes(receipt.raw_body),
            hmac_header="",
            shop_domain=receipt.shop_domain,
            webhook_id=receipt.webhook_id,
            topic=receipt.topic,
            trusted_receipt_public_id=str(receipt.public_id),
        )

    def ingest(
        self,
        *,
        raw_body: bytes,
        hmac_header: str,
        shop_domain: str,
        webhook_id: str = "",
        topic: str = "orders/create",
        trusted_receipt_public_id: str = "",
    ) -> dict:
        if trusted_receipt_public_id:
            store = ShopifyStore.objects.filter(shop_domain=shop_domain, is_active=True).first()
            if store is None:
                raise ValidationError("Boutique Shopify inactive ou introuvable.")
        else:
            store = authenticate_shopify_webhook(
                raw_body=raw_body,
                hmac_header=hmac_header,
                shop_domain=shop_domain,
            )

        topic_key = (topic or "orders/create").strip().lower() or "orders/create"
        if topic_key not in SUPPORTED_TOPICS:
            record_event(
                action="pod.shopify.webhook_ignored_topic",
                metadata={"shop": shop_domain, "topic": topic_key},
            )
            return {
                "queued": 0,
                "skipped": 0,
                "updated": 0,
                "cancelled": 0,
                "order": "",
                "ignored": True,
            }

        event_id = (webhook_id or "").strip()
        if not event_id:
            raise ValidationError("Identifiant de livraison Shopify manquant.")

        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError("Payload JSON invalide.") from exc
        if not isinstance(payload, dict):
            raise ValidationError("Payload Shopify invalide.")

        order_number = str(
            payload.get("name") or payload.get("order_number") or payload.get("id") or ""
        ).strip()
        if not order_number:
            raise ValidationError("Numéro de commande Shopify manquant.")
        external_order_id = str(payload.get("id") or "").strip()

        line_items = payload.get("line_items")
        if topic_key != "orders/cancelled" and (
            not isinstance(line_items, list)
            or any(not isinstance(line, dict) for line in line_items)
        ):
            raise ValidationError("Lignes Shopify manquantes ou invalides.")

        # The receipt and the business changes must commit together. A failed
        # delivery can then be retried with the same Shopify webhook ID.
        with transaction.atomic():
            # Serialize deliveries for one store, including different webhook IDs.
            store = ShopifyStore.objects.select_for_update().get(pk=store.pk)
            if trusted_receipt_public_id:
                receipt = (
                    ShopifyWebhookReceipt.objects.select_for_update()
                    .filter(
                        public_id=trusted_receipt_public_id,
                        shop_domain=store.shop_domain,
                        webhook_id=event_id,
                        topic=topic_key,
                    )
                    .first()
                )
                if receipt is None:
                    raise ValidationError("Livraison Shopify persistée incohérente.")
                if (
                    receipt.status != ShopifyWebhookReceipt.Status.PROCESSED
                    and bytes(receipt.raw_body) != raw_body
                ):
                    raise ValidationError("Corps de livraison Shopify persistée incohérent.")
            else:
                receipt = ShopifyWebhookReceipt.objects.filter(webhook_id=event_id).first()
                if receipt is None:
                    receipt = ShopifyWebhookReceipt.objects.create(
                        webhook_id=event_id,
                        shop_domain=store.shop_domain,
                        topic=topic_key,
                        raw_body=raw_body,
                        status=ShopifyWebhookReceipt.Status.PENDING,
                    )
            if (
                receipt.status == ShopifyWebhookReceipt.Status.PROCESSED
                or receipt.shop_domain != store.shop_domain
                or receipt.topic != topic_key
                or bytes(receipt.raw_body) != raw_body
            ):
                return {
                    "queued": 0,
                    "skipped": 0,
                    "updated": 0,
                    "cancelled": 0,
                    "order": "",
                    "duplicate": True,
                }

            if topic_key == "orders/cancelled":
                result = self._cancel_order(
                    store=store,
                    order_number=order_number,
                    external_order_id=external_order_id,
                    shop_domain=shop_domain,
                )
            else:
                result = self._sync_order_lines(
                    store=store,
                    order_number=order_number,
                    external_order_id=external_order_id,
                    line_items=line_items,
                    shop_domain=shop_domain,
                    topic=topic_key,
                )
            receipt.status = ShopifyWebhookReceipt.Status.PROCESSED
            receipt.raw_body = b""
            receipt.processed_at = timezone.now()
            receipt.next_retry_at = None
            receipt.last_error = ""
            receipt.save(
                update_fields=[
                    "status",
                    "raw_body",
                    "processed_at",
                    "next_retry_at",
                    "last_error",
                    "updated_at",
                ]
            )
            return result

    def _cancel_order(
        self,
        *,
        store: ShopifyStore,
        order_number: str,
        external_order_id: str,
        shop_domain: str,
    ) -> dict:
        cancelled = 0
        frozen = 0
        with transaction.atomic():
            if external_order_id:
                # Keep the same store -> order -> work item/unit lock order as
                # the QC completion path before freezing a production.
                order = (
                    PodShopifyOrder.objects.select_for_update(of=("self",))
                    .filter(
                        store=store,
                        external_order_id=external_order_id,
                    )
                    .first()
                )
                item_scope = {"shopify_order": order} if order is not None else {"pk__in": []}
            else:
                # A legacy delivery may only mutate legacy rows. Matching it by
                # display number against identity-backed rows would be ambiguous.
                item_scope = {
                    "shopify_order__isnull": True,
                    "shopify_line_item_id__isnull": True,
                    "shopify_order_number": order_number,
                }
            items = list(
                PodRipWorkItem.objects.select_for_update()
                .filter(store=store, **item_scope)
                .exclude(status=PodRipWorkItem.Status.CANCELLED)
            )
            for item in items:
                if item.status == PodRipWorkItem.Status.QUEUED:
                    item.status = PodRipWorkItem.Status.CANCELLED
                    item.skip_reason = "Commande Shopify annulée."
                    item.save(update_fields=["status", "skip_reason", "updated_at"])
                    from apps.pod.services.pick_sessions import PodPickSessionService

                    PodPickSessionService().void_lines_for_work_item(
                        work_item=item,
                        reason="orders/cancelled",
                    )
                    cancelled += 1
                    record_event(
                        action="pod.shopify.work_item_cancelled",
                        target=item,
                        metadata={
                            "shop": shop_domain,
                            "order": order_number,
                            "order_id": external_order_id,
                            "phase": "queued",
                        },
                    )
                    continue
                # INCLUDED / SKIPPED : conserver le lot et l'historique QC,
                # mais bloquer toute pièce non expédiée, y compris déjà posée.
                item.skip_reason = "Commande Shopify annulée — déjà en production."
                item.save(update_fields=["skip_reason", "updated_at"])
                from apps.pod.services.pick_sessions import PodPickSessionService

                PodPickSessionService().void_lines_for_work_item(
                    work_item=item,
                    reason="orders/cancelled-in-production",
                )
                updated_units = (
                    PodUnit.objects.filter(
                        work_item=item,
                    )
                    .exclude(
                        status=PodUnit.Status.ISSUE,
                    )
                    .update(status=PodUnit.Status.ISSUE, updated_at=timezone.now())
                )
                frozen += 1
                record_event(
                    action="pod.shopify.cancel_after_production",
                    target=item,
                    metadata={
                        "shop": shop_domain,
                        "order": order_number,
                        "order_id": external_order_id,
                        "units_flagged": updated_units,
                        "status": item.status,
                    },
                )
        record_event(
            action="pod.shopify.order_cancelled",
            metadata={
                "shop": shop_domain,
                "order": order_number,
                "order_id": external_order_id,
                "cancelled": cancelled,
                "frozen": frozen,
            },
        )
        return {
            "queued": 0,
            "skipped": 0,
            "updated": 0,
            "cancelled": cancelled,
            "frozen": frozen,
            "order": order_number,
        }

    def _sync_order_lines(
        self,
        *,
        store: ShopifyStore,
        order_number: str,
        external_order_id: str,
        line_items: list,
        shop_domain: str,
        topic: str,
    ) -> dict:
        queued = 0
        skipped = 0
        updated = 0
        cancelled = 0
        frozen = 0
        rip = PodRipLotService()
        config_service = VariantConfigService()
        seen_variant_ids: set[int] = set()
        seen_pod_variant_ids: set[int] = set()
        seen_line_item_ids: set[str] = set()
        unresolved_lines = 0
        identity_mode = bool(external_order_id)

        payload_line_ids = [str(line.get("id") or "").strip() for line in line_items]
        if identity_mode and any(not line_id for line_id in payload_line_ids):
            raise ValidationError(
                "Identifiant de ligne Shopify manquant pour une commande identifiée."
            )
        if not identity_mode and any(payload_line_ids):
            raise ValidationError(
                "Identifiant de commande Shopify manquant pour des lignes identifiées."
            )
        if identity_mode and len(payload_line_ids) != len(set(payload_line_ids)):
            raise ValidationError("Identifiants de ligne Shopify dupliqués dans le payload.")

        with transaction.atomic():
            shopify_order = None
            if identity_mode:
                if store.customer_id is None:
                    raise ValidationError(
                        "La boutique Shopify doit être liée à un Customer avant ingestion POD."
                    )
                shopify_order, created = PodShopifyOrder.objects.select_for_update().get_or_create(
                    store=store,
                    external_order_id=external_order_id,
                    defaults={
                        "customer_id": store.customer_id,
                        "order_number": order_number,
                    },
                )
                if not created and shopify_order.customer_id != store.customer_id:
                    raise ValidationError("La commande Shopify appartient à un autre Customer.")
                if shopify_order.order_number != order_number:
                    shopify_order.order_number = order_number
                    shopify_order.save(update_fields=["order_number", "updated_at"])

            for line, external_line_item_id in zip(line_items, payload_line_ids, strict=True):
                sku = str(line.get("sku") or "").strip()
                external_variant_id = str(line.get("variant_id") or "").strip()
                try:
                    qty = int(line.get("quantity") or 0)
                except (TypeError, ValueError):
                    qty = 0
                variants = ShopifyVariant.objects.select_related(
                    "ids_config", "product__store"
                ).filter(product__store=store)
                variant = None
                if external_variant_id:
                    variant = variants.filter(external_id=external_variant_id).first()
                # A provided Shopify variant ID is authoritative. Falling back
                # to a matching SKU here could print the wrong customer's item.
                if variant is None and not external_variant_id and sku:
                    sku_matches = list(variants.filter(sku__iexact=sku)[:2])
                    if len(sku_matches) == 1:
                        variant = sku_matches[0]
                if variant is None:
                    skipped += 1
                    unresolved_lines += 1
                    record_event(
                        action="pod.shopify.line_unmatched",
                        metadata={
                            "shop": shop_domain,
                            "order": order_number,
                            "sku": sku,
                            "variant_id": external_variant_id,
                        },
                    )
                    continue
                seen_variant_ids.add(variant.pk)
                if identity_mode:
                    seen_line_item_ids.add(external_line_item_id)
                config = getattr(variant, "ids_config", None)
                status = config_service.configuration_status(config) if config else "unmanaged"
                if status != CONFIG_STATUS_POD:
                    skipped += 1
                    continue
                if not identity_mode and variant.pk in seen_pod_variant_ids:
                    raise ValidationError(
                        "Commande Shopify ambiguë : plusieurs lignes POD utilisent la même "
                        "variante. Un suivi par identifiant de ligne est requis avant production."
                    )
                seen_pod_variant_ids.add(variant.pk)

                existing_items = PodRipWorkItem.objects.select_for_update().filter(store=store)
                if identity_mode:
                    existing = existing_items.filter(
                        shopify_order=shopify_order,
                        shopify_line_item_id=external_line_item_id,
                    ).first()
                else:
                    existing = (
                        existing_items.filter(
                            shopify_order__isnull=True,
                            shopify_line_item_id__isnull=True,
                            variant=variant,
                            shopify_order_number=order_number,
                        )
                        .exclude(status=PodRipWorkItem.Status.CANCELLED)
                        .order_by("-created_at")
                        .first()
                    )

                if existing is None:
                    if qty < 1:
                        skipped += 1
                        continue
                    rip.enqueue(
                        actor=None,
                        source="shopify_webhook",
                        variant_public_id=variant.public_id,
                        shopify_order_number=order_number,
                        shopify_order=shopify_order,
                        shopify_line_item_id=(external_line_item_id or None),
                        quantity=max(qty, 1),
                        trusted_source=True,
                    )
                    queued += 1
                    continue

                if existing.variant_id != variant.pk:
                    raise ValidationError(
                        "Une ligne Shopify identifiée ne peut pas changer de variante POD."
                    )

                if existing.status == PodRipWorkItem.Status.CANCELLED and qty > 0:
                    existing.status = PodRipWorkItem.Status.QUEUED
                    existing.skip_reason = ""
                    existing.quantity = max(qty, 1)
                    existing.save(update_fields=["status", "skip_reason", "quantity", "updated_at"])
                    updated += 1
                    record_event(
                        action="pod.shopify.work_item_restored",
                        target=existing,
                        metadata={
                            "shop": shop_domain,
                            "order": order_number,
                            "order_id": external_order_id,
                            "line_item_id": external_line_item_id,
                            "quantity": existing.quantity,
                        },
                    )
                    continue

                if existing.status == PodRipWorkItem.Status.INCLUDED:
                    if qty != existing.quantity:
                        frozen += 1
                        record_event(
                            action="pod.shopify.qty_ignored_in_production",
                            target=existing,
                            metadata={
                                "shop": shop_domain,
                                "order": order_number,
                                "order_id": external_order_id,
                                "line_item_id": external_line_item_id,
                                "shopify_qty": qty,
                                "atelier_qty": existing.quantity,
                            },
                        )
                    skipped += 1
                    continue

                if existing.status == PodRipWorkItem.Status.SKIPPED:
                    skipped += 1
                    continue

                # QUEUED
                if qty < 1:
                    existing.status = PodRipWorkItem.Status.CANCELLED
                    existing.skip_reason = "Ligne Shopify retirée / quantité 0."
                    existing.save(update_fields=["status", "skip_reason", "updated_at"])
                    from apps.pod.services.pick_sessions import PodPickSessionService

                    PodPickSessionService().void_lines_for_work_item(
                        work_item=existing,
                        reason="line_removed",
                    )
                    cancelled += 1
                    record_event(
                        action="pod.shopify.work_item_cancelled",
                        target=existing,
                        metadata={
                            "shop": shop_domain,
                            "order": order_number,
                            "order_id": external_order_id,
                            "line_item_id": external_line_item_id,
                            "phase": "line_removed",
                        },
                    )
                    continue

                printed = existing.pick_lines.filter(voided_at__isnull=True).count()
                applied = max(qty, printed, 1)
                if applied != existing.quantity:
                    existing.quantity = applied
                    existing.save(update_fields=["quantity", "updated_at"])
                    updated += 1
                    record_event(
                        action="pod.shopify.quantity_synced",
                        target=existing,
                        metadata={
                            "shop": shop_domain,
                            "order": order_number,
                            "order_id": external_order_id,
                            "line_item_id": external_line_item_id,
                            "quantity": applied,
                            "shopify_qty": qty,
                            "pick_floor": printed,
                            "topic": topic,
                        },
                    )
                else:
                    skipped += 1

            if unresolved_lines:
                raise ValidationError(
                    "Lignes Shopify non résolues : synchronisez le catalogue avant de rejouer."
                )

            # orders/updated : cancel only rows absent from the matching identity domain.
            if topic == "orders/updated":
                if identity_mode:
                    orphans = (
                        PodRipWorkItem.objects.select_for_update()
                        .filter(
                            store=store,
                            shopify_order=shopify_order,
                            shopify_line_item_id__isnull=False,
                            status=PodRipWorkItem.Status.QUEUED,
                        )
                        .exclude(shopify_line_item_id__in=seen_line_item_ids)
                    )
                else:
                    orphans = (
                        PodRipWorkItem.objects.select_for_update()
                        .filter(
                            store=store,
                            shopify_order__isnull=True,
                            shopify_line_item_id__isnull=True,
                            shopify_order_number=order_number,
                            status=PodRipWorkItem.Status.QUEUED,
                        )
                        .exclude(variant_id__in=seen_variant_ids)
                    )
                for item in orphans:
                    item.status = PodRipWorkItem.Status.CANCELLED
                    item.skip_reason = "Ligne absente du webhook orders/updated."
                    item.save(update_fields=["status", "skip_reason", "updated_at"])
                    from apps.pod.services.pick_sessions import PodPickSessionService

                    PodPickSessionService().void_lines_for_work_item(
                        work_item=item,
                        reason="orphan_line",
                    )
                    cancelled += 1
                    record_event(
                        action="pod.shopify.work_item_cancelled",
                        target=item,
                        metadata={
                            "shop": shop_domain,
                            "order": order_number,
                            "order_id": external_order_id,
                            "line_item_id": item.shopify_line_item_id or "",
                            "phase": "orphan_line",
                        },
                    )

        record_event(
            action="pod.shopify.fulfillment_ingested",
            metadata={
                "shop": shop_domain,
                "order": order_number,
                "order_id": external_order_id,
                "topic": topic,
                "queued": queued,
                "updated": updated,
                "cancelled": cancelled,
                "frozen": frozen,
            },
        )
        return {
            "queued": queued,
            "skipped": skipped,
            "updated": updated,
            "cancelled": cancelled,
            "frozen": frozen,
            "order": order_number,
        }
