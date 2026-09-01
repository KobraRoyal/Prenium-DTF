from __future__ import annotations

import hashlib
import hmac

import pytest
from apps.pod.models import IdsVariantConfig, ShopifyStore, ShopifyVariant
from apps.pod.services.shopify_connect import ShopifyConnectService
from apps.pod.services.token_crypto import decrypt_shopify_token, encrypt_shopify_token
from django.urls import reverse

from tests.pod.test_variant_config import MANAGE, VIEW, staff_client

pytestmark = pytest.mark.django_db

SHOP = "demo-pod.myshopify.com"


class FakeHttp:
    def __init__(self):
        self.calls = []

    def request(self, *, method, url, headers=None, payload=None):
        self.calls.append({"method": method, "url": url, "payload": payload})
        if "webhooks.json" in url:
            return {"webhook": {"id": 1}}
        if "products.json" in url:
            return {
                "products": [
                    {
                        "id": 11,
                        "title": "Tee POD",
                        "handle": "tee-pod",
                        "variants": [{"id": 22, "title": "M", "sku": "TEE-BLK-M"}],
                    }
                ]
            }
        return {}


def _oauth_hmac(secret: str, params: dict) -> str:
    message = "&".join(f"{key}={params[key]}" for key in sorted(params))
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def test_encrypt_decrypt_shopify_token_roundtrip():
    token = "shpat_test_token_value"
    blob = encrypt_shopify_token(token)
    assert token not in blob
    assert decrypt_shopify_token(blob) == token


def test_staff_oauth_start_redirects_to_shopify(settings):
    settings.SHOPIFY_POD_API_KEY = "key-test"
    settings.SHOPIFY_POD_API_SECRET = "secret-test"
    settings.PUBLIC_BASE_URL = "https://ids.example.test"
    actor, client = staff_client(email="staff-oauth@example.com", permissions=MANAGE)
    response = client.post(
        reverse("portal:staff-pod-shops"),
        {"intent": "oauth", "shop_domain": SHOP},
    )
    assert response.status_code == 302
    assert response["Location"].startswith(f"https://{SHOP}/admin/oauth/authorize")
    assert "client_id=key-test" in response["Location"]
    assert actor.email


def test_oauth_callback_stores_encrypted_token_and_imports(settings):
    settings.SHOPIFY_POD_API_KEY = "key-test"
    settings.SHOPIFY_POD_API_SECRET = "secret-test"
    http = FakeHttp()

    def exchange(url, data):
        assert "code" in data
        return {"access_token": "shpat_live_abcd1234", "scope": "read_products,read_orders"}

    service = ShopifyConnectService(http_client=http, token_exchange=exchange)
    state = service.signer.sign(SHOP)
    params = {"shop": SHOP, "state": state, "code": "oauth-code", "timestamp": "1"}
    hmac_value = _oauth_hmac("secret-test", params)
    store = service.complete_oauth(query={**params, "hmac": hmac_value})
    assert store.shop_domain == SHOP
    assert store.token_suffix == "1234"
    assert "shpat" not in store.access_token_encrypted
    assert decrypt_shopify_token(store.access_token_encrypted) == "shpat_live_abcd1234"
    assert ShopifyVariant.objects.filter(sku="TEE-BLK-M").exists()
    assert IdsVariantConfig.objects.filter(variant__sku="TEE-BLK-M").exists()
    assert any("webhooks.json" in item["url"] for item in http.calls)


def test_manual_token_and_staff_shops_page(settings):
    settings.SHOPIFY_POD_API_KEY = ""
    settings.SHOPIFY_POD_API_SECRET = ""
    actor, client = staff_client(email="staff-token@example.com", permissions=MANAGE)
    service = ShopifyConnectService(http_client=FakeHttp())
    store = service.save_manual_token(
        actor=actor,
        shop_domain=SHOP,
        token="shpat_manual_zzzz",
        name="Demo",
    )
    assert store.token_suffix == "zzzz"
    page = client.get(reverse("portal:staff-pod-shops"))
    assert page.status_code == 200
    body = page.content.decode()
    assert "zzzz" in body
    assert "shpat_manual" not in body


def test_client_cannot_open_shops():
    from apps.customers.models import Customer, CustomerMembership
    from django.contrib.auth import get_user_model
    from django.test import Client

    user = get_user_model().objects.create_user(email="client-shops@example.com", password="pass")
    CustomerMembership.objects.create(customer=Customer.objects.create(name="C"), user=user)
    client = Client()
    assert client.login(email=user.email, password="pass")
    assert client.get(reverse("portal:staff-pod-shops")).status_code == 403


def test_view_only_staff_cannot_save_token():
    _actor, client = staff_client(email="staff-shops-ro@example.com", permissions=VIEW)
    response = client.post(
        reverse("portal:staff-pod-shops"),
        {"intent": "save_token", "shop_domain": SHOP, "access_token": "shpat_nope"},
    )
    assert response.status_code == 403
    assert not ShopifyStore.objects.filter(shop_domain=SHOP).exists()
