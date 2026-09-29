from __future__ import annotations

import base64
import hashlib

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _fernet():
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover
        raise ImproperlyConfigured("Le paquet cryptography est requis.") from exc
    configured = (getattr(settings, "SHOPIFY_TOKEN_FERNET_KEY", "") or "").strip()
    if configured:
        key = configured.encode()
    else:
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_shopify_token(token: str) -> str:
    value = (token or "").strip()
    if not value:
        raise ValueError("Token Shopify vide.")
    return _fernet().encrypt(value.encode()).decode()


def decrypt_shopify_token(payload: str) -> str:
    blob = (payload or "").strip()
    if not blob:
        raise ValueError("Aucun token Shopify chiffré.")
    return _fernet().decrypt(blob.encode()).decode()


def token_suffix(token: str) -> str:
    clean = (token or "").strip()
    return clean[-4:] if len(clean) >= 4 else clean
