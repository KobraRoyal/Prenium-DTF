from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime
from urllib import error, parse, request
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.core.public_refs import short_public_ref
from apps.orders.models import Order
from apps.production.models import ProductionJob
from apps.production.services.workflow import ProductionWorkflowService
from apps.shipping.models import Shipment

CARRIER_HANDOFF_STATUS_CODES = frozenset(
    {
        "AT_CUSTOMS",
        "AT_SORTING_CENTER",
        "AT_SORTING_CENTRE",
        "ACCEPTED",
        "AWAITING_CUSTOMER_PICKUP",
        "BEING_SORTED",
        "COLLECTED",
        "COLLECTED_BY_CARRIER",
        "DELIVERED",
        "DELIVERY_ATTEMPT_FAILED",
        "DELIVERY_DELAYED",
        "DRIVER_EN_ROUTE",
        "EN_ROUTE_TO_SORTING_CENTER",
        "EN_ROUTE_TO_SORTING_CENTRE",
        "EN_ROUTE_TO_SORTING",
        "IN_TRANSIT",
        "NOT_SORTED",
        "PARCEL_EN_ROUTE",
        "PICKED_UP_BY_DRIVER",
        "REFUSED_BY_RECIPIENT",
        "RETURNED_TO_SENDER",
        "SHIPMENT_COLLECTED_BY_CUSTOMER",
        "SHIPMENT_PICKED_UP_BY_DRIVER",
        "SORTED",
        "UNABLE_TO_DELIVER",
    }
)


def is_carrier_handoff_status(status_code: str) -> bool:
    normalized = re.sub(r"[^A-Z0-9]+", "_", str(status_code).strip().upper()).strip("_")
    return normalized in CARRIER_HANDOFF_STATUS_CODES


class SendcloudConfigurationError(Exception):
    pass


class SendcloudAPIError(Exception):
    pass


def get_sendcloud_webhook_secret() -> str:
    return str(
        getattr(settings, "SENDCLOUD_WEBHOOK_SECRET", "") or settings.SENDCLOUD_SECRET_KEY or ""
    ).strip()


def verify_sendcloud_webhook_signature(*, payload: bytes, signature_header: str) -> None:
    secret = get_sendcloud_webhook_secret()
    if not secret:
        raise SendcloudConfigurationError(
            "Sendcloud webhook secret must be configured via SENDCLOUD_WEBHOOK_SECRET "
            "or SENDCLOUD_SECRET_KEY."
        )
    provided = str(signature_header or "").strip()
    if not provided:
        raise SendcloudAPIError("Missing Sendcloud-Signature header.")
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, provided):
        raise SendcloudAPIError("Invalid Sendcloud webhook signature.")


def extract_parcel_from_webhook_payload(payload: bytes) -> dict[str, object]:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SendcloudAPIError("Invalid Sendcloud webhook payload.") from exc
    if not isinstance(data, dict):
        raise SendcloudAPIError("Sendcloud webhook payload must be a JSON object.")

    for key in ("parcel", "data", "msg"):
        nested = data.get(key)
        if isinstance(nested, dict) and _looks_like_parcel(nested):
            return nested
    if _looks_like_parcel(data):
        return data
    raise SendcloudAPIError("Sendcloud webhook payload did not include a parcel.")


def _looks_like_parcel(value: dict[str, object]) -> bool:
    return bool(
        value.get("id")
        or value.get("tracking_number")
        or value.get("tracking_url")
        or value.get("status")
    )


def parse_sendcloud_event_timestamp(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.get_current_timezone())
        except (OverflowError, OSError, ValueError):
            return None
    raw = str(value).strip()
    if not raw:
        return None
    parsed = parse_datetime(raw)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed)
    return parsed


@dataclass(frozen=True)
class SendcloudOrderResult:
    """Résultat d’une déclaration Incoming Order (sans étiquette)."""

    sendcloud_order_id: str
    order_id: str
    order_number: str
    status_code: str
    status_message: str


class SendcloudGateway:
    def __init__(self):
        self.public_key = settings.SENDCLOUD_PUBLIC_KEY
        self.secret_key = settings.SENDCLOUD_SECRET_KEY
        self.base_url = settings.SENDCLOUD_API_BASE_URL.rstrip("/")
        self.timeout_seconds = settings.SENDCLOUD_TIMEOUT_SECONDS
        self.integration_id = int(getattr(settings, "SENDCLOUD_INTEGRATION_ID", 0) or 0)

        if not self.public_key or not self.secret_key:
            raise SendcloudConfigurationError(
                "Sendcloud credentials must be configured via environment variables."
            )
        if self.integration_id <= 0:
            raise SendcloudConfigurationError(
                "Sendcloud integration id must be configured via SENDCLOUD_INTEGRATION_ID."
            )

    def declare_order(self, *, payload: list[dict[str, object]]) -> SendcloudOrderResult:
        response_payload = self._request_json(
            method="POST",
            url=f"{self.base_url}/orders",
            payload=payload,
        )
        rows = response_payload.get("data")
        if not isinstance(rows, list) or not rows:
            raise SendcloudAPIError("Sendcloud response did not include an order.")
        row = rows[0] if isinstance(rows[0], dict) else {}
        sendcloud_order_id = str(row.get("id", "")).strip()
        if not sendcloud_order_id:
            raise SendcloudAPIError("Sendcloud response did not include an order id.")
        return SendcloudOrderResult(
            sendcloud_order_id=sendcloud_order_id,
            order_id=str(row.get("order_id", "")).strip(),
            order_number=str(row.get("order_number", "")).strip(),
            status_code="DECLARED",
            status_message="Declared in Sendcloud — awaiting label",
        )

    def build_order_payload(
        self,
        *,
        order: Order,
        shipment_request: dict[str, object],
    ) -> list[dict[str, object]]:
        recipient = shipment_request["recipient"]
        parcel = shipment_request.get("parcel") if isinstance(shipment_request.get("parcel"), dict) else {}
        weight = parcel.get("weight") if isinstance(parcel.get("weight"), dict) else {}
        weight_value = float(str(weight.get("value") or "1"))
        weight_unit = str(weight.get("unit") or "kg")
        order_id = str(order.public_id)
        order_number = short_public_ref(order.public_id)
        # Date de déclaration (pas Order.created_at) pour apparaître dans les filtres Sendcloud « 7 derniers jours ».
        created_at = timezone.now().isoformat()
        total_value = float(order.total_amount)
        order_items = self._build_order_items(order=order, weight_value=weight_value, weight_unit=weight_unit)

        return [
            {
                "order_id": order_id,
                "order_number": order_number,
                "order_details": {
                    "integration": {"id": self.integration_id},
                    "status": {"code": "ready_to_ship", "message": "Ready to ship"},
                    "order_created_at": created_at,
                    "order_items": order_items,
                },
                "payment_details": {
                    "total_price": {
                        "value": total_value,
                        "currency": order.currency,
                    },
                    "status": {"code": "paid", "message": "Paid"},
                },
                "shipping_address": {
                    "name": recipient["name"],
                    "company_name": recipient.get("company_name") or "",
                    "address_line_1": recipient["address_line_1"],
                    "address_line_2": recipient.get("address_line_2") or "",
                    "house_number": recipient["house_number"],
                    "postal_code": recipient["postal_code"],
                    "city": recipient["city"],
                    "country_code": recipient["country_code"],
                    "email": recipient["email"],
                    "phone_number": recipient.get("phone_number") or "",
                },
                "shipping_details": {
                    "is_local_pickup": False,
                    "measurement": {
                        "weight": {
                            "value": weight_value,
                            "unit": weight_unit,
                        }
                    },
                },
            }
        ]

    def _build_order_items(
        self,
        *,
        order: Order,
        weight_value: float,
        weight_unit: str,
    ) -> list[dict[str, object]]:
        lines = list(order.items.all())
        if not lines:
            return [
                {
                    "name": f"Commande Prenium DTF {short_public_ref(order.public_id)}",
                    "quantity": 1,
                    "total_price": {
                        "value": float(order.total_amount),
                        "currency": order.currency,
                    },
                    "measurement": {
                        "weight": {"value": weight_value, "unit": weight_unit},
                    },
                }
            ]

        items: list[dict[str, object]] = []
        for line in lines:
            # Sendcloud Orders API exige une quantité entière (>= 1).
            raw_quantity = float(line.quantity)
            quantity_payload = max(1, int(raw_quantity) if raw_quantity.is_integer() else int(raw_quantity) + 1)
            item: dict[str, object] = {
                "name": str(line.service_name or line.service_code or "Article DTF").strip(),
                "quantity": quantity_payload,
                "total_price": {
                    "value": float(line.line_total),
                    "currency": order.currency,
                },
            }
            sku = str(line.service_code or "").strip()
            if sku:
                item["sku"] = sku
            items.append(item)
        return items

    def find_parcels_for_order_number(self, *, order_number: str) -> list[dict[str, object]]:
        order_number = str(order_number).strip()
        if not order_number:
            return []
        url = f"{self._v2_base_url()}/parcels?order_number={parse.quote(order_number)}"
        response_payload = self._request_json(method="GET", url=url, payload=None)
        parcels = response_payload.get("parcels")
        if not isinstance(parcels, list):
            return []
        return [parcel for parcel in parcels if isinstance(parcel, dict)]

    def _v2_base_url(self) -> str:
        if self.base_url.endswith("/v3"):
            return f"{self.base_url[:-3]}/v2"
        return self.base_url.replace("/api/v3", "/api/v2")

    def _auth_header(self) -> str:
        raw_value = f"{self.public_key}:{self.secret_key}".encode()
        return f"Basic {base64.b64encode(raw_value).decode('ascii')}"

    def _request_json(
        self,
        *,
        method: str,
        url: str,
        payload: dict[str, object] | list[dict[str, object]] | None = None,
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
                raw = response.read().decode()
                if not raw:
                    return {}
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
                if isinstance(parsed, list):
                    return {"data": parsed}
                raise SendcloudAPIError("Unexpected Sendcloud response payload.")
        except error.HTTPError as exc:
            raise SendcloudAPIError(self._build_api_error_message(exc)) from exc
        except error.URLError as exc:
            raise SendcloudAPIError("Unable to reach Sendcloud.") from exc

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

            if shipment.status == Shipment.Status.CREATED and (
                shipment.sendcloud_order_id or shipment.sendcloud_parcel_id
            ):
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

        sendcloud_payload = gateway.build_order_payload(
            order=order,
            shipment_request=shipment_request,
        )

        try:
            result = gateway.declare_order(payload=sendcloud_payload)
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
            shipment.sendcloud_order_id = result.sendcloud_order_id
            shipment.sendcloud_shipment_id = ""
            shipment.sendcloud_parcel_id = ""
            shipment.sendcloud_status_code = result.status_code[:64]
            shipment.sendcloud_status_message = result.status_message[:255]
            shipment.tracking_number = ""
            shipment.tracking_url = ""
            shipment.label_filename = ""
            shipment.label_mime_type = ""
            shipment.label_retrieved_at = None
            shipment.last_api_sync_at = timezone.now()
            shipment.last_error_message = ""
            shipment.save(
                update_fields=[
                    "updated_by",
                    "status",
                    "sendcloud_order_id",
                    "sendcloud_shipment_id",
                    "sendcloud_parcel_id",
                    "sendcloud_status_code",
                    "sendcloud_status_message",
                    "tracking_number",
                    "tracking_url",
                    "label_filename",
                    "label_mime_type",
                    "label_retrieved_at",
                    "last_api_sync_at",
                    "last_error_message",
                    "updated_at",
                ]
            )

        record_event(
            action="shipping.shipment_created",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=shipment,
            metadata={
                "order_public_id": str(order.public_id),
                "customer_public_id": str(order.customer.public_id),
                "shipment_public_id": str(shipment.public_id),
                "sendcloud_order_id": shipment.sendcloud_order_id,
                "sendcloud_parcel_id": shipment.sendcloud_parcel_id,
                "tracking_number": shipment.tracking_number,
                "has_label": False,
                "declared_without_label": True,
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

        gateway = self._get_gateway()
        parcel_id = str(shipment.sendcloud_parcel_id or "").strip()
        try:
            if parcel_id:
                parcel_payload = gateway.fetch_parcel(parcel_id=parcel_id)
            else:
                parcels = gateway.find_parcels_for_order_number(
                    order_number=short_public_ref(order.public_id),
                )
                if not parcels:
                    parcels = gateway.find_parcels_for_order_number(
                        order_number=str(order.public_id),
                    )
                if not parcels:
                    raise ValidationError(
                        "Aucun colis Sendcloud pour cette commande. "
                        "Générez d'abord l'étiquette dans le panneau Sendcloud."
                    )
                parcel_payload = parcels[0]
                linked_parcel_id = str(parcel_payload.get("id", "")).strip()
                if linked_parcel_id:
                    with transaction.atomic():
                        shipment = Shipment.objects.select_for_update().get(pk=shipment.pk)
                        shipment.sendcloud_parcel_id = linked_parcel_id
                        shipment.save(update_fields=["sendcloud_parcel_id", "updated_at"])
        except (SendcloudAPIError, SendcloudConfigurationError) as exc:
            raise ValidationError(self._sanitize_error_message(str(exc))) from exc

        return self._apply_tracking_update(
            shipment=shipment,
            parcel=parcel_payload,
            actor=actor,
            source=source,
            audit_action="shipping.shipment_tracking_synced",
        )

    def apply_parcel_status_webhook(
        self,
        *,
        parcel: dict[str, object],
        source: str = "sendcloud_webhook",
    ):
        if not isinstance(parcel, dict):
            raise ValidationError("Sendcloud webhook parcel must be an object.")

        parcel_id = str(parcel.get("id", "")).strip()
        order_refs = self._extract_order_refs_from_parcel(parcel)
        shipment = None
        if parcel_id:
            shipment = (
                Shipment.objects.select_related("order", "order__customer")
                .filter(sendcloud_parcel_id=parcel_id, status=Shipment.Status.CREATED)
                .first()
            )

        if shipment is None and order_refs:
            public_ids = []
            short_refs = []
            for ref in order_refs:
                try:
                    public_ids.append(UUID(str(ref)))
                except (TypeError, ValueError, AttributeError):
                    cleaned = str(ref).strip().lower()
                    if len(cleaned) == 12 and all(char in "0123456789abcdef" for char in cleaned):
                        short_refs.append(cleaned)
            match_q = Q(sendcloud_order_id__in=order_refs)
            if public_ids:
                match_q |= Q(order__public_id__in=public_ids)
            shipment = (
                Shipment.objects.select_related("order", "order__customer")
                .filter(status=Shipment.Status.CREATED)
                .filter(match_q)
                .first()
            )
            if shipment is None and short_refs:
                for candidate in (
                    Shipment.objects.select_related("order", "order__customer")
                    .filter(status=Shipment.Status.CREATED)
                    .iterator(chunk_size=200)
                ):
                    if short_public_ref(candidate.order.public_id).lower() in short_refs:
                        shipment = candidate
                        break
            if shipment is not None and parcel_id and not shipment.sendcloud_parcel_id:
                with transaction.atomic():
                    shipment = Shipment.objects.select_for_update().get(pk=shipment.pk)
                    shipment.sendcloud_parcel_id = parcel_id
                    shipment.save(update_fields=["sendcloud_parcel_id", "updated_at"])

        if shipment is None:
            record_event(
                action="shipping.sendcloud_webhook_unknown_parcel",
                status=AuditLogEntry.Status.FAILURE,
                message="Sendcloud parcel not found locally.",
                metadata={
                    "sendcloud_parcel_id": parcel_id[:64],
                    "order_refs": sorted(order_refs)[:5],
                    "source": source,
                },
            )
            return None, None

        event_at = None
        for key in ("timestamp", "date_updated", "updated_at", "modified"):
            event_at = parse_sendcloud_event_timestamp(parcel.get(key))
            if event_at is not None:
                break

        return self._apply_tracking_update(
            shipment=shipment,
            parcel=parcel,
            actor=None,
            source=source,
            audit_action="shipping.shipment_tracking_synced",
            event_at=event_at,
        )

    def download_staff_shipment_label(self, *, order_public_id, actor, source: str):
        order = self._get_staff_order(order_public_id=order_public_id)
        if order is None:
            return None, None

        shipment = (
            Shipment.objects.select_related("order", "order__customer")
            .filter(order=order)
            .first()
        )
        if shipment is None or not shipment.label_file:
            return order, None

        record_event(
            action="shipping.shipment_label_downloaded",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=shipment,
            metadata={
                "order_public_id": str(order.public_id),
                "customer_public_id": str(order.customer.public_id),
                "shipment_public_id": str(shipment.public_id),
                "label_filename": shipment.label_filename,
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
                "shipped_at",
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
            "shipped_at": shipment.shipped_at.isoformat() if shipment.shipped_at else None,
            "last_sync_at": sync_ts.isoformat() if sync_ts else None,
        }

    def sync_stale_shipments_tracking(self, *, limit: int = 50) -> int:
        """Synchronise les expéditions créées dont le suivi n'a pas été rafraîchi récemment."""
        from datetime import timedelta

        stale_before = timezone.now() - timedelta(minutes=45)
        queryset = (
            Shipment.objects.filter(status=Shipment.Status.CREATED)
            .filter(Q(sendcloud_parcel_id__gt="") | Q(sendcloud_order_id__gt=""))
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

    def _apply_tracking_update(
        self,
        *,
        shipment: Shipment,
        parcel: dict[str, object],
        actor,
        source: str,
        audit_action: str,
        event_at: datetime | None = None,
    ):
        order = shipment.order
        fields = self._extract_tracking_fields_from_parcel(parcel)
        now = timezone.now()
        became_shipped = False
        skipped_stale = False

        with transaction.atomic():
            shipment = (
                Shipment.objects.select_for_update()
                .select_related("order", "order__customer")
                .get(pk=shipment.pk)
            )
            if (
                event_at is not None
                and shipment.last_api_sync_at is not None
                and event_at < shipment.last_api_sync_at
            ):
                skipped_stale = True
            else:
                shipment.sendcloud_status_code = fields["sendcloud_status_code"]
                shipment.sendcloud_status_message = fields["sendcloud_status_message"]
                if fields["tracking_number"]:
                    shipment.tracking_number = fields["tracking_number"]
                if fields["tracking_url"]:
                    shipment.tracking_url = fields["tracking_url"]
                if shipment.shipped_at is None and is_carrier_handoff_status(
                    fields["sendcloud_status_code"]
                ):
                    shipment.shipped_at = now
                    became_shipped = True
                shipment.last_api_sync_at = event_at or now
                shipment.updated_by = actor if getattr(actor, "is_authenticated", False) else None
                shipment.save(
                    update_fields=[
                        "sendcloud_status_code",
                        "sendcloud_status_message",
                        "tracking_number",
                        "tracking_url",
                        "shipped_at",
                        "last_api_sync_at",
                        "updated_by",
                        "updated_at",
                    ]
                )

        if skipped_stale:
            record_event(
                action="shipping.shipment_tracking_sync_skipped_stale",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=shipment,
                metadata={
                    "order_public_id": str(order.public_id),
                    "customer_public_id": str(order.customer.public_id),
                    "shipment_public_id": str(shipment.public_id),
                    "sendcloud_status_code": fields["sendcloud_status_code"],
                    "source": source,
                },
            )
            return order, shipment

        record_event(
            action=audit_action,
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
        if became_shipped:
            from apps.notifications.services.transactional import schedule_order_shipped_email

            schedule_order_shipped_email(order_public_id=order.public_id)
        return order, shipment

    def _extract_order_refs_from_parcel(self, parcel: dict[str, object]) -> list[str]:
        refs: list[str] = []
        for key in ("order_number", "external_order_id", "external_reference", "reference"):
            value = str(parcel.get(key, "")).strip()
            if value:
                refs.append(value)
        nested_order = parcel.get("order")
        if isinstance(nested_order, dict):
            for key in ("order_number", "order_id", "id", "external_order_id"):
                value = str(nested_order.get(key, "")).strip()
                if value:
                    refs.append(value)
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for ref in refs:
            if ref not in seen:
                seen.add(ref)
                unique.append(ref)
        return unique

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

        return {
            "shipping_option_code": shipping_option_code,
            "contract_id": normalized_contract_id,
            "recipient": recipient,
            "parcel": parcel,
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

    def _get_staff_order(self, *, order_public_id):
        return (
            Order.objects.select_related("customer", "created_by")
            .prefetch_related("items")
            .filter(public_id=order_public_id)
            .first()
        )

    def _get_gateway(self) -> SendcloudGateway:
        if self.gateway is None:
            self.gateway = SendcloudGateway()
        return self.gateway

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
