from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.exceptions import ValidationError


class ShopifyHttpClient:
    timeout_seconds = 20

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict | None = None,
        payload: dict | None = None,
    ) -> dict:
        body = None
        request_headers = {"Accept": "application/json", **(headers or {})}
        if payload is not None:
            body = json.dumps(payload).encode()
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8") or "{}"
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:240]
            raise ValidationError(f"API Shopify HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ValidationError("API Shopify injoignable.") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError("Réponse Shopify JSON invalide.") from exc


def shopify_admin_url(shop_domain: str, path: str) -> str:
    version = getattr(settings, "SHOPIFY_API_VERSION", "2024-10")
    return f"https://{shop_domain}/admin/api/{version}/{path.lstrip('/')}"


def shopify_form_post(url: str, data: dict) -> dict:
    encoded = urllib.parse.urlencode(data).encode()
    request = urllib.request.Request(url, data=encoded, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8") or "{}"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:240]
        raise ValidationError(f"OAuth Shopify HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ValidationError("OAuth Shopify injoignable.") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError("Réponse OAuth Shopify invalide.") from exc
