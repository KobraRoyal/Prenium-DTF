from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest
from apps.customers.models import Customer
from apps.inventory.models import WarehouseZone
from apps.inventory.services import StockOpsService, WarehouseLayoutService
from apps.pod.models import (
    PodRipWorkItem,
    ShopifyProduct,
    ShopifyStore,
    ShopifyVariant,
    ShopifyWebhookReceipt,
)
from apps.pod.services.shopify_ingest import ShopifyFulfillmentIngestService
from django.core.exceptions import ValidationError
from django.urls import reverse

from tests.pod.test_rip_lots import configure_pod
from tests.pod.test_variant_config import MANAGE, pod_fixture, staff_client

pytestmark = pytest.mark.django_db


def _sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _ingest(*, store, secret: str, payload: dict, webhook_id: str, topic: str) -> dict:
    raw = json.dumps(payload).encode()
    return ShopifyFulfillmentIngestService().ingest(
        raw_body=raw,
        hmac_header=_sign(secret, raw),
        shop_domain=store.shop_domain,
        webhook_id=webhook_id,
        topic=topic,
    )


def _stock_picking_blank(*, actor, blank_variant, quantity: int) -> None:
    warehouse = WarehouseLayoutService()
    warehouse.ensure_default_layout(actor=actor)
    zone = WarehouseZone.objects.get(kind=WarehouseZone.Kind.BLANKS, warehouse__code="atl-01")
    location = warehouse.create_location(
        actor=actor,
        source="test",
        data={"zone_public_id": str(zone.public_id), "code": "A-01-01-A", "label": "A-01-01-A"},
    )
    warehouse.set_blank_default_location(
        actor=actor,
        source="test",
        variant_public_id=blank_variant.public_id,
        location_public_id=location.public_id,
    )
    StockOpsService().receive_blank(
        actor=actor,
        source="test",
        blank_variant_public_id=blank_variant.public_id,
        location_public_id=location.public_id,
        quantity=quantity,
    )


def test_shopify_webhook_queues_pod_sku_and_rejects_bad_hmac():
    actor, _client = staff_client(email="staff-hook@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    store = variant.product.store
    store.webhook_secret = "hook-secret"
    store.save(update_fields=["webhook_secret"])
    payload = {
        "name": "#1042",
        "line_items": [{"sku": variant.sku, "quantity": 2}],
    }
    raw = json.dumps(payload).encode()
    url = reverse("pod:shopify-fulfillment-webhook")
    from django.test import Client

    anon = Client()
    bad = anon.post(
        url,
        data=raw,
        content_type="application/json",
        HTTP_X_SHOPIFY_HMAC_SHA256="nope",
        HTTP_X_SHOPIFY_SHOP_DOMAIN=store.shop_domain,
    )
    assert bad.status_code == 401
    ok = anon.post(
        url,
        data=raw,
        content_type="application/json",
        HTTP_X_SHOPIFY_HMAC_SHA256=_sign("hook-secret", raw),
        HTTP_X_SHOPIFY_SHOP_DOMAIN=store.shop_domain,
        HTTP_X_SHOPIFY_WEBHOOK_ID="evt-1042",
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["queued"] == 1
    item = PodRipWorkItem.objects.get(shopify_order_number="#1042")
    assert item.quantity == 2
    again = anon.post(
        url,
        data=raw,
        content_type="application/json",
        HTTP_X_SHOPIFY_HMAC_SHA256=_sign("hook-secret", raw),
        HTTP_X_SHOPIFY_SHOP_DOMAIN=store.shop_domain,
        HTTP_X_SHOPIFY_WEBHOOK_ID="evt-1042",
    )
    assert again.json().get("duplicate") is True or again.json()["queued"] == 0
    assert PodRipWorkItem.objects.filter(shopify_order_number="#1042").count() == 1


def test_identified_lines_of_same_variant_are_distinct_and_update_by_line_id():
    actor, _client = staff_client(email="staff-hook-lines@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    store = variant.product.store
    store.webhook_secret = "hook-secret"
    store.save(update_fields=["webhook_secret"])
    payload = {
        "id": 9001,
        "name": "#DUP-LINES",
        "line_items": [
            {"id": 1, "variant_id": variant.external_id, "quantity": 1},
            {"id": 2, "variant_id": variant.external_id, "quantity": 2},
        ],
    }
    response = _ingest(
        store=store,
        secret="hook-secret",
        payload=payload,
        webhook_id="evt-dup-lines",
        topic="orders/create",
    )
    assert response["queued"] == 2
    items = list(
        PodRipWorkItem.objects.filter(shopify_order_number="#DUP-LINES").order_by(
            "shopify_line_item_id"
        )
    )
    assert [item.shopify_line_item_id for item in items] == ["1", "2"]
    assert [item.quantity for item in items] == [1, 2]
    assert items[0].shopify_order_id == items[1].shopify_order_id
    assert items[0].shopify_order.external_order_id == "9001"
    assert items[0].shopify_order.customer_id == store.customer_id

    replay = _ingest(
        store=store,
        secret="hook-secret",
        payload=payload,
        webhook_id="evt-dup-lines-replay",
        topic="orders/updated",
    )
    assert replay["queued"] == 0
    assert PodRipWorkItem.objects.filter(shopify_order_number="#DUP-LINES").count() == 2

    updated = _ingest(
        store=store,
        secret="hook-secret",
        payload={
            "id": 9001,
            "name": "#DUP-LINES",
            "line_items": [
                {"id": 1, "variant_id": variant.external_id, "quantity": 4},
            ],
        },
        webhook_id="evt-dup-lines-update",
        topic="orders/updated",
    )
    assert updated["updated"] == 1
    assert updated["cancelled"] == 1
    items[0].refresh_from_db()
    items[1].refresh_from_db()
    assert items[0].quantity == 4
    assert items[0].status == PodRipWorkItem.Status.QUEUED
    assert items[1].status == PodRipWorkItem.Status.CANCELLED


def test_identified_order_isolated_from_legacy_row_and_other_store():
    actor, _client = staff_client(email="staff-hook-tenant@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, first_variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, first_variant)
    first_store = first_variant.product.store
    first_store.webhook_secret = "first-secret"
    first_store.save(update_fields=["webhook_secret"])
    legacy = PodRipWorkItem.objects.create(
        store=first_store,
        variant=first_variant,
        shopify_order_number="#SHARED",
    )

    second_store = ShopifyStore.objects.create(
        customer=Customer.objects.create(name="Second tenant"),
        slug="identity-second-store",
        name="Identity second store",
        shop_domain="identity-second-store.myshopify.com",
        webhook_secret="second-secret",
    )
    second_product = ShopifyProduct.objects.create(
        store=second_store,
        external_id="second-product",
        title="Second product",
    )
    second_variant = ShopifyVariant.objects.create(
        product=second_product,
        external_id="second-variant",
        title="Second variant",
        sku="SECOND-IDENTITY-SKU",
    )
    configure_pod(actor, dtf, blank_variant, second_variant)

    first_payload = {
        "id": "shared-order-id",
        "name": "#SHARED",
        "line_items": [
            {"id": "shared-line-id", "variant_id": first_variant.external_id, "quantity": 1}
        ],
    }
    second_payload = {
        "id": "shared-order-id",
        "name": "#SHARED",
        "line_items": [
            {"id": "shared-line-id", "variant_id": second_variant.external_id, "quantity": 2}
        ],
    }
    assert (
        _ingest(
            store=first_store,
            secret="first-secret",
            payload=first_payload,
            webhook_id="evt-identity-first",
            topic="orders/create",
        )["queued"]
        == 1
    )
    assert (
        _ingest(
            store=second_store,
            secret="second-secret",
            payload=second_payload,
            webhook_id="evt-identity-second",
            topic="orders/create",
        )["queued"]
        == 1
    )

    first_identified = PodRipWorkItem.objects.get(
        store=first_store,
        shopify_line_item_id="shared-line-id",
    )
    second_identified = PodRipWorkItem.objects.get(
        store=second_store,
        shopify_line_item_id="shared-line-id",
    )
    assert first_identified.shopify_order.customer_id == first_store.customer_id
    assert second_identified.shopify_order.customer_id == second_store.customer_id
    assert first_identified.shopify_order_id != second_identified.shopify_order_id

    cancelled = _ingest(
        store=first_store,
        secret="first-secret",
        payload={"id": "shared-order-id", "name": "#SHARED"},
        webhook_id="evt-identity-first-cancel",
        topic="orders/cancelled",
    )
    assert cancelled["cancelled"] == 1
    first_identified.refresh_from_db()
    second_identified.refresh_from_db()
    legacy.refresh_from_db()
    assert first_identified.status == PodRipWorkItem.Status.CANCELLED
    assert second_identified.status == PodRipWorkItem.Status.QUEUED
    assert legacy.status == PodRipWorkItem.Status.QUEUED


def test_legacy_duplicate_variant_lines_still_fail_closed():
    actor, _client = staff_client(email="staff-hook-legacy-lines@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    store = variant.product.store
    store.webhook_secret = "legacy-secret"
    store.save(update_fields=["webhook_secret"])
    raw = json.dumps(
        {
            "name": "#LEGACY-DUP",
            "line_items": [
                {"variant_id": variant.external_id, "quantity": 1},
                {"variant_id": variant.external_id, "quantity": 2},
            ],
        }
    ).encode()
    with pytest.raises(ValidationError, match="ambiguë"):
        ShopifyFulfillmentIngestService().ingest(
            raw_body=raw,
            hmac_header=_sign("legacy-secret", raw),
            shop_domain=store.shop_domain,
            webhook_id="evt-legacy-dup",
            topic="orders/create",
        )
    assert not PodRipWorkItem.objects.filter(shopify_order_number="#LEGACY-DUP").exists()
    assert not ShopifyWebhookReceipt.objects.filter(webhook_id="evt-legacy-dup").exists()


def test_replay_create_as_cancel_with_same_delivery_id_cannot_cancel_order():
    actor, _client = staff_client(email="staff-hook-topic@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    store = variant.product.store
    store.webhook_secret = "topic-secret"
    store.save(update_fields=["webhook_secret"])
    payload = {
        "name": "#TOPIC-REPLAY",
        "line_items": [{"variant_id": variant.external_id, "quantity": 1}],
    }
    created = _post_webhook(
        store=store,
        secret="topic-secret",
        payload=payload,
        webhook_id="evt-topic-replay",
        topic="orders/create",
    )
    assert created.json()["queued"] == 1
    replay = _post_webhook(
        store=store,
        secret="topic-secret",
        payload=payload,
        webhook_id="evt-topic-replay",
        topic="orders/cancelled",
    )
    assert replay.json()["duplicate"] is True
    assert PodRipWorkItem.objects.get(shopify_order_number="#TOPIC-REPLAY").status == (
        PodRipWorkItem.Status.QUEUED
    )


def test_failed_webhook_does_not_consume_receipt_and_can_be_retried(monkeypatch):
    actor, _client = staff_client(email="staff-hook-retry@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    store = variant.product.store
    store.webhook_secret = "hook-secret"
    store.save(update_fields=["webhook_secret"])
    raw = json.dumps(
        {"name": "#RETRY-1", "line_items": [{"sku": variant.sku, "quantity": 1}]}
    ).encode()
    kwargs = {
        "raw_body": raw,
        "hmac_header": _sign("hook-secret", raw),
        "shop_domain": store.shop_domain,
        "webhook_id": "evt-retry-1",
    }
    with monkeypatch.context() as patch:

        def fail_once(self, **_kwargs):
            raise ValidationError("Échec temporaire.")

        patch.setattr(ShopifyFulfillmentIngestService, "_sync_order_lines", fail_once)
        with pytest.raises(ValidationError):
            ShopifyFulfillmentIngestService().ingest(**kwargs)

    assert not ShopifyWebhookReceipt.objects.filter(webhook_id="evt-retry-1").exists()
    assert ShopifyFulfillmentIngestService().ingest(**kwargs)["queued"] == 1
    assert ShopifyWebhookReceipt.objects.filter(webhook_id="evt-retry-1").exists()


def test_invalid_update_does_not_consume_receipt_or_cancel_existing_lines():
    actor, _client = staff_client(email="staff-hook-shape@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    store = variant.product.store
    store.webhook_secret = "hook-secret"
    store.save(update_fields=["webhook_secret"])
    created = _post_webhook(
        store=store,
        secret="hook-secret",
        payload={"name": "#SHAPE-1", "line_items": [{"sku": variant.sku, "quantity": 1}]},
        webhook_id="evt-shape-create",
        topic="orders/create",
    )
    assert created.status_code == 200
    invalid = _post_webhook(
        store=store,
        secret="hook-secret",
        payload={"name": "#SHAPE-1"},
        webhook_id="evt-shape-update",
        topic="orders/updated",
    )
    assert invalid.status_code == 400
    assert not ShopifyWebhookReceipt.objects.filter(webhook_id="evt-shape-update").exists()
    item = PodRipWorkItem.objects.get(shopify_order_number="#SHAPE-1")
    assert item.status == PodRipWorkItem.Status.QUEUED

    empty = _post_webhook(
        store=store,
        secret="hook-secret",
        payload={"name": "#SHAPE-1", "line_items": []},
        webhook_id="evt-shape-update",
        topic="orders/updated",
    )
    assert empty.status_code == 200
    assert empty.json()["cancelled"] == 1
    item.refresh_from_db()
    assert item.status == PodRipWorkItem.Status.CANCELLED


def test_variant_id_disambiguates_duplicate_sku_and_ambiguous_fallback_is_quarantined():
    actor, _client = staff_client(email="staff-hook-sku@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    store = variant.product.store
    store.webhook_secret = "hook-secret"
    store.save(update_fields=["webhook_secret"])
    ShopifyVariant.objects.create(
        product=variant.product,
        external_id="another-shopify-variant",
        title="Autre variante",
        sku=variant.sku,
    )

    ambiguous = _post_webhook(
        store=store,
        secret="hook-secret",
        payload={"name": "#SKU-1", "line_items": [{"sku": variant.sku, "quantity": 1}]},
        webhook_id="evt-sku-ambiguous",
        topic="orders/create",
    )
    assert ambiguous.status_code == 400
    assert not ShopifyWebhookReceipt.objects.filter(webhook_id="evt-sku-ambiguous").exists()
    assert not PodRipWorkItem.objects.filter(shopify_order_number="#SKU-1").exists()

    resolved = _post_webhook(
        store=store,
        secret="hook-secret",
        payload={
            "name": "#SKU-2",
            "line_items": [{"variant_id": variant.external_id, "sku": variant.sku, "quantity": 2}],
        },
        webhook_id="evt-sku-resolved",
        topic="orders/create",
    )
    assert resolved.status_code == 200
    item = PodRipWorkItem.objects.get(shopify_order_number="#SKU-2")
    assert item.variant_id == variant.pk
    assert item.quantity == 2


def test_unknown_variant_id_never_falls_back_to_matching_sku():
    actor, _client = staff_client(email="staff-hook-id@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    store = variant.product.store
    store.webhook_secret = "hook-secret"
    store.save(update_fields=["webhook_secret"])
    result = _post_webhook(
        store=store,
        secret="hook-secret",
        payload={
            "name": "#BAD-ID",
            "line_items": [{"variant_id": "unknown-id", "sku": variant.sku, "quantity": 1}],
        },
        webhook_id="evt-bad-id",
        topic="orders/create",
    )
    assert result.status_code == 400
    assert not ShopifyWebhookReceipt.objects.filter(webhook_id="evt-bad-id").exists()
    assert not PodRipWorkItem.objects.filter(shopify_order_number="#BAD-ID").exists()


def test_unknown_line_in_update_never_cancels_queued_pod_item_or_consumes_receipt():
    actor, _client = staff_client(email="staff-hook-unknown-update@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    store = variant.product.store
    store.webhook_secret = "hook-secret"
    store.save(update_fields=["webhook_secret"])
    created = _post_webhook(
        store=store,
        secret="hook-secret",
        payload={"name": "#UNKNOWN-UP", "line_items": [{"sku": variant.sku, "quantity": 1}]},
        webhook_id="evt-unknown-created",
        topic="orders/create",
    )
    assert created.status_code == 200

    update = _post_webhook(
        store=store,
        secret="hook-secret",
        payload={
            "name": "#UNKNOWN-UP",
            "line_items": [{"variant_id": "not-imported", "sku": variant.sku, "quantity": 1}],
        },
        webhook_id="evt-unknown-updated",
        topic="orders/updated",
    )
    assert update.status_code == 400
    assert not ShopifyWebhookReceipt.objects.filter(webhook_id="evt-unknown-updated").exists()
    item = PodRipWorkItem.objects.get(shopify_order_number="#UNKNOWN-UP")
    assert item.status == PodRipWorkItem.Status.QUEUED


def test_receipt_id_is_global_across_shops_and_unsigned_topics():
    actor, _client = staff_client(email="staff-hook-scope@example.com", permissions=MANAGE)
    _dtf, _blank, _blank_variant, variant = pod_fixture(actor=actor)
    first = variant.product.store
    first.webhook_secret = "first-secret"
    first.save(update_fields=["webhook_secret"])
    second = ShopifyStore.objects.create(
        slug="second-store",
        name="Seconde boutique",
        shop_domain="second-store.myshopify.com",
        webhook_secret="second-secret",
    )
    raw = json.dumps({"name": "#SCOPE-1"}).encode()
    service = ShopifyFulfillmentIngestService()
    common = {"raw_body": raw, "webhook_id": "evt-shared", "topic": "orders/cancelled"}

    first_result = service.ingest(
        **common, hmac_header=_sign("first-secret", raw), shop_domain=first.shop_domain
    )
    second_result = service.ingest(
        **common, hmac_header=_sign("second-secret", raw), shop_domain=second.shop_domain
    )
    repeated = service.ingest(
        **common, hmac_header=_sign("first-secret", raw), shop_domain=first.shop_domain
    )
    assert first_result["cancelled"] == 0
    assert second_result["duplicate"] is True
    assert repeated["duplicate"] is True

    updated_raw = json.dumps({"name": "#SCOPE-1", "line_items": []}).encode()
    updated = service.ingest(
        raw_body=updated_raw,
        hmac_header=_sign("first-secret", updated_raw),
        shop_domain=first.shop_domain,
        webhook_id="evt-shared",
        topic="orders/updated",
    )
    assert updated["cancelled"] == 0
    assert updated["duplicate"] is True
    assert ShopifyWebhookReceipt.objects.filter(webhook_id="evt-shared").count() == 1


def test_shared_app_secret_replay_to_another_store_cannot_cancel_its_order(settings):
    actor, _client = staff_client(email="staff-hook-cross-shop@example.com", permissions=MANAGE)
    _dtf, _blank, _blank_variant, variant = pod_fixture(actor=actor)
    first = variant.product.store
    first.webhook_secret = ""
    first.save(update_fields=["webhook_secret"])
    second = ShopifyStore.objects.create(
        slug="replay-target",
        name="Boutique cible",
        shop_domain="replay-target.myshopify.com",
    )
    second_product = ShopifyProduct.objects.create(
        store=second, external_id="target-product", title="Target"
    )
    second_variant = ShopifyVariant.objects.create(
        product=second_product, external_id="target-variant", sku="TARGET-SKU"
    )
    target = PodRipWorkItem.objects.create(
        store=second,
        variant=second_variant,
        shopify_order_number="#CROSS-SHOP",
    )
    settings.SHOPIFY_POD_API_SECRET = "shared-app-secret"
    raw = json.dumps({"name": "#CROSS-SHOP", "line_items": []}).encode()
    service = ShopifyFulfillmentIngestService()
    first_result = service.ingest(
        raw_body=raw,
        hmac_header=_sign("shared-app-secret", raw),
        shop_domain=first.shop_domain,
        webhook_id="evt-cross-shop",
        topic="orders/create",
    )
    assert first_result["queued"] == 0
    replay = service.ingest(
        raw_body=raw,
        hmac_header=_sign("shared-app-secret", raw),
        shop_domain=second.shop_domain,
        webhook_id="evt-cross-shop",
        topic="orders/cancelled",
    )
    assert replay["duplicate"] is True
    target.refresh_from_db()
    assert target.status == PodRipWorkItem.Status.QUEUED


def test_service_rejects_delivery_without_id():
    actor, _client = staff_client(email="staff-hook-no-id@example.com", permissions=MANAGE)
    _dtf, _blank, _blank_variant, variant = pod_fixture(actor=actor)
    store = variant.product.store
    store.webhook_secret = "hook-secret"
    store.save(update_fields=["webhook_secret"])
    raw = json.dumps({"name": "#NO-ID", "line_items": []}).encode()
    with pytest.raises(ValidationError, match="livraison"):
        ShopifyFulfillmentIngestService().ingest(
            raw_body=raw,
            hmac_header=_sign("hook-secret", raw),
            shop_domain=store.shop_domain,
            webhook_id="",
        )
    assert not ShopifyWebhookReceipt.objects.exists()


def test_shopify_webhook_accepts_app_client_secret(settings):
    actor, _client = staff_client(email="staff-hook-app@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    store = variant.product.store
    store.webhook_secret = ""
    store.save(update_fields=["webhook_secret"])
    settings.SHOPIFY_POD_API_SECRET = "app-client-secret"
    payload = {"name": "#1043", "line_items": [{"sku": variant.sku, "quantity": 1}]}
    raw = json.dumps(payload).encode()
    from django.test import Client

    ok = Client().post(
        reverse("pod:shopify-fulfillment-webhook"),
        data=raw,
        content_type="application/json",
        HTTP_X_SHOPIFY_HMAC_SHA256=_sign("app-client-secret", raw),
        HTTP_X_SHOPIFY_SHOP_DOMAIN=store.shop_domain,
        HTTP_X_SHOPIFY_WEBHOOK_ID="evt-1043",
    )
    assert ok.status_code == 200
    assert ok.json()["queued"] == 1


def _post_webhook(*, store, secret: str, payload: dict, webhook_id: str, topic: str):
    from django.test import Client

    raw = json.dumps(payload).encode()
    return Client().post(
        reverse("pod:shopify-fulfillment-webhook"),
        data=raw,
        content_type="application/json",
        HTTP_X_SHOPIFY_HMAC_SHA256=_sign(secret, raw),
        HTTP_X_SHOPIFY_SHOP_DOMAIN=store.shop_domain,
        HTTP_X_SHOPIFY_WEBHOOK_ID=webhook_id,
        HTTP_X_SHOPIFY_TOPIC=topic,
    )


def test_shopify_webhook_cancel_queued_order():
    actor, _client = staff_client(email="staff-hook-cancel@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    store = variant.product.store
    store.webhook_secret = "hook-secret"
    store.save(update_fields=["webhook_secret"])
    create = _post_webhook(
        store=store,
        secret="hook-secret",
        payload={"name": "#C-1", "line_items": [{"sku": variant.sku, "quantity": 1}]},
        webhook_id="evt-c1-create",
        topic="orders/create",
    )
    assert create.status_code == 200
    item = PodRipWorkItem.objects.get(shopify_order_number="#C-1")
    assert item.status == PodRipWorkItem.Status.QUEUED
    cancel = _post_webhook(
        store=store,
        secret="hook-secret",
        payload={"name": "#C-1", "line_items": []},
        webhook_id="evt-c1-cancel",
        topic="orders/cancelled",
    )
    assert cancel.status_code == 200
    assert cancel.json()["cancelled"] == 1
    item.refresh_from_db()
    assert item.status == PodRipWorkItem.Status.CANCELLED


def test_shopify_webhook_updated_qty_respects_pick_floor(tmp_path, settings):
    from apps.pod.services.pick_sessions import PodPickSessionService
    from apps.pod.services.rip_lots import PodRipLotService

    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="staff-hook-qty@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    _stock_picking_blank(actor=actor, blank_variant=blank_variant, quantity=3)
    store = variant.product.store
    store.webhook_secret = "hook-secret"
    store.save(update_fields=["webhook_secret"])
    _post_webhook(
        store=store,
        secret="hook-secret",
        payload={"name": "#Q-1", "line_items": [{"sku": variant.sku, "quantity": 3}]},
        webhook_id="evt-q1-create",
        topic="orders/create",
    )
    item = PodRipWorkItem.objects.get(shopify_order_number="#Q-1")
    PodPickSessionService().open_session(
        actor=actor,
        source="test",
        work_item_public_ids=[str(item.public_id)],
    )
    assert item.pick_lines.count() == 3
    down = _post_webhook(
        store=store,
        secret="hook-secret",
        payload={"name": "#Q-1", "line_items": [{"sku": variant.sku, "quantity": 1}]},
        webhook_id="evt-q1-down",
        topic="orders/updated",
    )
    assert down.status_code == 200
    item.refresh_from_db()
    assert item.quantity == 3
    up = _post_webhook(
        store=store,
        secret="hook-secret",
        payload={"name": "#Q-1", "line_items": [{"sku": variant.sku, "quantity": 5}]},
        webhook_id="evt-q1-up",
        topic="orders/updated",
    )
    assert up.status_code == 200
    assert up.json()["updated"] == 1
    item.refresh_from_db()
    assert item.quantity == 5
    # Sanity: rip service still lists it queued
    assert PodRipLotService().list_queue(actor=actor).filter(pk=item.pk).exists()


def test_shopify_webhook_cancel_after_lot_flags_units(tmp_path, settings):
    from apps.pod.models import PodUnit
    from apps.pod.services.pick_sessions import PodPickSessionService
    from apps.pod.services.rip_lots import PodRipLotService

    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="staff-hook-freeze@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    _stock_picking_blank(actor=actor, blank_variant=blank_variant, quantity=1)
    store = variant.product.store
    store.webhook_secret = "hook-secret"
    store.save(update_fields=["webhook_secret"])
    _post_webhook(
        store=store,
        secret="hook-secret",
        payload={"name": "#F-1", "line_items": [{"sku": variant.sku, "quantity": 1}]},
        webhook_id="evt-f1-create",
        topic="orders/create",
    )
    item = PodRipWorkItem.objects.get(shopify_order_number="#F-1")
    picking = PodPickSessionService()
    session = picking.open_session(
        actor=actor, source="test", work_item_public_ids=[str(item.public_id)]
    )
    picking.confirm_pick(
        actor=actor,
        source="test",
        scan_identifier=session.lines.get().scan_identifier,
        scanned_bin_code="A-01-01-A",
    )
    PodRipLotService().prepare_dtf_lot(
        actor=actor,
        source="test",
        work_item_public_ids=[str(item.public_id)],
    )
    item.refresh_from_db()
    assert item.status == PodRipWorkItem.Status.INCLUDED
    unit = PodUnit.objects.get(work_item=item)
    assert unit.status == PodUnit.Status.WAITING_PRESS
    cancel = _post_webhook(
        store=store,
        secret="hook-secret",
        payload={"name": "#F-1"},
        webhook_id="evt-f1-cancel",
        topic="orders/cancelled",
    )
    assert cancel.status_code == 200
    assert cancel.json().get("frozen") == 1
    item.refresh_from_db()
    unit.refresh_from_db()
    assert item.status == PodRipWorkItem.Status.INCLUDED
    assert "annulée" in item.skip_reason.lower()
    assert unit.status == PodUnit.Status.ISSUE
    assert PodUnit.objects.filter(work_item=item).count() == 1


def test_shopify_cancel_voids_pick_session_pdf():
    from apps.pod.models import PodPickSessionLine
    from apps.pod.services.pick_sessions import PodPickSessionService

    actor, client = staff_client(
        email="staff-hook-void@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    _stock_picking_blank(actor=actor, blank_variant=blank_variant, quantity=1)
    store = variant.product.store
    store.webhook_secret = "hook-secret"
    store.save(update_fields=["webhook_secret"])
    _post_webhook(
        store=store,
        secret="hook-secret",
        payload={"name": "#V-1", "line_items": [{"sku": variant.sku, "quantity": 1}]},
        webhook_id="evt-v1-create",
        topic="orders/create",
    )
    item = PodRipWorkItem.objects.get(shopify_order_number="#V-1")
    session = PodPickSessionService().open_session(
        actor=actor,
        source="test",
        work_item_public_ids=[str(item.public_id)],
    )
    cancel = _post_webhook(
        store=store,
        secret="hook-secret",
        payload={"name": "#V-1"},
        webhook_id="evt-v1-cancel",
        topic="orders/cancelled",
    )
    assert cancel.status_code == 200
    assert PodPickSessionLine.objects.filter(session=session, voided_at__isnull=False).count() == 1
    pdf = client.get(
        reverse(
            "portal:staff-pod-pick-session-pdf",
            kwargs={"session_public_id": session.public_id, "document_kind": "picking"},
        )
    )
    assert pdf.status_code == 302
    assert pdf.url.endswith(reverse("portal:staff-pod-hub"))
