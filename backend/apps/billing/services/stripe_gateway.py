from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from decimal import Decimal
from urllib import error, parse, request

from django.conf import settings

from apps.billing.services.gateways import (
    CheckoutConfirmResult,
    CheckoutCreateResult,
    PaymentGatewayConfigurationError,
    PaymentGatewayError,
)
from apps.orders.models import Order


class StripeAPIError(PaymentGatewayError):
    pass


class StripeGateway:
    provider = "stripe"

    def __init__(self):
        self.secret_key = settings.STRIPE_SECRET_KEY
        self.api_base_url = settings.STRIPE_API_BASE_URL.rstrip("/")
        self.timeout_seconds = settings.STRIPE_TIMEOUT_SECONDS
        self.webhook_secret = settings.STRIPE_WEBHOOK_SECRET
        if not self.secret_key:
            raise PaymentGatewayConfigurationError(
                "Stripe credentials must be configured via STRIPE_SECRET_KEY."
            )

    def create_checkout(
        self,
        *,
        order: Order,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutCreateResult:
        amount_cents = int((Decimal(order.total_amount) * Decimal("100")).quantize(Decimal("1")))
        if amount_cents <= 0:
            raise StripeAPIError("Montant Stripe invalide.")

        integration_suffix = "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(8))
        form = {
            "mode": "payment",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": str(order.public_id),
            "customer_email": (order.customer.billing_email or "").strip() or None,
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": order.currency.lower(),
            "line_items[0][price_data][unit_amount]": str(amount_cents),
            "line_items[0][price_data][product_data][name]": f"Commande {order.public_id}",
            "metadata[order_public_id]": str(order.public_id),
            "metadata[customer_public_id]": str(order.customer.public_id),
            "integration_identifier": f"prenium-dtf-checkout-{integration_suffix}",
        }
        # Stripe ignore les valeurs None ; on filtre.
        body = {k: v for k, v in form.items() if v is not None}
        payload = self._request_form(method="POST", path="/v1/checkout/sessions", form=body)
        return CheckoutCreateResult(
            provider_payment_id=str(payload.get("id", "")).strip(),
            status=str(payload.get("status", "")).strip() or "open",
            checkout_url=str(payload.get("url", "")).strip(),
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

    def verify_and_parse_webhook(
        self,
        *,
        payload: bytes,
        signature_header: str,
    ) -> dict[str, object]:
        if not self.webhook_secret:
            raise PaymentGatewayConfigurationError(
                "Stripe webhook secret must be configured via STRIPE_WEBHOOK_SECRET."
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
    ) -> dict[str, object]:
        data = None if form is None else parse.urlencode(form).encode()
        http_request = request.Request(
            url=f"{self.api_base_url}{path}",
            data=data,
            headers={
                "Authorization": f"Bearer {self.secret_key}",
                "Accept": "application/json",
                **({"Content-Type": "application/x-www-form-urlencoded"} if data else {}),
            },
            method=method,
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode())
        except error.HTTPError as exc:
            raise StripeAPIError(self._build_api_error_message(exc)) from exc
        except error.URLError as exc:
            raise StripeAPIError("Unable to reach Stripe.") from exc

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
