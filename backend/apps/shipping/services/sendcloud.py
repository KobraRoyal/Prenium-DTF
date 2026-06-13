from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from urllib import error, request

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.orders.models import Order
from apps.production.models import ProductionJob
from apps.production.services.workflow import ProductionWorkflowService
from apps.shipping.models import Shipment


class SendcloudConfigurationError(Exception):
    pass


class SendcloudAPIError(Exception):
    pass


@dataclass(frozen=True)
class SendcloudShipmentResult:
    shipment_id: str
    parcel_id: str
    status_code: str
    status_message: str
    tracking_number: str
    tracking_url: str
    label_content: bytes
    label_mime_type: str


class SendcloudGateway:
    def __init__(self):
        self.public_key = settings.SENDCLOUD_PUBLIC_KEY
        self.secret_key = settings.SENDCLOUD_SECRET_KEY
        self.base_url = settings.SENDCLOUD_API_BASE_URL.rstrip("/")
        self.timeout_seconds = settings.SENDCLOUD_TIMEOUT_SECONDS
        self.sender_address = self._build_sender_address()

        if not self.public_key or not self.secret_key:
            raise SendcloudConfigurationError(
                "Sendcloud credentials must be configured via environment variables."
            )

    def create_shipment(self, *, payload: dict[str, object]) -> SendcloudShipmentResult:
        response_payload = self._request_json(
            method="POST",
            url=f"{self.base_url}/shipments/announce",
            payload=payload,
        )
        shipment_data = response_payload.get("data") or {}
        parcels = shipment_data.get("parcels") or []
        if not parcels:
            raise SendcloudAPIError("Sendcloud response did not include a parcel.")

        parcel = parcels[0]
        status = parcel.get("status") or {}
        label_document_link = self._extract_label_link(parcel)
        if not label_document_link:
            raise SendcloudAPIError("Sendcloud response did not include a label document.")

        label_mime_type = str(payload.get("label_details", {}).get("mime_type", "application/pdf"))
        label_content = self._download_binary(label_document_link, accept=label_mime_type)

        return SendcloudShipmentResult(
            shipment_id=str(shipment_data.get("id", "")).strip(),
            parcel_id=str(parcel.get("id", "")).strip(),
            status_code=str(status.get("code", "")).strip(),
            status_message=str(status.get("message", "")).strip(),
            tracking_number=str(parcel.get("tracking_number", "")).strip(),
            tracking_url=str(parcel.get("tracking_url", "")).strip(),
            label_content=label_content,
            label_mime_type=label_mime_type,
        )

    def build_request_payload(
        self,
        *,
        order: Order,
        shipment_request: dict[str, object],
    ) -> dict[str, object]:
        ship_with_properties = {
            "shipping_option_code": shipment_request["shipping_option_code"],
        }
        contract_id = shipment_request.get("contract_id")
        if contract_id is not None:
            ship_with_properties["contract_id"] = contract_id

        return {
            "label_details": shipment_request["label_details"],
            "to_address": shipment_request["recipient"],
            "from_address": self.sender_address,
            "ship_with": {
                "type": "shipping_option_code",
                "properties": ship_with_properties,
            },
            "order_number": str(order.public_id),
            "reference": str(order.public_id),
            "external_reference_id": str(order.public_id),
            "total_order_price": {
                "currency": order.currency,
                "value": f"{order.total_amount:.2f}",
            },
            "parcels": [shipment_request["parcel"]],
        }

    def _build_sender_address(self) -> dict[str, str]:
        sender = {
            "name": settings.SENDCLOUD_SENDER_NAME,
            "company_name": settings.SENDCLOUD_SENDER_COMPANY_NAME,
            "address_line_1": settings.SENDCLOUD_SENDER_ADDRESS_LINE_1,
            "address_line_2": settings.SENDCLOUD_SENDER_ADDRESS_LINE_2,
            "house_number": settings.SENDCLOUD_SENDER_HOUSE_NUMBER,
            "postal_code": settings.SENDCLOUD_SENDER_POSTAL_CODE,
            "city": settings.SENDCLOUD_SENDER_CITY,
            "country_code": settings.SENDCLOUD_SENDER_COUNTRY_CODE,
            "email": settings.SENDCLOUD_SENDER_EMAIL,
            "phone_number": settings.SENDCLOUD_SENDER_PHONE_NUMBER,
        }
        required_fields = (
            "name",
            "address_line_1",
            "house_number",
            "postal_code",
            "city",
            "country_code",
            "email",
        )
        missing_fields = [field_name for field_name in required_fields if not sender[field_name]]
        if missing_fields:
            raise SendcloudConfigurationError(
                "Missing Sendcloud sender configuration: " + ", ".join(sorted(missing_fields))
            )
        return sender

    def _extract_label_link(self, parcel: dict[str, object]) -> str:
        for document in parcel.get("documents") or []:
            if str(document.get("type", "")).strip().lower() == "label":
                return str(document.get("link", "")).strip()
        return ""

    def _auth_header(self) -> str:
        raw_value = f"{self.public_key}:{self.secret_key}".encode()
        return f"Basic {base64.b64encode(raw_value).decode('ascii')}"

    def _request_json(
        self,
        *,
        method: str,
        url: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        body = None if payload is None else json.dumps(payload).encode()
        headers = {
            "Authorization": self._auth_header(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        http_request = request.Request(url, data=body, headers=headers, method=method)
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode())
        except error.HTTPError as exc:
            raise SendcloudAPIError(self._build_api_error_message(exc)) from exc
        except error.URLError as exc:
            raise SendcloudAPIError("Unable to reach Sendcloud.") from exc

    def _download_binary(self, url: str, *, accept: str) -> bytes:
        http_request = request.Request(
            url,
            headers={
                "Authorization": self._auth_header(),
                "Accept": accept,
            },
            method="GET",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                return response.read()
        except error.HTTPError as exc:
            raise SendcloudAPIError(self._build_api_error_message(exc)) from exc
        except error.URLError as exc:
            raise SendcloudAPIError("Unable to download Sendcloud label.") from exc

    def _build_api_error_message(self, exc: error.HTTPError) -> str:
        try:
            payload = json.loads(exc.read().decode())
        except Exception:
            return f"Sendcloud request failed with HTTP {exc.code}."

        detail = (
            payload.get("error", {}).get("message")
            or payload.get("message")
            or payload.get("detail")
            or f"Sendcloud request failed with HTTP {exc.code}."
        )
        return str(detail).strip()[:255]

    def fetch_parcel(self, *, parcel_id: str) -> dict[str, object]:
        parcel_id = str(parcel_id).strip()
        if not parcel_id:
            raise SendcloudAPIError("Sendcloud parcel id is required.")
        url = f"{self.base_url}/parcels/{parcel_id}"
        response_payload = self._request_json(method="GET", url=url, payload=None)
        parcel = response_payload.get("parcel")
        if not isinstance(parcel, dict):
            data = response_payload.get("data")
            parcel = data if isinstance(data, dict) else {}
        if not parcel:
            raise SendcloudAPIError("Sendcloud parcel payload is empty.")
        return parcel


class ShipmentService:
    def __init__(self, *, gateway: SendcloudGateway | None = None):
        self.gateway = gateway
        self.production_workflow_service = ProductionWorkflowService()

    def get_staff_shipment(self, *, order_public_id, actor, source: str):
        order = self._get_staff_order(order_public_id=order_public_id)
        if order is None:
            return None, None

        shipment = (
            Shipment.objects.select_related("order", "order__customer", "created_by", "updated_by")
            .filter(order=order)
            .first()
        )
        if shipment is None:
            return order, None

        self.record_view_event(shipment=shipment, actor=actor, source=source)
        return order, shipment

    def create_shipment(
        self,
        *,
        order_public_id,
        actor,
        source: str,
        payload: dict[str, object],
    ):
        order = self._get_staff_order(order_public_id=order_public_id)
        if order is None:
            return None, None

        production_job = self.production_workflow_service.get_or_create_for_order(order=order)
        if production_job.status != ProductionJob.Status.READY_TO_SHIP:
            raise ValidationError("Shipment can only be created when production is ready to ship.")

        shipment_request = self._normalize_create_payload(payload)
        gateway = self._get_gateway()

        with transaction.atomic():
            shipment, _created = Shipment.objects.select_for_update().get_or_create(
                order=order,
                defaults={
                    "created_by": actor if getattr(actor, "is_authenticated", False) else None,
                    "updated_by": actor if getattr(actor, "is_authenticated", False) else None,
                    "status": Shipment.Status.PENDING,
                    "shipping_option_code": shipment_request["shipping_option_code"],
                    "contract_id": shipment_request["contract_id"],
                    "source": source,
                    "request_snapshot": shipment_request,
                },
            )

            if shipment.status == Shipment.Status.CREATED and shipment.sendcloud_parcel_id:
                raise ValidationError("A shipment already exists for this order.")

            shipment.updated_by = actor if getattr(actor, "is_authenticated", False) else None
            shipment.status = Shipment.Status.PENDING
            shipment.shipping_option_code = shipment_request["shipping_option_code"]
            shipment.contract_id = shipment_request["contract_id"]
            shipment.source = source
            shipment.request_snapshot = shipment_request
            shipment.last_error_message = ""
            shipment.save(
                update_fields=[
                    "updated_by",
                    "status",
                    "shipping_option_code",
                    "contract_id",
                    "source",
                    "request_snapshot",
                    "last_error_message",
                    "updated_at",
                ]
            )

        sendcloud_payload = gateway.build_request_payload(
            order=order,
            shipment_request=shipment_request,
        )

        try:
            result = gateway.create_shipment(payload=sendcloud_payload)
        except (SendcloudAPIError, SendcloudConfigurationError) as exc:
            self._mark_failed_shipment(
                shipment=shipment,
                actor=actor,
                source=source,
                message=self._sanitize_error_message(str(exc)),
            )

        with transaction.atomic():
            shipment = Shipment.objects.select_for_update().get(pk=shipment.pk)
            shipment.updated_by = actor if getattr(actor, "is_authenticated", False) else None
            shipment.status = Shipment.Status.CREATED
            shipment.sendcloud_shipment_id = result.shipment_id
            shipment.sendcloud_parcel_id = result.parcel_id
            shipment.sendcloud_status_code = result.status_code
            shipment.sendcloud_status_message = result.status_message[:255]
            shipment.tracking_number = result.tracking_number
            shipment.tracking_url = result.tracking_url
            shipment.label_filename = self._build_label_filename(shipment=shipment)
            shipment.label_mime_type = result.label_mime_type
            shipment.label_retrieved_at = timezone.now()
            shipment.last_api_sync_at = shipment.label_retrieved_at
            shipment.last_error_message = ""
            shipment.label_file.save(
                shipment.label_filename,
                ContentFile(result.label_content),
                save=False,
            )
            shipment.save()

        record_event(
            action="shipping.shipment_created",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=shipment,
            metadata={
                "order_public_id": str(order.public_id),
                "customer_public_id": str(order.customer.public_id),
                "shipment_public_id": str(shipment.public_id),
                "sendcloud_shipment_id": shipment.sendcloud_shipment_id,
                "sendcloud_parcel_id": shipment.sendcloud_parcel_id,
                "tracking_number": shipment.tracking_number,
                "has_label": bool(shipment.label_file),
                "source": source,
            },
        )
        return order, shipment

    def record_view_event(self, *, shipment: Shipment, actor, source: str) -> None:
        record_event(
            action="shipping.shipment_viewed",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=shipment,
            metadata={
                "order_public_id": str(shipment.order.public_id),
                "customer_public_id": str(shipment.order.customer.public_id),
                "shipment_public_id": str(shipment.public_id),
                "status": shipment.status,
                "sendcloud_status_code": shipment.sendcloud_status_code,
                "source": source,
            },
        )

    def sync_shipment_tracking_from_sendcloud(
        self,
        *,
        order_public_id,
        actor,
        source: str,
    ):
        order = self._get_staff_order(order_public_id=order_public_id)
        if order is None:
            return None, None

        shipment = (
            Shipment.objects.select_related("order", "order__customer").filter(order=order).first()
        )
        if shipment is None:
            raise ValidationError("Aucune expédition pour cette commande.")
        if shipment.status != Shipment.Status.CREATED:
            raise ValidationError(
                "La synchronisation du suivi n'est disponible que pour une expédition créée.",
            )
        if not str(shipment.sendcloud_parcel_id or "").strip():
            raise ValidationError("Identifiant colis Sendcloud manquant.")

        gateway = self._get_gateway()
        try:
            parcel_payload = gateway.fetch_parcel(parcel_id=shipment.sendcloud_parcel_id)
        except (SendcloudAPIError, SendcloudConfigurationError) as exc:
            raise ValidationError(self._sanitize_error_message(str(exc))) from exc

        fields = self._extract_tracking_fields_from_parcel(parcel_payload)
        now = timezone.now()
        with transaction.atomic():
            shipment = Shipment.objects.select_for_update().get(pk=shipment.pk)
            shipment.sendcloud_status_code = fields["sendcloud_status_code"]
            shipment.sendcloud_status_message = fields["sendcloud_status_message"]
            if fields["tracking_number"]:
                shipment.tracking_number = fields["tracking_number"]
            if fields["tracking_url"]:
                shipment.tracking_url = fields["tracking_url"]
            shipment.last_api_sync_at = now
            shipment.updated_by = actor if getattr(actor, "is_authenticated", False) else None
            shipment.save(
                update_fields=[
                    "sendcloud_status_code",
                    "sendcloud_status_message",
                    "tracking_number",
                    "tracking_url",
                    "last_api_sync_at",
                    "updated_by",
                    "updated_at",
                ]
            )

        record_event(
            action="shipping.shipment_tracking_synced",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=shipment,
            metadata={
                "order_public_id": str(order.public_id),
                "customer_public_id": str(order.customer.public_id),
                "shipment_public_id": str(shipment.public_id),
                "sendcloud_status_code": shipment.sendcloud_status_code,
                "source": source,
            },
        )
        return order, shipment

    def get_customer_shipment_snapshot(self, *, customer, order_public_id):
        order = (
            Order.objects.filter(customer=customer, public_id=order_public_id)
            .select_related("customer")
            .first()
        )
        if order is None:
            return None
        shipment = (
            Shipment.objects.filter(order=order)
            .only(
                "public_id",
                "status",
                "tracking_number",
                "tracking_url",
                "sendcloud_status_code",
                "sendcloud_status_message",
                "last_api_sync_at",
                "updated_at",
            )
            .first()
        )
        if shipment is None:
            return None
        sync_ts = shipment.last_api_sync_at or shipment.updated_at
        return {
            "public_id": str(shipment.public_id),
            "status": shipment.status,
            "tracking_number": shipment.tracking_number,
            "tracking_url": shipment.tracking_url,
            "carrier_status": {
                "code": shipment.sendcloud_status_code,
                "message": shipment.sendcloud_status_message,
            },
            "last_sync_at": sync_ts.isoformat() if sync_ts else None,
        }

    def sync_stale_shipments_tracking(self, *, limit: int = 50) -> int:
        """Synchronise les expéditions créées dont le suivi n'a pas été rafraîchi récemment."""
        from datetime import timedelta

        stale_before = timezone.now() - timedelta(minutes=45)
        queryset = (
            Shipment.objects.filter(status=Shipment.Status.CREATED)
            .exclude(sendcloud_parcel_id="")
            .filter(Q(last_api_sync_at__isnull=True) | Q(last_api_sync_at__lt=stale_before))
            .order_by("last_api_sync_at")[:limit]
        )
        updated = 0
        for shipment in queryset:
            try:
                self.sync_shipment_tracking_from_sendcloud(
                    order_public_id=shipment.order.public_id,
                    actor=None,
                    source="celery_periodic",
                )
                updated += 1
            except ValidationError:
                continue
            except (SendcloudAPIError, SendcloudConfigurationError):
                continue
        return updated

    def _extract_tracking_fields_from_parcel(self, parcel: dict[str, object]) -> dict[str, str]:
        status = parcel.get("status")
        if isinstance(status, dict):
            code = str(status.get("code") or status.get("id") or status.get("name") or "").strip()
            message = str(status.get("message") or status.get("label") or "").strip()
        elif status is not None:
            code = str(status).strip()
            message = ""
        else:
            code = ""
            message = ""
        return {
            "sendcloud_status_code": code[:64],
            "sendcloud_status_message": message[:255],
            "tracking_number": str(parcel.get("tracking_number", "")).strip()[:255],
            "tracking_url": str(parcel.get("tracking_url", "")).strip()[:2048],
        }

    def _mark_failed_shipment(self, *, shipment: Shipment, actor, source: str, message: str):
        with transaction.atomic():
            shipment = Shipment.objects.select_for_update().get(pk=shipment.pk)
            shipment.updated_by = actor if getattr(actor, "is_authenticated", False) else None
            shipment.status = Shipment.Status.FAILED
            shipment.last_error_message = message
            shipment.last_api_sync_at = timezone.now()
            shipment.save(
                update_fields=[
                    "updated_by",
                    "status",
                    "last_error_message",
                    "last_api_sync_at",
                    "updated_at",
                ]
            )

        record_event(
            action="shipping.shipment_creation_failed",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=shipment,
            status=AuditLogEntry.Status.FAILURE,
            message=message,
            metadata={
                "order_public_id": str(shipment.order.public_id),
                "customer_public_id": str(shipment.order.customer.public_id),
                "shipment_public_id": str(shipment.public_id),
                "shipping_option_code": shipment.shipping_option_code,
                "source": source,
            },
        )
        raise ValidationError(message)

    def _normalize_create_payload(self, payload: dict[str, object]) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValidationError("Shipment payload must be an object.")

        shipping_option_code = str(payload.get("shipping_option_code", "")).strip()
        if not shipping_option_code:
            raise ValidationError("shipping_option_code is required.")

        contract_id = payload.get("contract_id")
        if contract_id in ("", None):
            normalized_contract_id = None
        else:
            try:
                normalized_contract_id = int(contract_id)
            except (TypeError, ValueError) as exc:
                raise ValidationError("contract_id must be an integer.") from exc
            if normalized_contract_id <= 0:
                raise ValidationError("contract_id must be a positive integer.")

        recipient = self._normalize_address(payload.get("recipient"), label="recipient")
        parcel = self._normalize_parcel(payload.get("parcel"))
        label_details = self._normalize_label_details(payload.get("label_details"))

        return {
            "shipping_option_code": shipping_option_code,
            "contract_id": normalized_contract_id,
            "recipient": recipient,
            "parcel": parcel,
            "label_details": label_details,
        }

    def _normalize_address(self, value, *, label: str) -> dict[str, str]:
        if not isinstance(value, dict):
            raise ValidationError(f"{label} must be an object.")

        address = {
            "name": str(value.get("name", "")).strip(),
            "company_name": str(value.get("company_name", "")).strip(),
            "address_line_1": str(value.get("address_line_1", "")).strip(),
            "address_line_2": str(value.get("address_line_2", "")).strip(),
            "house_number": str(value.get("house_number", "")).strip(),
            "postal_code": str(value.get("postal_code", "")).strip(),
            "city": str(value.get("city", "")).strip(),
            "country_code": str(value.get("country_code", "")).strip().upper(),
            "email": str(value.get("email", "")).strip(),
            "phone_number": str(value.get("phone_number", "")).strip(),
        }
        required_fields = (
            "name",
            "address_line_1",
            "house_number",
            "postal_code",
            "city",
            "country_code",
            "email",
        )
        missing_fields = [field_name for field_name in required_fields if not address[field_name]]
        if missing_fields:
            raise ValidationError(
                f"{label} is missing required fields: {', '.join(sorted(missing_fields))}."
            )
        return address

    def _normalize_parcel(self, value) -> dict[str, object]:
        if not isinstance(value, dict):
            raise ValidationError("parcel must be an object.")

        weight = value.get("weight")
        if not isinstance(weight, dict):
            raise ValidationError("parcel.weight must be an object.")

        weight_value = str(weight.get("value", "")).strip()
        weight_unit = str(weight.get("unit", "")).strip().lower() or "kg"
        if not weight_value:
            raise ValidationError("parcel.weight.value is required.")
        if weight_unit not in {"kg"}:
            raise ValidationError("parcel.weight.unit must be 'kg'.")

        parcel: dict[str, object] = {
            "weight": {
                "value": weight_value,
                "unit": weight_unit,
            }
        }
        dimensions = value.get("dimensions")
        if dimensions:
            if not isinstance(dimensions, dict):
                raise ValidationError("parcel.dimensions must be an object.")
            dimension_unit = str(dimensions.get("unit", "")).strip().lower() or "cm"
            if dimension_unit not in {"cm"}:
                raise ValidationError("parcel.dimensions.unit must be 'cm'.")
            parcel["dimensions"] = {
                "length": str(dimensions.get("length", "")).strip(),
                "width": str(dimensions.get("width", "")).strip(),
                "height": str(dimensions.get("height", "")).strip(),
                "unit": dimension_unit,
            }
        return parcel

    def _normalize_label_details(self, value) -> dict[str, object]:
        if value in (None, ""):
            return {
                "mime_type": "application/pdf",
                "dpi": 72,
            }
        if not isinstance(value, dict):
            raise ValidationError("label_details must be an object.")

        mime_type = str(value.get("mime_type", "application/pdf")).strip() or "application/pdf"
        if mime_type != "application/pdf":
            raise ValidationError("label_details.mime_type must be 'application/pdf'.")

        dpi = value.get("dpi", 72)
        try:
            dpi = int(dpi)
        except (TypeError, ValueError) as exc:
            raise ValidationError("label_details.dpi must be an integer.") from exc
        if dpi <= 0:
            raise ValidationError("label_details.dpi must be a positive integer.")

        return {
            "mime_type": mime_type,
            "dpi": dpi,
        }

    def _get_staff_order(self, *, order_public_id):
        return (
            Order.objects.select_related("customer", "created_by")
            .filter(public_id=order_public_id)
            .first()
        )

    def _get_gateway(self) -> SendcloudGateway:
        if self.gateway is None:
            self.gateway = SendcloudGateway()
        return self.gateway

    def _build_label_filename(self, *, shipment: Shipment) -> str:
        return f"{shipment.order.public_id}-sendcloud-label.pdf"

    def _sanitize_error_message(self, value: str) -> str:
        cleaned_value = " ".join(str(value).split())
        cleaned_value = re.sub(
            r"(secret[_-]?key|secret)\s*=\s*\S+",
            "credential=[redacted]",
            cleaned_value,
        )
        cleaned_value = re.sub(
            r"(public[_-]?key|api[_-]?key)\s*=\s*\S+",
            "credential=[redacted]",
            cleaned_value,
        )
        return cleaned_value[:255]
