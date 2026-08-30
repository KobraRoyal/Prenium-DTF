from __future__ import annotations

import re
import unicodedata

ASCII_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def ascii_token(value: str, *, fallback: str = "x") -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    token = ASCII_TOKEN_RE.sub("-", ascii_only).strip("-")
    return token or fallback


def rip_filename(
    *, shop_slug: str, order_number: str, placement: str, sku: str, extension: str
) -> str:
    shop = ascii_token(shop_slug, fallback="shop")
    order = ascii_token(order_number, fallback="so")
    pose = ascii_token(placement, fallback="zone")
    sku_token = ascii_token(sku, fallback="sku")
    ext = extension if extension.startswith(".") else f".{extension}"
    return f"{shop}_{order}_{pose}_{sku_token}{ext}"
