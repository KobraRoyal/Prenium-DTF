from __future__ import annotations

import base64
import hashlib
import hmac
import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.pod.models import (
    PodRipWorkItem,
    PodUnit,
    ShopifyStore,
    ShopifyVariant,
    ShopifyWebhookReceipt,
)
from apps.pod.services.rip_lots import PodRipLotService
from apps.pod.services.shopify_connect import hmac_secrets_for_store
from apps.pod.services.variant_config import CONFIG_STATUS_POD, VariantConfigService

SUPPORTED_TOPICS = frozenset(
    {
        "orders/create",
        "orders/updated",
        "orders/cancelled",
    }
)


class ShopifyFulfillmentIngestService:
    def ingest(
        self,
        *,
        raw_body: bytes,
        hmac_header: str,
        shop_domain: str,
        webhook_id: str = "",
        topic: str = "orders/create",
    ) -> dict:
        store = ShopifyStore.objects.filter(shop_domain=shop_domain, is_active=True).first()
        if store is None:
            raise ValidationError("Boutique inconnue.")
        provided = (hmac_header or "").removeprefix("sha256=").strip()
        secrets = hmac_secrets_for_store(store)
        if not secrets or not provided:
            raise ValidationError("Secret webhook boutique manquant.")
        matched = False
        for secret in secrets:
            expected = base64.b64encode(
                hmac.new(secret, raw_body, hashlib.sha256).digest()
            ).decode()
            if hmac.compare_digest(expected, provided):
                matched = True
                break
        if not matched:
            record_event(
                action="pod.shopify.webhook_rejected",
                status="failure",
                message="HMAC Shopify invalide.",
                metadata={"shop": shop_domain},
            )
            raise ValidationError("HMAC Shopify invalide.")

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
        if event_id:
            _receipt, created = ShopifyWebhookReceipt.objects.get_or_create(
                webhook_id=event_id,
                defaults={"shop_domain": shop_domain, "topic": topic_key},
            )
            if not created:
                return {
                    "queued": 0,
                    "skipped": 0,
                    "updated": 0,
                    "cancelled": 0,
                    "order": "",
                    "duplicate": True,
                }

        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise ValidationError("Payload JSON invalide.") from exc

        order_number = str(
            payload.get("name") or payload.get("order_number") or payload.get("id") or ""
        ).strip()
        if not order_number:
            raise ValidationError("Numéro de commande Shopify manquant.")

        if topic_key == "orders/cancelled":
            result = self._cancel_order(
                store=store, order_number=order_number, shop_domain=shop_domain
            )
            return result

        return self._sync_order_lines(
            store=store,
            order_number=order_number,
            line_items=payload.get("line_items") or [],
            shop_domain=shop_domain,
            topic=topic_key,
        )

    def _cancel_order(self, *, store: ShopifyStore, order_number: str, shop_domain: str) -> dict:
        cancelled = 0
        frozen = 0
        with transaction.atomic():
            items = list(
                PodRipWorkItem.objects.select_for_update()
                .filter(store=store, shopify_order_number=order_number)
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
                        metadata={"shop": shop_domain, "order": order_number, "phase": "queued"},
                    )
                    continue
                # INCLUDED / SKIPPED : ne pas détruire le lot — geler la pose restante.
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
                        status=PodUnit.Status.WAITING_PRESS,
                    ).update(status=PodUnit.Status.ISSUE, updated_at=timezone.now())
                )
                frozen += 1
                record_event(
                    action="pod.shopify.cancel_after_production",
                    target=item,
                    metadata={
                        "shop": shop_domain,
                        "order": order_number,
                        "units_flagged": updated_units,
                        "status": item.status,
                    },
                )
        record_event(
            action="pod.shopify.order_cancelled",
            metadata={
                "shop": shop_domain,
                "order": order_number,
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

        with transaction.atomic():
            for line in line_items:
                sku = str(line.get("sku") or "").strip()
                try:
                    qty = int(line.get("quantity") or 0)
                except (TypeError, ValueError):
                    qty = 0
                variant = (
                    ShopifyVariant.objects.select_related("ids_config", "product__store")
                    .filter(product__store=store, sku__iexact=sku)
                    .first()
                )
                if variant is None:
                    skipped += 1
                    continue
                seen_variant_ids.add(variant.pk)
                config = getattr(variant, "ids_config", None)
                status = config_service.configuration_status(config) if config else "unmanaged"
                if status != CONFIG_STATUS_POD:
                    skipped += 1
                    continue

                existing = (
                    PodRipWorkItem.objects.select_for_update()
                    .filter(
                        store=store,
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
                        quantity=max(qty, 1),
                        trusted_source=True,
                    )
                    queued += 1
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
                            "quantity": applied,
                            "shopify_qty": qty,
                            "pick_floor": printed,
                            "topic": topic,
                        },
                    )
                else:
                    skipped += 1

            # orders/updated : lignes POD absentes du payload → cancel si encore QUEUED
            if topic == "orders/updated" and seen_variant_ids:
                orphans = (
                    PodRipWorkItem.objects.select_for_update()
                    .filter(
                        store=store,
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
                            "phase": "orphan_line",
                        },
                    )

        record_event(
            action="pod.shopify.fulfillment_ingested",
            metadata={
                "shop": shop_domain,
                "order": order_number,
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
