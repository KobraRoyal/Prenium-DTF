from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError


class PushEndpointValidationError(ValidationError):
    pass


class WebPushDeliveryError(RuntimeError):
    def __init__(self, *, code: str, status_code: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class WebPushGone(WebPushDeliveryError):
    pass


class WebPushTransientError(WebPushDeliveryError):
    pass


class WebPushPermanentError(WebPushDeliveryError):
    pass


def validate_subscription_keys(*, p256dh: str, auth: str) -> None:
    """Validate the standard Web Push P-256 public key and auth secret."""

    public_key = _decode_base64url_secret(p256dh)
    auth_secret = _decode_base64url_secret(auth)
    if len(public_key) != 65 or public_key[0] != 4 or len(auth_secret) != 16:
        raise PushEndpointValidationError("Invalid Web Push subscription keys")


def _decode_base64url_secret(value: str) -> bytes:
    if not value or len(value) > 512 or any(ord(char) > 127 for char in value):
        raise PushEndpointValidationError("Invalid Web Push subscription keys")
    padding = "=" * (-len(value) % 4)
    try:
        return base64.b64decode(
            (value + padding).encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError) as exc:
        raise PushEndpointValidationError("Invalid Web Push subscription keys") from exc


@dataclass(frozen=True)
class WebPushConfiguration:
    vapid_public_key: str
    vapid_private_key: str
    vapid_contact: str
    allowed_domains: tuple[str, ...]
    timeout_seconds: int

    @classmethod
    def from_settings(cls) -> WebPushConfiguration:
        return cls(
            vapid_public_key=settings.WEB_PUSH_VAPID_PUBLIC_KEY.strip(),
            vapid_private_key=settings.WEB_PUSH_VAPID_PRIVATE_KEY.strip(),
            vapid_contact=settings.WEB_PUSH_VAPID_CONTACT.strip(),
            allowed_domains=tuple(settings.WEB_PUSH_ALLOWED_DOMAINS),
            timeout_seconds=settings.WEB_PUSH_TIMEOUT_SECONDS,
        )

    def validate(self) -> None:
        if not settings.WEB_PUSH_ENABLED:
            raise ImproperlyConfigured("Web Push is disabled")
        if not self.vapid_public_key or not self.vapid_private_key or not self.vapid_contact:
            raise ImproperlyConfigured("Web Push VAPID settings are incomplete")
        if not self.vapid_contact.startswith(("mailto:", "https://")):
            raise ImproperlyConfigured("WEB_PUSH_VAPID_CONTACT must use mailto: or https:")
        if not self.allowed_domains:
            raise ImproperlyConfigured("WEB_PUSH_ALLOWED_DOMAINS must not be empty")
        if self.timeout_seconds <= 0:
            raise ImproperlyConfigured("WEB_PUSH_TIMEOUT_SECONDS must be positive")


@dataclass(frozen=True)
class ValidatedPushEndpoint:
    endpoint: str
    hostname: str
    addresses: frozenset[str]


Resolver = Callable[..., list[tuple]]


def validate_push_endpoint(
    endpoint: str,
    *,
    allowed_domains: tuple[str, ...] | list[str] | None = None,
    resolver=socket.getaddrinfo,
) -> str:
    """Reject non-HTTPS, non-allowlisted and non-public push service endpoints."""

    return _validate_and_resolve_push_endpoint(
        endpoint,
        allowed_domains=allowed_domains,
        resolver=resolver,
    ).endpoint


def _validate_and_resolve_push_endpoint(
    endpoint: str,
    *,
    allowed_domains: tuple[str, ...] | list[str] | None = None,
    resolver: Resolver = socket.getaddrinfo,
) -> ValidatedPushEndpoint:
    if not endpoint or len(endpoint) > 4096 or any(ord(char) < 32 for char in endpoint):
        raise PushEndpointValidationError("Invalid Web Push endpoint")
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError as exc:
        raise PushEndpointValidationError("Invalid Web Push endpoint") from exc
    if parsed.scheme != "https" or not parsed.hostname:
        raise PushEndpointValidationError("Web Push endpoint must use HTTPS")
    if parsed.username or parsed.password or parsed.fragment or port not in (None, 443):
        raise PushEndpointValidationError("Invalid Web Push endpoint authority")

    hostname = parsed.hostname.rstrip(".").lower()
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise PushEndpointValidationError("IP Web Push endpoints are not allowed")

    allowed = tuple(allowed_domains or settings.WEB_PUSH_ALLOWED_DOMAINS)
    if not any(_hostname_matches(hostname, domain) for domain in allowed):
        raise PushEndpointValidationError("Web Push endpoint domain is not allowed")

    try:
        addresses = resolver(hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise PushEndpointValidationError("Web Push endpoint cannot be resolved") from exc
    if not addresses:
        raise PushEndpointValidationError("Web Push endpoint cannot be resolved")
    resolved_ips: set[str] = set()
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise PushEndpointValidationError("Web Push endpoint resolved to a non-public address")
        resolved_ips.add(ip.compressed)
    return ValidatedPushEndpoint(
        endpoint=endpoint,
        hostname=hostname,
        addresses=frozenset(resolved_ips),
    )


def _hostname_matches(hostname: str, configured_domain: str) -> bool:
    allowed = configured_domain.strip().rstrip(".").lower()
    if not allowed:
        return False
    if allowed.startswith("*."):
        suffix = allowed[1:]
        return hostname.endswith(suffix) and hostname != suffix[1:]
    return hostname == allowed


class SafeWebPushSession(requests.Session):
    """Requests transport that blocks redirects, proxies and DNS changes before POST."""

    def __init__(
        self,
        *,
        approved_endpoint: ValidatedPushEndpoint,
        allowed_domains: tuple[str, ...],
        resolver: Resolver,
    ) -> None:
        super().__init__()
        self.trust_env = False
        self._approved_endpoint = approved_endpoint
        self._allowed_domains = allowed_domains
        self._resolver = resolver

    def post(self, url, data=None, json=None, **kwargs):
        current = _validate_and_resolve_push_endpoint(
            str(url),
            allowed_domains=self._allowed_domains,
            resolver=self._resolver,
        )
        if (
            current.endpoint != self._approved_endpoint.endpoint
            or current.hostname != self._approved_endpoint.hostname
            or current.addresses != self._approved_endpoint.addresses
        ):
            raise PushEndpointValidationError("Web Push endpoint resolution changed")
        kwargs["allow_redirects"] = False
        return super().post(url, data=data, json=json, **kwargs)


class WebPushClient:
    """Small pywebpush adapter that never includes subscription secrets in errors."""

    def __init__(
        self,
        configuration: WebPushConfiguration | None = None,
        *,
        resolver: Resolver = socket.getaddrinfo,
    ) -> None:
        self.configuration = configuration or WebPushConfiguration.from_settings()
        self._resolver = resolver

    def send(self, *, endpoint: str, p256dh: str, auth: str, payload: dict[str, str]) -> None:
        self.configuration.validate()
        approved_endpoint = _validate_and_resolve_push_endpoint(
            endpoint,
            allowed_domains=self.configuration.allowed_domains,
            resolver=self._resolver,
        )
        session = SafeWebPushSession(
            approved_endpoint=approved_endpoint,
            allowed_domains=self.configuration.allowed_domains,
            resolver=self._resolver,
        )
        from pywebpush import WebPushException, webpush

        try:
            try:
                webpush(
                    subscription_info={
                        "endpoint": endpoint,
                        "keys": {"p256dh": p256dh, "auth": auth},
                    },
                    data=json.dumps(payload, separators=(",", ":")),
                    vapid_private_key=self.configuration.vapid_private_key,
                    vapid_claims={"sub": self.configuration.vapid_contact},
                    timeout=self.configuration.timeout_seconds,
                    requests_session=session,
                )
            finally:
                session.close()
        except WebPushException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in {404, 410}:
                raise WebPushGone(code="subscription_gone", status_code=status_code) from None
            if status_code is None or status_code == 429 or status_code >= 500:
                raise WebPushTransientError(
                    code="provider_temporarily_unavailable",
                    status_code=status_code,
                ) from None
            raise WebPushPermanentError(
                code="provider_rejected",
                status_code=status_code,
            ) from None
