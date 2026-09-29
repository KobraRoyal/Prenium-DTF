from __future__ import annotations

import hashlib
import hmac
import re
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.signing import BadSignature, TimestampSigner
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.text import slugify

from apps.auditlog.services import record_event
from apps.customers.models import Customer
from apps.pod.models import IdsVariantConfig, ShopifyProduct, ShopifyStore, ShopifyVariant
from apps.pod.services.shopify_http import ShopifyHttpClient, shopify_admin_url, shopify_form_post
from apps.pod.services.token_crypto import (
    decrypt_shopify_token,
    encrypt_shopify_token,
    token_suffix,
)
from apps.pod.services.validation import require_staff_perm

SHOP_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*\.myshopify\.com$")


def normalize_shop_domain(value: str) -> str:
    shop = (value or "").strip().lower()
    shop = shop.replace("https://", "").replace("http://", "").split("/")[0]
    if shop and not shop.endswith(".myshopify.com"):
        shop = f"{shop}.myshopify.com"
    if not SHOP_RE.match(shop):
        raise ValidationError("Domaine boutique invalide (ex. ma-boutique.myshopify.com).")
    return shop


def hmac_secrets_for_store(store: ShopifyStore) -> list[bytes]:
    secrets: list[bytes] = []
    seen: set[bytes] = set()
    for value in (store.webhook_secret, getattr(settings, "SHOPIFY_POD_API_SECRET", "")):
        raw = (value or "").strip().encode()
        if raw and raw not in seen:
            seen.add(raw)
            secrets.append(raw)
    return secrets


class ShopifyConnectService:
    view_permission = "pod.access_pod_atelier"
    manage_permission = "pod.manage_pod_catalog"
    customer_view_permission = "customers.view_customer"
    signer = TimestampSigner(salt="pod.shopify.oauth")

    def __init__(self, http_client: ShopifyHttpClient | None = None, token_exchange=None):
        self.http = http_client or ShopifyHttpClient()
        self.token_exchange = token_exchange or shopify_form_post

    def list_stores(self, *, actor):
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.shopify",
            action="pod.shopify.permission_rejected",
        )
        return ShopifyStore.objects.select_related("customer").annotate(
            product_count=Count("products")
        )

    def get_store(self, *, actor, store_public_id) -> ShopifyStore:
        store = self.list_stores(actor=actor).filter(public_id=store_public_id).first()
        if store is None:
            raise ValidationError("Boutique introuvable.")
        return store

    def assign_store_customer(self, *, actor, store_public_id, customer_public_id) -> ShopifyStore:
        require_staff_perm(
            actor,
            self.manage_permission,
            source="pod.shopify.store_customer",
            action="pod.shopify.permission_rejected",
        )
        require_staff_perm(
            actor,
            self.customer_view_permission,
            source="pod.shopify.store_customer",
            action="pod.shopify.permission_rejected",
        )
        with transaction.atomic():
            store = (
                ShopifyStore.objects.select_for_update().filter(public_id=store_public_id).first()
            )
            if store is None:
                raise ValidationError("Boutique introuvable.")
            customer = Customer.objects.active().filter(public_id=customer_public_id).first()
            if customer is None:
                raise ValidationError("Client actif introuvable.")
            if store.customer_id not in (None, customer.pk):
                raise ValidationError(
                    "Cette boutique est déjà liée à un autre client. "
                    "Une migration contrôlée est requise."
                )
            if store.customer_id is None:
                store.customer = customer
                store.save(update_fields=["customer", "updated_at"])
                record_event(
                    action="pod.shopify.store_customer_assigned",
                    actor=actor,
                    target=store,
                    metadata={"customer_public_id": str(customer.public_id)},
                )
            return store

    def oauth_is_configured(self) -> bool:
        return bool(settings.SHOPIFY_POD_API_KEY and settings.SHOPIFY_POD_API_SECRET)

    def authorization_url(self, *, actor, shop_domain: str) -> str:
        require_staff_perm(
            actor,
            self.manage_permission,
            source="pod.shopify",
            action="pod.shopify.permission_rejected",
        )
        if not self.oauth_is_configured():
            raise ValidationError(
                "Renseignez SHOPIFY_POD_API_KEY et SHOPIFY_POD_API_SECRET pour l’OAuth."
            )
        shop = normalize_shop_domain(shop_domain)
        state = self.signer.sign(shop)
        redirect_uri = f"{settings.PUBLIC_BASE_URL}/integrations/shopify/pod/oauth/callback/"
        query = urlencode(
            {
                "client_id": settings.SHOPIFY_POD_API_KEY,
                "scope": settings.SHOPIFY_POD_SCOPES,
                "redirect_uri": redirect_uri,
                "state": state,
            }
        )
        return f"https://{shop}/admin/oauth/authorize?{query}"

    def complete_oauth(self, *, query) -> ShopifyStore:
        query = {key: query.get(key) for key in query}
        shop = normalize_shop_domain(str(query.get("shop") or ""))
        state = str(query.get("state") or "")
        code = str(query.get("code") or "")
        if not code:
            raise ValidationError("Code OAuth Shopify manquant.")
        try:
            unsigned = self.signer.unsign(state, max_age=600)
        except BadSignature as exc:
            raise ValidationError("State OAuth invalide ou expiré.") from exc
        if unsigned != shop:
            raise ValidationError("State OAuth ne correspond pas à la boutique.")
        self._verify_oauth_hmac(query)
        payload = self.token_exchange(
            f"https://{shop}/admin/oauth/access_token",
            {
                "client_id": settings.SHOPIFY_POD_API_KEY,
                "client_secret": settings.SHOPIFY_POD_API_SECRET,
                "code": code,
            },
        )
        token = str(payload.get("access_token") or "").strip()
        scopes = str(payload.get("scope") or settings.SHOPIFY_POD_SCOPES)
        if not token:
            raise ValidationError("Token OAuth Shopify manquant.")
        store = self._persist_token(shop=shop, token=token, scopes=scopes, source="oauth")
        self._after_token(store=store)
        return store

    def save_manual_token(
        self, *, actor, shop_domain: str, token: str, name: str = ""
    ) -> ShopifyStore:
        require_staff_perm(
            actor,
            self.manage_permission,
            source="pod.shopify",
            action="pod.shopify.permission_rejected",
        )
        shop = normalize_shop_domain(shop_domain)
        store = self._persist_token(
            shop=shop,
            token=token,
            scopes=settings.SHOPIFY_POD_SCOPES,
            source="manual",
            name=name,
        )
        try:
            self._after_token(store=store)
        except ValidationError:
            record_event(
                action="pod.shopify.post_connect_partial",
                actor=actor,
                target=store,
                status="failure",
                message="Token enregistré ; webhooks ou import à relancer.",
            )
            raise
        record_event(
            action="pod.shopify.store_connected",
            actor=actor,
            target=store,
            metadata={"shop": shop, "mode": "manual"},
        )
        return store

    def install_webhooks(self, *, store: ShopifyStore) -> None:
        token = decrypt_shopify_token(store.access_token_encrypted)
        address = f"{settings.PUBLIC_BASE_URL}/webhooks/shopify/pod/fulfillment/"
        for topic in ("orders/create", "orders/updated", "orders/cancelled"):
            payload = {
                "webhook": {
                    "topic": topic,
                    "address": address,
                    "format": "json",
                }
            }
            try:
                self.http.request(
                    method="POST",
                    url=shopify_admin_url(store.shop_domain, "webhooks.json"),
                    headers={"X-Shopify-Access-Token": token},
                    payload=payload,
                )
            except ValidationError as exc:
                if "422" not in str(exc):
                    raise

    def import_catalog(self, *, store: ShopifyStore) -> int:
        token = decrypt_shopify_token(store.access_token_encrypted)
        created = 0
        for product_payload in self._iter_shopify_products(store=store, token=token):
            created += self._upsert_product_payload(store=store, product_payload=product_payload)
        record_event(
            action="pod.shopify.catalog_imported",
            target=store,
            metadata={"variants": created, "shop": store.shop_domain},
        )
        return created

    def _iter_shopify_products(self, *, store: ShopifyStore, token: str):
        since_id = 0
        while True:
            data = self.http.request(
                method="GET",
                url=shopify_admin_url(
                    store.shop_domain,
                    f"products.json?limit=250&since_id={since_id}",
                ),
                headers={"X-Shopify-Access-Token": token},
            )
            products = data.get("products") or []
            if not products:
                break
            yield from products
            last_id = products[-1].get("id")
            try:
                since_id = int(last_id)
            except (TypeError, ValueError):
                break
            if len(products) < 250:
                break

    def _upsert_product_payload(self, *, store: ShopifyStore, product_payload: dict) -> int:
        handle = slugify(
            str(product_payload.get("handle") or product_payload.get("title") or "produit")
        )
        product_external = str(
            product_payload.get("id") or product_payload.get("admin_graphql_api_id")
        )[:64]
        image_map, product_image_url, product_image_id = self._extract_product_images(
            product_payload
        )
        product, _ = ShopifyProduct.objects.get_or_create(
            store=store,
            external_id=product_external,
            defaults={
                "title": str(product_payload.get("title") or "Produit Shopify")[:255],
                "handle": handle[:255],
                "image_url": product_image_url[:512],
                "image_external_id": product_image_id[:64],
            },
        )
        product.title = str(product_payload.get("title") or product.title)[:255]
        product.handle = handle[:255]
        product.image_url = product_image_url[:512]
        product.image_external_id = product_image_id[:64]
        product.save(
            update_fields=["title", "handle", "image_url", "image_external_id", "updated_at"]
        )
        created = 0
        for variant_payload in product_payload.get("variants") or []:
            variant_external = str(
                variant_payload.get("id") or variant_payload.get("admin_graphql_api_id")
            )[:64]
            variant_image_id, variant_image_url = self._resolve_variant_image(
                variant_payload,
                image_map=image_map,
                fallback_url=product_image_url,
            )
            variant, was_created = ShopifyVariant.objects.get_or_create(
                product=product,
                external_id=variant_external,
                defaults={
                    "title": str(variant_payload.get("title") or "")[:255],
                    "sku": str(variant_payload.get("sku") or "")[:80],
                    "option1": str(variant_payload.get("option1") or "")[:120],
                    "option2": str(variant_payload.get("option2") or "")[:120],
                    "option3": str(variant_payload.get("option3") or "")[:120],
                    "image_url": variant_image_url[:512],
                    "image_external_id": variant_image_id[:64],
                },
            )
            if was_created:
                IdsVariantConfig.objects.get_or_create(variant=variant)
                created += 1
            else:
                variant.sku = str(variant_payload.get("sku") or variant.sku)[:80]
                variant.title = str(variant_payload.get("title") or variant.title)[:255]
                variant.option1 = str(variant_payload.get("option1") or "")[:120]
                variant.option2 = str(variant_payload.get("option2") or "")[:120]
                variant.option3 = str(variant_payload.get("option3") or "")[:120]
                variant.image_url = variant_image_url[:512]
                variant.image_external_id = variant_image_id[:64]
                variant.save(
                    update_fields=[
                        "sku",
                        "title",
                        "option1",
                        "option2",
                        "option3",
                        "image_url",
                        "image_external_id",
                        "updated_at",
                    ]
                )
        return created

    @staticmethod
    def _extract_product_images(product_payload: dict) -> tuple[dict[str, str], str, str]:
        image_map: dict[str, str] = {}
        for image in product_payload.get("images") or []:
            image_id = str(image.get("id") or "").strip()
            src = str(image.get("src") or "").strip()
            if image_id and src:
                image_map[image_id] = src
        featured = product_payload.get("image") or {}
        featured_id = str(featured.get("id") or "").strip()
        featured_src = str(featured.get("src") or "").strip()
        if featured_id and featured_src:
            image_map.setdefault(featured_id, featured_src)
        if not featured_src and image_map:
            featured_id, featured_src = next(iter(image_map.items()))
        return image_map, featured_src, featured_id

    @staticmethod
    def _resolve_variant_image(
        variant_payload: dict, *, image_map: dict[str, str], fallback_url: str
    ) -> tuple[str, str]:
        image_id = str(variant_payload.get("image_id") or "").strip()
        if image_id and image_id in image_map:
            return image_id, image_map[image_id]
        nested = variant_payload.get("image") or {}
        nested_src = str(nested.get("src") or "").strip()
        nested_id = str(nested.get("id") or image_id or "").strip()
        if nested_src:
            return nested_id, nested_src
        return "", fallback_url

    def run_store_action(self, *, actor, store_public_id, intent: str) -> ShopifyStore:
        require_staff_perm(
            actor,
            self.manage_permission,
            source="pod.shopify",
            action="pod.shopify.permission_rejected",
        )
        store = self.get_store(actor=actor, store_public_id=store_public_id)
        if not store.access_token_encrypted:
            raise ValidationError("Aucun token Shopify enregistré.")
        if intent == "import":
            self.import_catalog(store=store)
        elif intent == "webhooks":
            self.install_webhooks(store=store)
        elif intent == "sync":
            self.install_webhooks(store=store)
            self.import_catalog(store=store)
        else:
            raise ValidationError("Action boutique inconnue.")
        return store

    def _after_token(self, *, store: ShopifyStore) -> None:
        self._remember_shop_name(store)
        self.install_webhooks(store=store)
        self.import_catalog(store=store)

    def _remember_shop_name(self, store: ShopifyStore) -> None:
        token = decrypt_shopify_token(store.access_token_encrypted)
        try:
            data = self.http.request(
                method="GET",
                url=shopify_admin_url(store.shop_domain, "shop.json"),
                headers={"X-Shopify-Access-Token": token},
            )
        except ValidationError:
            return
        name = str((data.get("shop") or {}).get("name") or "").strip()
        if not name or name == store.name:
            return
        store.name = name[:160]
        store.save(update_fields=["name", "updated_at"])

    def _persist_token(
        self, *, shop: str, token: str, scopes: str, source: str, name: str = ""
    ) -> ShopifyStore:
        encrypted = encrypt_shopify_token(token)
        slug = slugify(shop.replace(".myshopify.com", ""))[:64] or "shopify-store"
        store, _ = ShopifyStore.objects.get_or_create(
            shop_domain=shop,
            defaults={
                "slug": slug,
                "name": (name or shop).strip()[:160],
                "is_active": True,
            },
        )
        store.access_token_encrypted = encrypted
        store.token_suffix = token_suffix(token)
        store.oauth_scopes = scopes[:255]
        store.connected_at = timezone.now()
        store.is_active = True
        # The app OAuth secret is read from settings for HMAC verification. It
        # must never be duplicated in cleartext in every ShopifyStore row.
        if store.webhook_secret == settings.SHOPIFY_POD_API_SECRET:
            store.webhook_secret = ""
        store.save(
            update_fields=[
                "access_token_encrypted",
                "token_suffix",
                "oauth_scopes",
                "connected_at",
                "is_active",
                "webhook_secret",
                "updated_at",
            ]
        )
        record_event(
            action="pod.shopify.token_saved",
            target=store,
            metadata={"shop": shop, "source": source, "suffix": store.token_suffix},
        )
        return store

    def _verify_oauth_hmac(self, query: dict) -> None:
        secret = (settings.SHOPIFY_POD_API_SECRET or "").encode()
        provided = str(query.get("hmac") or "")
        if not secret or not provided:
            raise ValidationError("HMAC OAuth Shopify manquant.")
        pairs = [f"{key}={query[key]}" for key in sorted(query) if key not in {"hmac", "signature"}]
        digest = hmac.new(secret, "&".join(pairs).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(digest, provided):
            raise ValidationError("HMAC OAuth Shopify invalide.")
