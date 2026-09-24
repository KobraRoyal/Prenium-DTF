from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest
from apps.pod.models import PodRipWorkItem
from django.urls import reverse

from tests.pod.test_rip_lots import configure_pod
from tests.pod.test_variant_config import MANAGE, pod_fixture, staff_client

pytestmark = pytest.mark.django_db


def _sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


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
    actor, _client = staff_client(email="staff-hook-qty@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
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
    from apps.pod.services.rip_lots import PodRipLotService

    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(email="staff-hook-freeze@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
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

    actor, client = staff_client(email="staff-hook-void@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
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
