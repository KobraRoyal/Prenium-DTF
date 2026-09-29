from __future__ import annotations

import hashlib
import hmac

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer
from apps.pod.models import IdsVariantConfig, ShopifyStore, ShopifyVariant
from apps.pod.services.shopify_connect import ShopifyConnectService
from apps.pod.services.token_crypto import decrypt_shopify_token, encrypt_shopify_token
from django.urls import reverse

from tests.pod.test_variant_config import MANAGE, VIEW, staff_client

pytestmark = pytest.mark.django_db

SHOP = "demo-pod.myshopify.com"
MANAGE_CUSTOMERS = (*MANAGE, "view_customer")


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
                        "image": {
                            "id": 1001,
                            "src": "https://cdn.shopify.com/s/files/1/tee-product.jpg",
                        },
                        "images": [
                            {
                                "id": 1001,
                                "src": "https://cdn.shopify.com/s/files/1/tee-product.jpg",
                            },
                            {
                                "id": 1002,
                                "src": "https://cdn.shopify.com/s/files/1/tee-black.jpg",
                            },
                        ],
                        "variants": [
                            {
                                "id": 22,
                                "title": "M / Noir",
                                "sku": "TEE-BLK-M",
                                "image_id": 1002,
                            }
                        ],
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
    assert store.webhook_secret == ""
    assert ShopifyVariant.objects.filter(sku="TEE-BLK-M").exists()
    assert IdsVariantConfig.objects.filter(variant__sku="TEE-BLK-M").exists()
    variant = ShopifyVariant.objects.get(sku="TEE-BLK-M")
    assert variant.image_url.endswith("tee-black.jpg")
    assert variant.product.image_url.endswith("tee-product.jpg")
    webhook_calls = [item for item in http.calls if "webhooks.json" in item["url"]]
    assert len(webhook_calls) == 3
    topics = {item["payload"]["webhook"]["topic"] for item in webhook_calls}
    assert topics == {"orders/create", "orders/updated", "orders/cancelled"}


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
    assert "Connecter avec ce token" in body


def test_oauth_page_is_one_click(settings):
    settings.SHOPIFY_POD_API_KEY = "key-test"
    settings.SHOPIFY_POD_API_SECRET = "secret-test"
    _actor, client = staff_client(email="staff-oauth-ui@example.com", permissions=MANAGE)
    body = client.get(reverse("portal:staff-pod-shops")).content.decode()
    assert "Continuer sur Shopify" in body
    assert "SHOPIFY_POD_API_KEY" not in body


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


def test_staff_assigns_store_customer_once_and_cannot_reassign():
    actor, client = staff_client(
        email="staff-store-owner@example.com", permissions=MANAGE_CUSTOMERS
    )
    store = ShopifyStore.objects.create(
        slug="store-owner",
        name="Store owner",
        shop_domain="store-owner.myshopify.com",
    )
    first = Customer.objects.create(name="Client A")
    second = Customer.objects.create(name="Client B")
    url = reverse("portal:staff-pod-shops")
    page = client.get(url)
    assert page.status_code == 200
    assert "Client A" in page.content.decode()
    response = client.post(
        url,
        {
            "intent": "assign_customer",
            "store_public_id": str(store.public_id),
            "customer_public_id": str(first.public_id),
        },
    )
    assert response.status_code == 302
    store.refresh_from_db()
    assert store.customer == first
    assert AuditLogEntry.objects.filter(action="pod.shopify.store_customer_assigned").exists()

    rejected = client.post(
        url,
        {
            "intent": "assign_customer",
            "store_public_id": str(store.public_id),
            "customer_public_id": str(second.public_id),
        },
    )
    assert rejected.status_code == 400
    store.refresh_from_db()
    assert store.customer == first


def test_view_only_staff_cannot_assign_store_customer():
    _actor, client = staff_client(email="staff-store-owner-ro@example.com", permissions=VIEW)
    store = ShopifyStore.objects.create(
        slug="store-owner-ro",
        name="Store owner RO",
        shop_domain="store-owner-ro.myshopify.com",
    )
    customer = Customer.objects.create(name="Client interdit")
    response = client.post(
        reverse("portal:staff-pod-shops"),
        {
            "intent": "assign_customer",
            "store_public_id": str(store.public_id),
            "customer_public_id": str(customer.public_id),
        },
    )
    assert response.status_code == 403
    store.refresh_from_db()
    assert store.customer_id is None


def test_catalog_manager_without_customer_permission_cannot_list_or_assign_customers():
    actor, client = staff_client(email="staff-store-no-customers@example.com", permissions=MANAGE)
    store = ShopifyStore.objects.create(
        slug="store-no-customers",
        name="Store without customer permission",
        shop_domain="store-no-customers.myshopify.com",
    )
    customer = Customer.objects.create(name="Client confidentiel")
    url = reverse("portal:staff-pod-shops")

    page = client.get(url)

    assert page.status_code == 200
    body = page.content.decode()
    assert customer.name not in body
    assert str(customer.public_id) not in body
    assert 'name="customer_public_id"' not in body

    response = client.post(
        url,
        {
            "intent": "assign_customer",
            "store_public_id": str(store.public_id),
            "customer_public_id": str(customer.public_id),
        },
    )

    assert response.status_code == 403
    store.refresh_from_db()
    assert store.customer_id is None
    rejection = AuditLogEntry.objects.get(
        action="pod.shopify.permission_rejected",
        actor=actor,
        status=AuditLogEntry.Status.FAILURE,
    )
    assert rejection.metadata == {
        "source": "pod.shopify.store_customer",
        "permission": "customers.view_customer",
    }
