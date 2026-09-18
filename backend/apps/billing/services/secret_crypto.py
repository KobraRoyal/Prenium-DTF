from __future__ import annotations

from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class PaymentSecretDecryptionError(ValueError):
    """Raised when an encrypted payment secret cannot be decrypted."""


@dataclass(frozen=True)
class _VersionedKey:
    version: str
    fernet: Fernet


class PaymentSecretCrypto:
    """Encrypt PayPal/Stripe secrets with rotatable Fernet keys."""

    def __init__(self, raw_keys: tuple[str, ...] | list[str] | None = None) -> None:
        if raw_keys is not None:
            configured = tuple(raw_keys)
        else:
            configured = tuple(getattr(settings, "PAYMENT_SECRET_ENCRYPTION_KEYS", ()) or ())
            if not configured:
                configured = tuple(settings.WEB_PUSH_ENCRYPTION_KEYS or ())
        self._keys = self._parse_keys(configured)

    def encrypt(self, value: str) -> str:
        self._require_keys()
        primary = self._keys[0]
        token = primary.fernet.encrypt(value.encode("utf-8")).decode("ascii")
        return f"{primary.version}:{token}"

    def decrypt(self, value: str) -> str:
        self._require_keys()
        version, separator, token = value.partition(":")
        if not separator:
            raise PaymentSecretDecryptionError("Invalid encrypted payment secret")

        ordered = [item.fernet for item in self._keys if item.version == version]
        ordered.extend(item.fernet for item in self._keys if item.version != version)
        try:
            cleartext = MultiFernet(ordered).decrypt(token.encode("ascii"))
        except (InvalidToken, ValueError) as exc:
            raise PaymentSecretDecryptionError("Unable to decrypt payment secret") from exc
        return cleartext.decode("utf-8")

    def decrypt_or_empty(self, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            return ""
        try:
            return self.decrypt(cleaned)
        except PaymentSecretDecryptionError:
            return ""

    def _require_keys(self) -> None:
        if not self._keys:
            raise ImproperlyConfigured(
                "PAYMENT_SECRET_ENCRYPTION_KEYS or WEB_PUSH_ENCRYPTION_KEYS "
                "must contain at least one key"
            )

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
                raise ImproperlyConfigured("PAYMENT_SECRET_ENCRYPTION_KEYS versions must be unique")
            try:
                fernet = Fernet(key.encode("ascii"))
            except (ValueError, TypeError) as exc:
                raise ImproperlyConfigured(
                    "PAYMENT_SECRET_ENCRYPTION_KEYS contains an invalid key"
                ) from exc
            versions.add(version)
            parsed.append(_VersionedKey(version=version, fernet=fernet))
        return tuple(parsed)
