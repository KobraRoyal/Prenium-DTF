from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from decimal import Decimal
from urllib import error, parse, request

from django.conf import settings

from apps.billing.services.gateways import (
    CheckoutConfirmResult,
    CheckoutCreateResult,
    PaymentGatewayConfigurationError,
    PaymentGatewayError,
    validate_provider_checkout_url,
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


class PayPalGateway:
    provider = "paypal"

    def __init__(self):
        from apps.billing.services.gateway_settings import payment_gateway_settings_service

        config = payment_gateway_settings_service.effective()
        self.client_id = config.paypal_client_id
        self.client_secret = config.paypal_client_secret
        self.webhook_id = config.paypal_webhook_id
        self.base_url = settings.PAYPAL_API_BASE_URL.rstrip("/")
        self.timeout_seconds = settings.PAYPAL_TIMEOUT_SECONDS
        if not self.client_id or not self.client_secret:
            raise PayPalConfigurationError(
                "PayPal credentials must be configured in Atelier settings or environment."
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
            request_id=idempotency_key,
        )
        return CheckoutCreateResult(
            provider_payment_id=result.paypal_order_id,
            status=result.status,
            checkout_url=result.approval_url,
            payload=result.payload,
        )

    def confirm_checkout(self, *, provider_payment_id: str) -> CheckoutConfirmResult:
        result = self.capture_order(paypal_order_id=provider_payment_id)
        return CheckoutConfirmResult(
            provider_payment_id=provider_payment_id,
            provider_capture_id=result.capture_id,
            status=result.status,
            payload=result.payload,
        )

    def create_order(
        self,
        *,
        order: Order,
        return_url: str = "",
        cancel_url: str = "",
        request_id: str = "",
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
            extra_headers={"PayPal-Request-Id": request_id} if request_id else None,
        )
        approval_url = ""
        for link in response_payload.get("links", []):
            if str(link.get("rel", "")).strip().lower() == "approve":
                approval_url = str(link.get("href", "")).strip()
                break
        return PayPalCreateOrderResult(
            paypal_order_id=str(response_payload.get("id", "")).strip(),
            status=str(response_payload.get("status", "")).strip(),
            approval_url=validate_provider_checkout_url(
                url=approval_url,
                provider="PayPal",
                allowed_hosts={"www.paypal.com", "www.sandbox.paypal.com"},
            ),
            payload=response_payload,
        )

    def capture_order(self, *, paypal_order_id: str) -> PayPalCaptureResult:
        access_token = self._get_access_token()
        try:
            response_payload = self._request_json(
                method="POST",
                url=f"{self.base_url}/v2/checkout/orders/{paypal_order_id}/capture",
                payload={},
                access_token=access_token,
            )
        except PayPalAPIError as exc:
            if not self._is_already_captured(exc):
                raise
            response_payload = self.get_order(
                paypal_order_id=paypal_order_id,
                access_token=access_token,
            )
        return self._capture_result_from_order_payload(response_payload=response_payload)

    def get_order(
        self, *, paypal_order_id: str, access_token: str | None = None
    ) -> dict[str, object]:
        token = access_token or self._get_access_token()
        return self._request_json(
            method="GET",
            url=f"{self.base_url}/v2/checkout/orders/{paypal_order_id}",
            payload=None,
            access_token=token,
        )

    def verify_and_parse_webhook(
        self,
        *,
        payload: bytes,
        headers: dict[str, str],
    ) -> dict[str, object]:
        webhook_id = self.webhook_id
        if not webhook_id:
            raise PayPalConfigurationError(
                "PayPal webhook id must be configured in Atelier settings or PAYPAL_WEBHOOK_ID."
            )
        try:
            event = json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise PayPalAPIError("Invalid PayPal webhook payload.") from exc
        if not isinstance(event, dict):
            raise PayPalAPIError("Invalid PayPal webhook payload.")

        verification_payload = {
            "auth_algo": headers.get("paypal-auth-algo") or headers.get("PAYPAL-AUTH-ALGO") or "",
            "cert_url": headers.get("paypal-cert-url") or headers.get("PAYPAL-CERT-URL") or "",
            "transmission_id": headers.get("paypal-transmission-id")
            or headers.get("PAYPAL-TRANSMISSION-ID")
            or "",
            "transmission_sig": headers.get("paypal-transmission-sig")
            or headers.get("PAYPAL-TRANSMISSION-SIG")
            or "",
            "transmission_time": headers.get("paypal-transmission-time")
            or headers.get("PAYPAL-TRANSMISSION-TIME")
            or "",
            "webhook_id": webhook_id,
            "webhook_event": event,
        }
        if not all(
            verification_payload[key]
            for key in (
                "auth_algo",
                "cert_url",
                "transmission_id",
                "transmission_sig",
                "transmission_time",
            )
        ):
            raise PayPalAPIError("Missing PayPal webhook signature headers.")

        access_token = self._get_access_token()
        result = self._request_json(
            method="POST",
            url=f"{self.base_url}/v1/notifications/verify-webhook-signature",
            payload=verification_payload,
            access_token=access_token,
        )
        if str(result.get("verification_status", "")).strip().upper() != "SUCCESS":
            raise PayPalAPIError("Invalid PayPal webhook signature.")
        return event

    @staticmethod
    def extract_order_id_from_webhook(event: dict[str, object]) -> str:
        resource = event.get("resource") if isinstance(event.get("resource"), dict) else {}
        event_type = str(event.get("event_type", "")).strip().upper()
        if event_type == "CHECKOUT.ORDER.APPROVED":
            return str(resource.get("id", "")).strip()
        supplementary = resource.get("supplementary_data") if isinstance(resource, dict) else {}
        related = (
            supplementary.get("related_ids") if isinstance(supplementary, dict) else {}
        ) or {}
        order_id = str(related.get("order_id", "")).strip() if isinstance(related, dict) else ""
        if order_id:
            return order_id
        return str(resource.get("id", "")).strip()

    @staticmethod
    def _is_already_captured(exc: PayPalAPIError) -> bool:
        message = str(exc).upper()
        return "ORDER_ALREADY_CAPTURED" in message or "ALREADY_CAPTURED" in message

    @staticmethod
    def _capture_result_from_order_payload(
        *,
        response_payload: dict[str, object],
    ) -> PayPalCaptureResult:
        capture_id = ""
        capture_status = ""
        purchase_units = response_payload.get("purchase_units") or []
        if purchase_units:
            captures = (
                purchase_units[0].get("payments", {}).get("captures", [])
                if isinstance(purchase_units[0], dict)
                else []
            )
            if captures and isinstance(captures[0], dict):
                capture_id = str(captures[0].get("id", "")).strip()
                capture_status = str(captures[0].get("status", "")).strip()
        order_status = str(response_payload.get("status", "")).strip()
        normalized = (capture_status or order_status).upper()
        if capture_status.upper() == "PENDING":
            normalized = "PENDING"
        elif capture_status.upper() == "COMPLETED" or (
            order_status.upper() == "COMPLETED" and not capture_status
        ):
            normalized = "COMPLETED"
        return PayPalCaptureResult(
            capture_id=capture_id,
            status=normalized,
            payload=response_payload,
        )

    def _request_json(
        self,
        *,
        method: str,
        url: str,
        payload: dict[str, object] | None,
        access_token: str,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        data = None if payload is None else json.dumps(payload).encode()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        if extra_headers:
            headers.update(extra_headers)
        http_request = request.Request(
            url=url,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode())
        except error.HTTPError as exc:
            raise PayPalAPIError(self._build_api_error_message(exc)) from exc
        except error.URLError as exc:
            raise PayPalAPIError("Unable to reach PayPal.") from exc

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
        except error.URLError as exc:
            raise PayPalAPIError("Unable to reach PayPal.") from exc

    def _build_api_error_message(self, exc: error.HTTPError) -> str:
        try:
            payload = json.loads(exc.read().decode())
        except Exception:
            return f"PayPal request failed with HTTP {exc.code}."
        issues = []
        details = payload.get("details") if isinstance(payload, dict) else None
        if isinstance(details, list):
            for item in details:
                if isinstance(item, dict) and item.get("issue"):
                    issues.append(str(item.get("issue")))
        detail = (
            payload.get("name")
            or payload.get("message")
            or payload.get("error_description")
            or payload.get("error")
            or f"PayPal request failed with HTTP {exc.code}."
        )
        if issues:
            detail = f"{detail} {' '.join(issues)}"
        return str(detail).strip()[:255]
