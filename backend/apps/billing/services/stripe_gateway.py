from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal
from urllib import error, parse, request

from django.conf import settings

from apps.billing.services.gateways import (
    CheckoutConfirmResult,
    CheckoutCreateResult,
    PaymentGatewayConfigurationError,
    PaymentGatewayError,
    PaymentGatewayTransientError,
    open_provider_request,
    validate_provider_checkout_url,
)
from apps.orders.models import Order


class StripeAPIError(PaymentGatewayError):
    pass


class StripeTransientError(PaymentGatewayTransientError):
    pass


class StripeGateway:
    provider = "stripe"

    def __init__(self):
        from apps.billing.services.gateway_settings import payment_gateway_settings_service

        config = payment_gateway_settings_service.effective()
        self.secret_key = config.stripe_secret_key
        self.api_base_url = settings.STRIPE_API_BASE_URL.rstrip("/")
        self.api_version = getattr(settings, "STRIPE_API_VERSION", "2026-07-29.dahlia")
        self.timeout_seconds = settings.STRIPE_TIMEOUT_SECONDS
        self.webhook_secret = config.stripe_webhook_secret
        if not self.secret_key:
            raise PaymentGatewayConfigurationError(
                "Stripe credentials must be configured in Atelier settings or STRIPE_SECRET_KEY."
            )
        if self.api_base_url != "https://api.stripe.com":
            raise PaymentGatewayConfigurationError("URL API Stripe non officielle.")

    def probe_readiness(self) -> None:
        """Vérifie la clé et la permission de lecture Checkout sans créer de session."""
        payload = self._request_form(method="GET", path="/v1/checkout/sessions?limit=1", form=None)
        if not isinstance(payload.get("data"), list):
            raise StripeAPIError("Réponse de lecture des sessions Stripe invalide.")

    def create_checkout(
        self,
        *,
        order: Order,
        success_url: str,
        cancel_url: str,
        idempotency_key: str = "",
    ) -> CheckoutCreateResult:
        amount_cents = int((Decimal(order.total_amount) * Decimal("100")).quantize(Decimal("1")))
        if amount_cents <= 0:
            raise StripeAPIError("Montant Stripe invalide.")

        form = {
            "mode": "payment",
            "payment_method_types[0]": "card",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": str(order.public_id),
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": order.currency.lower(),
            "line_items[0][price_data][unit_amount]": str(amount_cents),
            "line_items[0][price_data][product_data][name]": f"Commande {order.public_id}",
            "metadata[order_public_id]": str(order.public_id),
            "metadata[customer_public_id]": str(order.customer.public_id),
            "metadata[payment_public_id]": idempotency_key,
        }
        # Stripe ignore les valeurs None ; on filtre.
        body = {k: v for k, v in form.items() if v is not None}
        payload = self._request_form(
            method="POST",
            path="/v1/checkout/sessions",
            form=body,
            idempotency_key=idempotency_key or str(order.public_id),
        )
        return CheckoutCreateResult(
            provider_payment_id=str(payload.get("id", "")).strip(),
            status=str(payload.get("status", "")).strip() or "open",
            checkout_url=validate_provider_checkout_url(
                url=str(payload.get("url", "")).strip(),
                provider="Stripe",
                allowed_hosts={"checkout.stripe.com"},
            ),
            payload=payload,
            provider_capture_id=str(payload.get("payment_intent") or "").strip(),
        )

    def confirm_checkout(self, *, provider_payment_id: str) -> CheckoutConfirmResult:
        payload = self._request_form(
            method="GET",
            path=f"/v1/checkout/sessions/{provider_payment_id}",
            form=None,
        )
        payment_status = str(payload.get("payment_status", "")).strip().lower()
        session_status = str(payload.get("status", "")).strip().lower()
        if payment_status == "paid":
            normalized = "COMPLETED"
        elif session_status in {"open", "complete"} and payment_status == "unpaid":
            normalized = "PENDING"
        else:
            normalized = session_status.upper() or "FAILED"

        payment_intent = payload.get("payment_intent")
        if isinstance(payment_intent, dict):
            capture_id = str(payment_intent.get("id", "")).strip()
        else:
            capture_id = str(payment_intent or "").strip()

        amount_total = payload.get("amount_total")
        return CheckoutConfirmResult(
            provider_payment_id=str(payload.get("id", "")).strip() or provider_payment_id,
            provider_capture_id=capture_id,
            status=normalized,
            payload=payload,
            amount_total_cents=int(amount_total) if amount_total is not None else None,
            currency=str(payload.get("currency") or "").upper() or None,
        )

    def checkout_state(self, *, provider_payment_id: str) -> str:
        payload = self._request_form(
            method="GET", path=f"/v1/checkout/sessions/{provider_payment_id}", form=None
        )
        if str(payload.get("payment_status") or "").lower() == "paid":
            return "COMPLETED"
        return str(payload.get("status") or "").upper()

    def verify_checkout_binding(
        self,
        *,
        provider_payment_id: str,
        payment_public_id,
        order_public_id,
        customer_public_id,
        amount,
        currency,
        allow_legacy_missing_payment_id: bool = False,
    ) -> dict[str, object]:
        payload = self._request_form(
            method="GET", path=f"/v1/checkout/sessions/{provider_payment_id}", form=None
        )
        metadata = payload.get("metadata") or {}
        remote_payment_id = (
            str(metadata.get("payment_public_id") or "") if isinstance(metadata, dict) else ""
        )
        payment_id_matches = remote_payment_id == str(payment_public_id) or (
            allow_legacy_missing_payment_id and not remote_payment_id
        )
        expected_cents = int((Decimal(amount) * Decimal("100")).quantize(Decimal("1")))
        if (
            str(payload.get("id") or "") != provider_payment_id
            or str(payload.get("client_reference_id") or "") != str(order_public_id)
            or not isinstance(metadata, dict)
            or str(metadata.get("order_public_id") or "") != str(order_public_id)
            or str(metadata.get("customer_public_id") or "") != str(customer_public_id)
            or not payment_id_matches
            or payload.get("amount_total") is None
            or int(payload["amount_total"]) != expected_cents
            or str(payload.get("currency") or "").upper() != str(currency).upper()
        ):
            raise StripeAPIError("Session Stripe liée à une autre tentative ou montant incohérent.")
        return payload

    def resume_checkout(self, *, provider_payment_id: str, order: Order, payment_public_id):
        payload = self._request_form(
            method="GET", path=f"/v1/checkout/sessions/{provider_payment_id}", form=None
        )
        expected_cents = int((Decimal(order.total_amount) * Decimal("100")).quantize(Decimal("1")))
        metadata = payload.get("metadata") or {}
        remote_payment_id = (
            str(metadata.get("payment_public_id") or "") if isinstance(metadata, dict) else ""
        )
        if (
            str(payload.get("id") or "") != provider_payment_id
            or str(payload.get("status") or "").lower() != "open"
            or str(payload.get("payment_status") or "").lower() != "unpaid"
            or str(payload.get("client_reference_id") or "") != str(order.public_id)
            or not isinstance(metadata, dict)
            or str(metadata.get("order_public_id") or "") != str(order.public_id)
            or str(metadata.get("customer_public_id") or "") != str(order.customer.public_id)
            or remote_payment_id not in {"", str(payment_public_id)}
            or payload.get("amount_total") is None
            or int(payload["amount_total"]) != expected_cents
            or str(payload.get("currency") or "").upper() != str(order.currency).upper()
        ):
            raise StripeAPIError("Session Stripe impossible à reprendre sans rapprochement.")
        return CheckoutCreateResult(
            provider_payment_id=provider_payment_id,
            status="OPEN",
            checkout_url=validate_provider_checkout_url(
                url=str(payload.get("url") or ""),
                provider="Stripe",
                allowed_hosts={"checkout.stripe.com"},
            ),
            payload=payload,
            provider_capture_id=str(payload.get("payment_intent") or ""),
        )

    def expire_checkout(self, *, provider_payment_id: str) -> str:
        payload = self._request_form(
            method="POST",
            path=f"/v1/checkout/sessions/{provider_payment_id}/expire",
            form={},
            idempotency_key=f"expire-{provider_payment_id}",
        )
        return str(payload.get("status") or "").upper()

    def verify_and_parse_webhook(
        self,
        *,
        payload: bytes,
        signature_header: str,
    ) -> dict[str, object]:
        if not self.webhook_secret:
            raise PaymentGatewayConfigurationError(
                "Stripe webhook secret must be configured in Atelier settings "
                "or STRIPE_WEBHOOK_SECRET."
            )
        self._verify_signature(payload=payload, signature_header=signature_header)
        try:
            return json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise StripeAPIError("Invalid Stripe webhook payload.") from exc

    def _verify_signature(self, *, payload: bytes, signature_header: str) -> None:
        elements = {}
        for part in signature_header.split(","):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            elements.setdefault(key.strip(), []).append(value.strip())
        timestamp = (elements.get("t") or [None])[0]
        signatures = elements.get("v1") or []
        if not timestamp or not signatures:
            raise StripeAPIError("Missing Stripe signature elements.")

        try:
            ts = int(timestamp)
        except ValueError as exc:
            raise StripeAPIError("Invalid Stripe signature timestamp.") from exc

        tolerance = int(getattr(settings, "STRIPE_WEBHOOK_TOLERANCE_SECONDS", 300))
        if abs(int(time.time()) - ts) > tolerance:
            raise StripeAPIError("Stripe webhook timestamp outside tolerance.")

        signed_payload = f"{timestamp}.".encode() + payload
        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()
        if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
            raise StripeAPIError("Invalid Stripe webhook signature.")

    def _request_form(
        self,
        *,
        method: str,
        path: str,
        form: dict[str, str] | None,
        idempotency_key: str = "",
    ) -> dict[str, object]:
        data = None if form is None else parse.urlencode(form).encode()
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Accept": "application/json",
            "Stripe-Version": str(self.api_version),
        }
        if data:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        http_request = request.Request(
            url=f"{self.api_base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with open_provider_request(http_request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode())
        except error.HTTPError as exc:
            if exc.code >= 500:
                raise StripeTransientError("Stripe est temporairement indisponible.") from exc
            raise StripeAPIError(self._build_api_error_message(exc)) from exc
        except error.URLError as exc:
            raise StripeTransientError("Stripe est temporairement inaccessible.") from exc

    def _build_api_error_message(self, exc: error.HTTPError) -> str:
        try:
            payload = json.loads(exc.read().decode())
        except Exception:
            return f"Stripe request failed with HTTP {exc.code}."
        err = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(err, dict):
            detail = err.get("message") or err.get("code") or err.get("type")
        else:
            detail = None
        return str(detail or f"Stripe request failed with HTTP {exc.code}.").strip()[:255]
