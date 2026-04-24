from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from decimal import Decimal
from urllib import error, parse, request

from django.conf import settings

from apps.orders.models import Order


class PayPalConfigurationError(Exception):
    pass


class PayPalAPIError(Exception):
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
    def __init__(self):
        self.client_id = settings.PAYPAL_CLIENT_ID
        self.client_secret = settings.PAYPAL_CLIENT_SECRET
        self.base_url = settings.PAYPAL_API_BASE_URL.rstrip("/")
        self.timeout_seconds = settings.PAYPAL_TIMEOUT_SECONDS
        if not self.client_id or not self.client_secret:
            raise PayPalConfigurationError(
                "PayPal credentials must be configured via environment variables."
            )

    def create_order(self, *, order: Order) -> PayPalCreateOrderResult:
        access_token = self._get_access_token()
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "custom_id": str(order.public_id),
                    "reference_id": str(order.public_id),
                    "amount": {
                        "currency_code": order.currency,
                        "value": f"{Decimal(order.total_amount):.2f}",
                    },
                }
            ],
            "application_context": {
                "brand_name": "Prenium DTF",
                "user_action": "PAY_NOW",
            },
        }
        response_payload = self._request_json(
            method="POST",
            url=f"{self.base_url}/v2/checkout/orders",
            payload=payload,
            access_token=access_token,
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

    def capture_order(self, *, paypal_order_id: str) -> PayPalCaptureResult:
        access_token = self._get_access_token()
        response_payload = self._request_json(
            method="POST",
            url=f"{self.base_url}/v2/checkout/orders/{paypal_order_id}/capture",
            payload={},
            access_token=access_token,
        )
        capture_id = ""
        purchase_units = response_payload.get("purchase_units") or []
        if purchase_units:
            captures = (
                purchase_units[0].get("payments", {}).get("captures", [])
                if isinstance(purchase_units[0], dict)
                else []
            )
            if captures:
                capture_id = str(captures[0].get("id", "")).strip()
        return PayPalCaptureResult(
            capture_id=capture_id,
            status=str(response_payload.get("status", "")).strip(),
            payload=response_payload,
        )

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

    def _request_json(
        self,
        *,
        method: str,
        url: str,
        payload: dict[str, object],
        access_token: str,
    ) -> dict[str, object]:
        http_request = request.Request(
            url=url,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method=method,
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode())
        except error.HTTPError as exc:
            raise PayPalAPIError(self._build_api_error_message(exc)) from exc
        except error.URLError as exc:
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

