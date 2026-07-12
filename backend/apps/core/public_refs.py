from __future__ import annotations

import uuid


def short_public_ref(value) -> str:
    """Dernier segment d'un UUID (ex. 55576b264201)."""
    if value is None:
        return ""
    if isinstance(value, uuid.UUID):
        return value.hex[-12:]
    text = str(value).strip()
    if not text:
        return text
    if "-" in text:
        return text.rsplit("-", 1)[-1]
    return text[-12:] if len(text) >= 12 else text
