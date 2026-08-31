from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from urllib import error, parse, request

from django.conf import settings

from apps.billing.services.gateways import (
    CheckoutConfirmResult,
    CheckoutCreateResult,
    PaymentGatewayConfigurationError,
    PaymentGatewayError,
)
from apps.orders.models import Order


class PayPalConfigurationError(PaymentGatewayConfigurationError):
    pass


class PayPalAPIError(PaymentGatewayError):
    pass


@dataclass(frozen=True)
class PayPalCreateOrderResult:
    paypal_order_id: str
    status: str
    approval_url: str
    payload: dict[str, object]


@dataclass(frozen=True)
class PayPalCaptureResult:
    capture_id: str
    status: str
    payload: dict[str, object]
    amount_total_cents: int | None = None
    currency: str | None = None


class PayPalGateway:
    provider = "paypal"

    def __init__(self):
        self.client_id = settings.PAYPAL_CLIENT_ID
        self.client_secret = settings.PAYPAL_CLIENT_SECRET
        self.base_url = settings.PAYPAL_API_BASE_URL.rstrip("/")
        self.timeout_seconds = settings.PAYPAL_TIMEOUT_SECONDS
        if not self.client_id or not self.client_secret:
            raise PayPalConfigurationError(
                "PayPal credentials must be configured via environment variables."
            )

    def create_checkout(
        self,
        *,
        order: Order,
        success_url: str,
        cancel_url: str,
        idempotency_key: str = "",
    ) -> CheckoutCreateResult:
        result = self.create_order(
            order=order,
            return_url=success_url,
            cancel_url=cancel_url,
            idempotency_key=idempotency_key,
        )
        return CheckoutCreateResult(
            provider_payment_id=result.paypal_order_id,
            status=result.status,
            checkout_url=result.approval_url,
            payload=result.payload,
        )

    def confirm_checkout(
        self,
        *,
        provider_payment_id: str,
        idempotency_key: str = "",
    ) -> CheckoutConfirmResult:
        result = self.capture_order(
            paypal_order_id=provider_payment_id,
            idempotency_key=idempotency_key,
        )
        return CheckoutConfirmResult(
            provider_payment_id=provider_payment_id,
            provider_capture_id=result.capture_id,
            status=result.status,
            payload=result.payload,
            amount_total_cents=result.amount_total_cents,
            currency=result.currency,
        )

    def create_order(
        self,
        *,
        order: Order,
        return_url: str = "",
        cancel_url: str = "",
        idempotency_key: str = "",
    ) -> PayPalCreateOrderResult:
        access_token = self._get_access_token()
        application_context = {
            "brand_name": "Prenium DTF",
            "user_action": "PAY_NOW",
        }
        if return_url:
            application_context["return_url"] = self._sanitize_redirect_url(return_url)
        if cancel_url:
            application_context["cancel_url"] = self._sanitize_redirect_url(cancel_url)
        # PayPal limite reference_id / custom_id ; UUID complet + tirets OK, mais
        # on reste sur une ref courte stable pour les rapports.
        unit_reference = str(order.public_id).replace("-", "")[:32]
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "custom_id": unit_reference,
                    "reference_id": unit_reference,
                    "description": f"Commande {order.short_ref}",
                    "amount": {
                        "currency_code": str(order.currency or "EUR").upper(),
                        "value": f"{Decimal(order.total_amount):.2f}",
                    },
                }
            ],
            "application_context": application_context,
        }
        response_payload = self._request_json(
            method="POST",
            url=f"{self.base_url}/v2/checkout/orders",
            payload=payload,
            access_token=access_token,
            idempotency_key=idempotency_key,
        )
        approval_url = ""
        for link in response_payload.get("links", []):
            if str(link.get("rel", "")).strip().lower() == "approve":
                approval_url = str(link.get("href", "")).strip()
                break
        return PayPalCreateOrderResult(
            paypal_order_id=str(response_payload.get("id", "")).strip(),
            status=str(response_payload.get("status", "")).strip(),
            approval_url=approval_url,
            payload=response_payload,
        )

    def capture_order(
        self,
        *,
        paypal_order_id: str,
        idempotency_key: str = "",
    ) -> PayPalCaptureResult:
        access_token = self._get_access_token()
        response_payload = self._request_json(
            method="POST",
            url=f"{self.base_url}/v2/checkout/orders/{paypal_order_id}/capture",
            payload={},
            access_token=access_token,
            idempotency_key=idempotency_key,
        )
        capture_id, amount_total_cents, currency = self._capture_summary(response_payload)
        return PayPalCaptureResult(
            capture_id=capture_id,
            status=str(response_payload.get("status", "")).strip(),
            payload=response_payload,
            amount_total_cents=amount_total_cents,
            currency=currency,
        )

    @staticmethod
    def _capture_summary(payload: dict[str, object]) -> tuple[str, int | None, str | None]:
        capture_id = ""
        total = Decimal("0")
        currencies: set[str] = set()
        amount_count = 0

        for purchase_unit in payload.get("purchase_units") or []:
            if not isinstance(purchase_unit, dict):
                continue
            payments = purchase_unit.get("payments") or {}
            captures = (payments.get("captures") or []) if isinstance(payments, dict) else []
            for capture in captures:
                if not isinstance(capture, dict):
                    continue
                if not capture_id:
                    capture_id = str(capture.get("id", "")).strip()
                amount = capture.get("amount") or {}
                if not isinstance(amount, dict):
                    continue
                currency = str(amount.get("currency_code", "")).strip().upper()
                try:
                    value = Decimal(str(amount.get("value", "")).strip())
                except (InvalidOperation, ValueError):
                    continue
                if not currency:
                    continue
                currencies.add(currency)
                total += value
                amount_count += 1

        if amount_count == 0 or len(currencies) != 1:
            return capture_id, None, None
        amount_total_cents = int(
            (total * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        return capture_id, amount_total_cents, next(iter(currencies))

    @staticmethod
    def _sanitize_redirect_url(url: str) -> str:
        """Retire les placeholders Stripe Checkout (invalides pour PayPal)."""
        cleaned = (
            str(url or "")
            .replace("{{CHECKOUT_SESSION_ID}}", "")
            .replace("%7B%7BCHECKOUT_SESSION_ID%7D%7D", "")
        )
        # Nettoie session_id vide laissé par le placeholder.
        cleaned = cleaned.replace("session_id=&", "").replace("?session_id=", "?")
        if cleaned.endswith("&session_id="):
            cleaned = cleaned[: -len("&session_id=")]
        if cleaned.endswith("?session_id="):
            cleaned = cleaned[: -len("?session_id=")]
        cleaned = cleaned.replace("&&", "&")
        if cleaned.endswith("&"):
            cleaned = cleaned[:-1]
        if cleaned.endswith("?"):
            cleaned = cleaned[:-1]
        return cleaned

    def _get_access_token(self) -> str:
        encoded_credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode("ascii")
        http_request = request.Request(
            url=f"{self.base_url}/v1/oauth2/token",
            data=parse.urlencode({"grant_type": "client_credentials"}).encode(),
            headers={
                "Authorization": f"Basic {encoded_credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode())
                return str(payload.get("access_token", "")).strip()
        except error.HTTPError as exc:
            raise PayPalAPIError(self._build_api_error_message(exc)) from exc
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise PayPalAPIError("Unable to reach PayPal.") from exc

    def _request_json(
        self,
        *,
        method: str,
        url: str,
        payload: dict[str, object],
        access_token: str,
        idempotency_key: str = "",
    ) -> dict[str, object]:
        if idempotency_key and len(idempotency_key) > 38:
            raise PayPalAPIError("PayPal idempotency key exceeds 38 characters.")
        http_request = request.Request(
            url=url,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                **({"PayPal-Request-Id": idempotency_key} if idempotency_key else {}),
            },
            method=method,
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode())
        except error.HTTPError as exc:
            raise PayPalAPIError(self._build_api_error_message(exc)) from exc
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise PayPalAPIError("Unable to reach PayPal.") from exc

    def _build_api_error_message(self, exc: error.HTTPError) -> str:
        try:
            payload = json.loads(exc.read().decode())
        except Exception:
            return f"PayPal request failed with HTTP {exc.code}."
        detail = (
            payload.get("message")
            or payload.get("error_description")
            or payload.get("error")
            or f"PayPal request failed with HTTP {exc.code}."
        )
        return str(detail).strip()[:255]
