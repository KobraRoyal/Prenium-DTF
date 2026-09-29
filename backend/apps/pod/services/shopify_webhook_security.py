from __future__ import annotations

import base64
import hashlib
import hmac

from django.core.exceptions import ValidationError

from apps.auditlog.services import record_event
from apps.pod.models import ShopifyStore
from apps.pod.services.shopify_connect import hmac_secrets_for_store


def authenticate_shopify_webhook(
    *, raw_body: bytes, hmac_header: str, shop_domain: str
) -> ShopifyStore:
    """Authenticate a Shopify webhook before any asynchronous hand-off."""
    store = ShopifyStore.objects.filter(
        shop_domain=(shop_domain or "").strip().lower(),
        is_active=True,
    ).first()
    if store is None:
        _reject(shop_domain=shop_domain, reason="unknown_store")
        raise ValidationError("Boutique inconnue.")

    provided = (hmac_header or "").removeprefix("sha256=").strip()
    secrets = hmac_secrets_for_store(store)
    if not secrets or not provided:
        _reject(shop_domain=shop_domain, reason="missing_signature")
        raise ValidationError("Secret ou signature webhook Shopify manquant.")

    for secret in secrets:
        expected = base64.b64encode(hmac.new(secret, raw_body, hashlib.sha256).digest()).decode()
        if hmac.compare_digest(expected, provided):
            return store

    _reject(shop_domain=shop_domain, reason="invalid_hmac")
    raise ValidationError("HMAC Shopify invalide.")


def _reject(*, shop_domain: str, reason: str) -> None:
    record_event(
        action="pod.shopify.webhook_rejected",
        status="failure",
        message="Authentification webhook Shopify refusée.",
        metadata={"shop": (shop_domain or "").strip().lower(), "reason": reason},
    )
