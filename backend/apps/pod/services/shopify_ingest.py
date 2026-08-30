from __future__ import annotations

import base64
import hashlib
import hmac
import json

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.auditlog.services import record_event
from apps.pod.models import PodRipWorkItem, ShopifyStore, ShopifyVariant
from apps.pod.services.rip_lots import PodRipLotService
from apps.pod.services.variant_config import CONFIG_STATUS_POD, VariantConfigService


class ShopifyFulfillmentIngestService:
    def ingest(
        self,
        *,
        raw_body: bytes,
        hmac_header: str,
        shop_domain: str,
    ) -> dict:
        store = ShopifyStore.objects.filter(shop_domain=shop_domain, is_active=True).first()
        if store is None:
            raise ValidationError("Boutique inconnue.")
        secret = (store.webhook_secret or "").encode()
        if not secret:
            raise ValidationError("Secret webhook boutique manquant.")
        digest = hmac.new(secret, raw_body, hashlib.sha256).digest()
        expected = base64.b64encode(digest).decode()
        provided = (hmac_header or "").removeprefix("sha256=").strip()
        if not provided or not hmac.compare_digest(expected, provided):
            record_event(
                action="pod.shopify.webhook_rejected",
                status="failure",
                message="HMAC Shopify invalide.",
                metadata={"shop": shop_domain},
            )
            raise ValidationError("HMAC Shopify invalide.")
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise ValidationError("Payload JSON invalide.") from exc
        order_number = str(
            payload.get("name") or payload.get("order_number") or payload.get("id") or ""
        ).strip()
        if not order_number:
            raise ValidationError("Numéro de commande Shopify manquant.")
        line_items = payload.get("line_items") or []
        queued = 0
        skipped = 0
        rip = PodRipLotService()
        config_service = VariantConfigService()
        with transaction.atomic():
            for line in line_items:
                sku = str(line.get("sku") or "").strip()
                qty = int(line.get("quantity") or 1)
                variant = (
                    ShopifyVariant.objects.select_related("ids_config", "product__store")
                    .filter(product__store=store, sku__iexact=sku)
                    .first()
                )
                if variant is None:
                    skipped += 1
                    continue
                already_queued = PodRipWorkItem.objects.filter(
                    store=store,
                    variant=variant,
                    shopify_order_number=order_number,
                    status=PodRipWorkItem.Status.QUEUED,
                ).exists()
                if already_queued:
                    skipped += 1
                    continue
                config = getattr(variant, "ids_config", None)
                status = (
                    config_service.configuration_status(config) if config else "unmanaged"
                )
                if status != CONFIG_STATUS_POD:
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
        record_event(
            action="pod.shopify.fulfillment_ingested",
            metadata={"shop": shop_domain, "order": order_number, "queued": queued},
        )
        return {"queued": queued, "skipped": skipped, "order": order_number}
