from __future__ import annotations

import hashlib
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class PushSecretDecryptionError(ValueError):
    """Raised when an encrypted subscription secret cannot be decrypted."""


@dataclass(frozen=True)
class _VersionedKey:
    version: str
    fernet: Fernet


class PushSubscriptionCrypto:
    """Encrypt browser subscription material with dedicated, rotatable keys."""

    def __init__(self, raw_keys: tuple[str, ...] | list[str] | None = None) -> None:
        configured = raw_keys if raw_keys is not None else settings.WEB_PUSH_ENCRYPTION_KEYS
        self._keys = self._parse_keys(tuple(configured))

    @staticmethod
    def endpoint_digest(endpoint: str) -> str:
        return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()

    def encrypt(self, value: str) -> str:
        self._require_keys()
        primary = self._keys[0]
        token = primary.fernet.encrypt(value.encode("utf-8")).decode("ascii")
        return f"{primary.version}:{token}"

    def decrypt(self, value: str) -> str:
        self._require_keys()
        version, separator, token = value.partition(":")
        if not separator:
            raise PushSecretDecryptionError("Invalid encrypted Web Push value")

        ordered = [item.fernet for item in self._keys if item.version == version]
        ordered.extend(item.fernet for item in self._keys if item.version != version)
        try:
            cleartext = MultiFernet(ordered).decrypt(token.encode("ascii"))
        except (InvalidToken, ValueError) as exc:
            raise PushSecretDecryptionError("Unable to decrypt Web Push value") from exc
        return cleartext.decode("utf-8")

    def _require_keys(self) -> None:
        if not self._keys:
            raise ImproperlyConfigured("WEB_PUSH_ENCRYPTION_KEYS must contain at least one key")

    @staticmethod
    def _parse_keys(raw_keys: tuple[str, ...]) -> tuple[_VersionedKey, ...]:
        parsed: list[_VersionedKey] = []
        versions: set[str] = set()
        for index, raw_key in enumerate(raw_keys):
            entry = raw_key.strip()
            if not entry:
                continue
            version, separator, key = entry.partition(":")
            if not separator:
                version = f"v{index + 1}"
                key = entry
            if not version or version in versions:
                raise ImproperlyConfigured("WEB_PUSH_ENCRYPTION_KEYS versions must be unique")
            try:
                fernet = Fernet(key.encode("ascii"))
            except (ValueError, TypeError) as exc:
                raise ImproperlyConfigured(
                    "WEB_PUSH_ENCRYPTION_KEYS contains an invalid key"
                ) from exc
            versions.add(version)
            parsed.append(_VersionedKey(version=version, fernet=fernet))
        return tuple(parsed)
