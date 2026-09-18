from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
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


class PayPalConfigurationError(PaymentGatewayConfigurationError):
    pass


class PayPalAPIError(PaymentGatewayError):
    pass


class PayPalBindingError(PayPalAPIError):
    """Références d'une commande PayPal différentes de la tentative locale."""


class PayPalTransientError(PaymentGatewayTransientError):
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
        from apps.billing.services.gateway_settings import payment_gateway_settings_service

        config = payment_gateway_settings_service.effective()
        self.client_id = config.paypal_client_id
        self.client_secret = config.paypal_client_secret
        self.webhook_id = config.paypal_webhook_id
        self.base_url = settings.PAYPAL_API_BASE_URL.rstrip("/")
        self.timeout_seconds = settings.PAYPAL_TIMEOUT_SECONDS
        if self.base_url not in {
            "https://api-m.sandbox.paypal.com",
            "https://api-m.paypal.com",
        }:
            raise PayPalConfigurationError("URL API PayPal non officielle.")
        if not self.client_id or not self.client_secret:
            raise PayPalConfigurationError(
                "PayPal credentials must be configured in Atelier settings or environment."
            )

    def probe_readiness(self) -> None:
        """Vérifie les identifiants actifs sans créer de commande PayPal."""
        if not self._get_access_token():
            raise PayPalAPIError("PayPal n'a pas délivré de jeton d'accès.")

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
            amount_total_cents=result.amount_total_cents,
            currency=result.currency,
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
                    "custom_id": request_id or unit_reference,
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
        capture_request_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"paypal-capture:{paypal_order_id}")
        )
        try:
            response_payload = self._request_json(
                method="POST",
                url=f"{self.base_url}/v2/checkout/orders/{paypal_order_id}/capture",
                payload={},
                access_token=access_token,
                extra_headers={"PayPal-Request-Id": capture_request_id},
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

    def checkout_state(self, *, provider_payment_id: str) -> str:
        payload = self.get_order(paypal_order_id=provider_payment_id)
        return str(payload.get("status") or "").upper()

    def resume_checkout(self, *, provider_payment_id: str, order: Order, payment_public_id):
        payload = self.get_order(paypal_order_id=provider_payment_id)
        units = payload.get("purchase_units") or []
        unit = units[0] if units and isinstance(units[0], dict) else {}
        amount = unit.get("amount") if isinstance(unit.get("amount"), dict) else {}
        order_reference = str(order.public_id).replace("-", "")[:32]
        try:
            actual_amount = Decimal(str(amount.get("value") or ""))
        except (ArithmeticError, ValueError) as exc:
            raise PayPalAPIError("Montant PayPal indisponible pour la reprise.") from exc
        if (
            str(payload.get("id") or "") != provider_payment_id
            or str(payload.get("status") or "").upper()
            not in {"CREATED", "SAVED", "PAYER_ACTION_REQUIRED"}
            or str(unit.get("reference_id") or "") != order_reference
            or str(unit.get("custom_id") or "") not in {str(payment_public_id), order_reference}
            or actual_amount != Decimal(order.total_amount)
            or str(amount.get("currency_code") or "").upper() != str(order.currency).upper()
        ):
            raise PayPalAPIError("Commande PayPal impossible à reprendre sans rapprochement.")
        approval_url = next(
            (
                str(link.get("href") or "")
                for link in payload.get("links") or []
                if isinstance(link, dict)
                and str(link.get("rel") or "").lower() in {"approve", "payer-action"}
            ),
            "",
        )
        return CheckoutCreateResult(
            provider_payment_id=provider_payment_id,
            status=str(payload.get("status") or ""),
            checkout_url=validate_provider_checkout_url(
                url=approval_url,
                provider="PayPal",
                allowed_hosts={"www.paypal.com", "www.sandbox.paypal.com"},
            ),
            payload=payload,
        )

    def verify_checkout_binding(
        self,
        *,
        provider_payment_id: str,
        payment_public_id,
        order_public_id,
        amount=None,
        currency=None,
        allow_legacy_custom_id: bool = False,
    ) -> dict[str, object]:
        payload = self.get_order(paypal_order_id=provider_payment_id)
        if str(payload.get("id") or "").strip() != provider_payment_id:
            raise PayPalBindingError("Référence de commande PayPal incohérente.")
        units = payload.get("purchase_units") or []
        unit = units[0] if units and isinstance(units[0], dict) else {}
        order_reference = str(order_public_id).replace("-", "")[:32]
        custom_id = str(unit.get("custom_id") or "").strip()
        reference_id = str(unit.get("reference_id") or "").strip()
        accepted_custom_ids = {str(payment_public_id)}
        if allow_legacy_custom_id:
            accepted_custom_ids.add(order_reference)
        if reference_id != order_reference or custom_id not in accepted_custom_ids:
            raise PayPalBindingError("Commande PayPal liée à une autre tentative de paiement.")
        remote_amount = unit.get("amount") if isinstance(unit.get("amount"), dict) else {}
        try:
            actual_amount = Decimal(str(remote_amount.get("value") or ""))
        except (ArithmeticError, ValueError) as exc:
            raise PayPalBindingError("Montant PayPal absent ou invalide.") from exc
        if (
            amount is not None
            and actual_amount != Decimal(amount)
            or currency is not None
            and str(remote_amount.get("currency_code") or "").upper() != str(currency).upper()
        ):
            raise PayPalBindingError("Montant ou devise PayPal incohérent avant capture.")
        return payload

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
    def extract_payment_public_id_from_webhook(event: dict[str, object]) -> str:
        resource = event.get("resource") if isinstance(event.get("resource"), dict) else {}
        custom_id = resource.get("custom_id")
        units = resource.get("purchase_units") or []
        if not custom_id and units and isinstance(units[0], dict):
            custom_id = units[0].get("custom_id")
        cleaned = str(custom_id or "").strip()
        try:
            parsed = uuid.UUID(cleaned)
        except (TypeError, ValueError, AttributeError):
            return ""
        return cleaned if cleaned == str(parsed) else ""

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
        capture_amount = None
        capture_currency = None
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
                capture_amount = (captures[0].get("amount") or {}).get("value")
                capture_currency = (captures[0].get("amount") or {}).get("currency_code")
        order_status = str(response_payload.get("status", "")).strip()
        normalized = (capture_status or order_status).upper()
        if capture_status.upper() == "PENDING":
            normalized = "PENDING"
        elif capture_status.upper() == "COMPLETED" and capture_id:
            normalized = "COMPLETED"
        if normalized == "COMPLETED" and (capture_amount is None or not capture_currency):
            raise PayPalAPIError("PayPal capture amount or currency is missing.")
        try:
            amount_cents = (
                int((Decimal(str(capture_amount)) * Decimal("100")).quantize(Decimal("1")))
                if capture_amount is not None
                else None
            )
        except (ValueError, ArithmeticError) as exc:
            raise PayPalAPIError("PayPal capture amount is invalid.") from exc
        return PayPalCaptureResult(
            capture_id=capture_id,
            status=normalized,
            payload=response_payload,
            amount_total_cents=amount_cents,
            currency=str(capture_currency or "").upper() or None,
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
            with open_provider_request(http_request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode())
        except error.HTTPError as exc:
            if exc.code >= 500:
                raise PayPalTransientError("PayPal est temporairement indisponible.") from exc
            raise PayPalAPIError(self._build_api_error_message(exc)) from exc
        except error.URLError as exc:
            raise PayPalTransientError("PayPal est temporairement inaccessible.") from exc

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
            with open_provider_request(http_request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode())
                return str(payload.get("access_token", "")).strip()
        except error.HTTPError as exc:
            if exc.code >= 500:
                raise PayPalTransientError("PayPal est temporairement indisponible.") from exc
            raise PayPalAPIError(self._build_api_error_message(exc)) from exc
        except error.URLError as exc:
            raise PayPalTransientError("PayPal est temporairement inaccessible.") from exc

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
