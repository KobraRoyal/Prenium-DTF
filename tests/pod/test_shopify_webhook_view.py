from __future__ import annotations

import base64
import hashlib
import hmac
from unittest.mock import patch

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.pod.models import PodRipWorkItem, ShopifyStore, ShopifyWebhookReceipt
from apps.pod.tasks import process_shopify_pod_inbox_task, recover_shopify_pod_inbox_task
from django.test import Client
from django.urls import reverse

from tests.pod.test_rip_lots import configure_pod
from tests.pod.test_variant_config import MANAGE, pod_fixture, staff_client

pytestmark = pytest.mark.django_db


def _signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def test_invalid_hmac_is_rejected_before_non_eager_task_enqueue(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = False
    store = ShopifyStore.objects.create(
        name="Webhook store",
        slug="webhook-store",
        shop_domain="webhook-store.myshopify.com",
        webhook_secret="test-webhook-secret",
    )

    with patch("apps.pod.views_webhooks.process_shopify_pod_inbox_task.delay") as delay:
        response = Client().post(
            reverse("pod:shopify-fulfillment-webhook"),
            data=b'{"id": 42}',
            content_type="application/json",
            HTTP_X_SHOPIFY_HMAC_SHA256="invalid",
            HTTP_X_SHOPIFY_SHOP_DOMAIN=store.shop_domain,
        )

    assert response.status_code == 401
    delay.assert_not_called()
    assert AuditLogEntry.objects.filter(
        action="pod.shopify.webhook_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


def test_valid_hmac_is_enqueued_in_non_eager_mode(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = False
    store = ShopifyStore.objects.create(
        name="Webhook store",
        slug="webhook-store-valid",
        shop_domain="webhook-valid.myshopify.com",
        webhook_secret="test-webhook-secret",
    )
    raw = b'{"id": 42}'

    with patch("apps.pod.views_webhooks.process_shopify_pod_inbox_task.delay") as delay:
        response = Client().post(
            reverse("pod:shopify-fulfillment-webhook"),
            data=raw,
            content_type="application/json",
            HTTP_X_SHOPIFY_HMAC_SHA256=_signature("test-webhook-secret", raw),
            HTTP_X_SHOPIFY_SHOP_DOMAIN=store.shop_domain,
            HTTP_X_SHOPIFY_WEBHOOK_ID="evt-valid",
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "accepted": True, "duplicate": False}
    receipt = ShopifyWebhookReceipt.objects.get(webhook_id="evt-valid")
    assert receipt.status == ShopifyWebhookReceipt.Status.PENDING
    assert bytes(receipt.raw_body) == raw
    delay.assert_called_once_with(str(receipt.public_id))


def test_missing_delivery_id_is_rejected_before_enqueue(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = False
    store = ShopifyStore.objects.create(
        name="Webhook no ID",
        slug="webhook-no-id",
        shop_domain="webhook-no-id.myshopify.com",
        webhook_secret="test-webhook-secret",
    )
    raw = b'{"id": 43}'
    with patch("apps.pod.views_webhooks.process_shopify_pod_inbox_task.delay") as delay:
        response = Client().post(
            reverse("pod:shopify-fulfillment-webhook"),
            data=raw,
            content_type="application/json",
            HTTP_X_SHOPIFY_HMAC_SHA256=_signature("test-webhook-secret", raw),
            HTTP_X_SHOPIFY_SHOP_DOMAIN=store.shop_domain,
        )
    assert response.status_code == 400
    delay.assert_not_called()
    assert AuditLogEntry.objects.filter(
        action="pod.shopify.webhook_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


def test_non_eager_unknown_variant_is_durable_and_replays_after_catalog_import(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = False
    actor, _client = staff_client(email="hook-replay@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    store = variant.product.store
    store.webhook_secret = "hook-replay-secret"
    store.save(update_fields=["webhook_secret"])
    raw = b'{"name":"#REPLAY","line_items":[{"variant_id":"new-import-id","quantity":1}]}'
    with patch("apps.pod.views_webhooks.process_shopify_pod_inbox_task.delay"):
        response = Client().post(
            reverse("pod:shopify-fulfillment-webhook"),
            data=raw,
            content_type="application/json",
            HTTP_X_SHOPIFY_HMAC_SHA256=_signature("hook-replay-secret", raw),
            HTTP_X_SHOPIFY_SHOP_DOMAIN=store.shop_domain,
            HTTP_X_SHOPIFY_WEBHOOK_ID="evt-replay",
        )
    assert response.status_code == 200
    receipt = ShopifyWebhookReceipt.objects.get(webhook_id="evt-replay")
    assert receipt.status == ShopifyWebhookReceipt.Status.PENDING

    failed = process_shopify_pod_inbox_task(str(receipt.public_id))
    assert failed["ok"] is False
    receipt.refresh_from_db()
    assert receipt.status == ShopifyWebhookReceipt.Status.FAILED
    assert not PodRipWorkItem.objects.filter(shopify_order_number="#REPLAY").exists()

    variant.external_id = "new-import-id"
    variant.save(update_fields=["external_id", "updated_at"])
    recovered = process_shopify_pod_inbox_task(str(receipt.public_id))
    assert recovered["ok"] is True
    assert recovered["queued"] == 1
    receipt.refresh_from_db()
    assert receipt.status == ShopifyWebhookReceipt.Status.PROCESSED
    assert bytes(receipt.raw_body) == b""
    assert process_shopify_pod_inbox_task(str(receipt.public_id))["duplicate"] is True
    assert PodRipWorkItem.objects.filter(shopify_order_number="#REPLAY").count() == 1


def test_broker_failure_keeps_pending_receipt_for_periodic_recovery(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = False
    store = ShopifyStore.objects.create(
        name="Recovery store",
        slug="recovery-store",
        shop_domain="recovery-store.myshopify.com",
        webhook_secret="recovery-secret",
    )
    raw = b'{"name":"#RECOVER","line_items":[]}'
    with patch(
        "apps.pod.views_webhooks.process_shopify_pod_inbox_task.delay",
        side_effect=RuntimeError("broker unavailable"),
    ):
        response = Client().post(
            reverse("pod:shopify-fulfillment-webhook"),
            data=raw,
            content_type="application/json",
            HTTP_X_SHOPIFY_HMAC_SHA256=_signature("recovery-secret", raw),
            HTTP_X_SHOPIFY_SHOP_DOMAIN=store.shop_domain,
            HTTP_X_SHOPIFY_WEBHOOK_ID="evt-recover",
        )
    assert response.status_code == 200
    receipt = ShopifyWebhookReceipt.objects.get(webhook_id="evt-recover")
    assert receipt.status == ShopifyWebhookReceipt.Status.PENDING
    with patch("apps.pod.tasks.process_shopify_pod_inbox_task.delay") as delay:
        result = recover_shopify_pod_inbox_task()
    assert result["dispatched"] == 1
    delay.assert_called_once_with(str(receipt.public_id))
