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
