import ipaddress
import logging
from secrets import compare_digest

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse, Http404
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasStaffBillingReadAccess
from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.customers.permissions import HasScopedCustomerAccess

from .services.payments import PaymentService

payment_service = PaymentService()
logger = logging.getLogger(__name__)


def raise_api_validation_error(error: DjangoValidationError):
    if hasattr(error, "message_dict"):
        raise DRFValidationError(error.message_dict)
    raise DRFValidationError({"detail": error.messages})


def serialize_payment(payment) -> dict[str, object]:
    return {
        "public_id": str(payment.public_id),
        "order_public_id": str(payment.order.public_id),
        "provider": payment.provider,
        "status": payment.status,
        "amount": f"{payment.amount:.2f}",
        "currency": payment.currency,
        "paypal_order_id": payment.paypal_order_id,
        "paypal_capture_id": payment.paypal_capture_id,
        "approval_url": payment.approval_url,
        "last_error_message": payment.last_error_message,
        "captured_at": payment.captured_at.isoformat() if payment.captured_at else None,
        "created_at": payment.created_at.isoformat(),
        "updated_at": payment.updated_at.isoformat(),
    }


def serialize_invoice(invoice) -> dict[str, object]:
    return {
        "public_id": str(invoice.public_id),
        "order_public_id": str(invoice.order.public_id),
        "payment_public_id": str(invoice.payment.public_id) if invoice.payment else None,
        "status": invoice.status,
        "invoice_number": invoice.invoice_number,
        "subtotal_amount": f"{invoice.subtotal_amount:.2f}",
        "total_amount": f"{invoice.total_amount:.2f}",
        "currency": invoice.currency,
        "billing_name": invoice.billing_name,
        "billing_email": invoice.billing_email,
        "file": {
            "has_file": bool(invoice.file),
            "name": invoice.file_name,
            "mime_type": invoice.file_mime_type,
        },
        "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None,
        "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
        "created_at": invoice.created_at.isoformat(),
        "updated_at": invoice.updated_at.isoformat(),
    }


def _audit_ip(raw: str) -> str | None:
    try:
        return str(ipaddress.ip_address(raw.strip()))
    except ValueError:
        return None


def _client_ip(request) -> str:
    if getattr(settings, "PAYPAL_INTERNAL_CONFIRM_TRUST_X_FORWARDED_FOR", False):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
    return request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR") or "0.0.0.0"


class ClientPayPalPaymentInitiateView(APIView):
    permission_classes = [IsAuthenticated, HasScopedCustomerAccess]

    def post(self, request, customer_public_id, order_public_id):
        try:
            _order, payment = payment_service.initiate_payment_for_customer_order(
                customer=self.customer,
                order_public_id=order_public_id,
                actor=request.user,
                source="client_api",
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)
        if payment is None:
            raise Http404
        return Response(serialize_payment(payment), status=201)


class ClientInvoiceDetailView(APIView):
    permission_classes = [IsAuthenticated, HasScopedCustomerAccess]

    def get(self, request, customer_public_id, order_public_id):
        _order, invoice = payment_service.get_customer_invoice(
            customer=self.customer,
            order_public_id=order_public_id,
        )
        if invoice is None:
            raise Http404
        return Response(serialize_invoice(invoice))


class ClientInvoiceDownloadView(APIView):
    permission_classes = [IsAuthenticated, HasScopedCustomerAccess]

    def get(self, request, customer_public_id, order_public_id):
        _order, invoice = payment_service.get_customer_invoice(
            customer=self.customer,
            order_public_id=order_public_id,
        )
        if invoice is None or not invoice.file:
            raise Http404
        return FileResponse(
            invoice.file.open("rb"),
            as_attachment=True,
            filename=invoice.file_name or "invoice.pdf",
            content_type=invoice.file_mime_type or "application/pdf",
        )


class BackendPayPalCaptureView(APIView):
    authentication_classes = []
    permission_classes = []

    def _record_denied_attempt(self, *, request, client_ip: str, reason: str, message: str) -> None:
        logger.warning(
            "paypal_internal_capture_denied",
            extra={"client_ip": client_ip, "reason": reason},
        )
        record_event(
            action="security.paypal_internal_capture_denied",
            status=AuditLogEntry.Status.FAILURE,
            message=message,
            ip_address=_audit_ip(client_ip),
            metadata={
                "client_ip": client_ip,
                "reason": reason,
                "path": request.path,
            },
        )

    def _rate_limit_key(self, client_ip: str) -> str:
        return f"paypal_internal_capture_rl:{client_ip}"

    def _register_denied_attempt(self, *, request, client_ip: str, reason: str) -> bool:
        window = getattr(settings, "PAYPAL_INTERNAL_CONFIRM_RATE_LIMIT_WINDOW_SECONDS", 300)
        max_attempts = getattr(settings, "PAYPAL_INTERNAL_CONFIRM_RATE_LIMIT_MAX_ATTEMPTS", 10)
        key = self._rate_limit_key(client_ip)
        try:
            current = cache.incr(key)
        except ValueError:
            cache.add(key, 1, timeout=window)
            current = 1

        self._record_denied_attempt(
            request=request,
            client_ip=client_ip,
            reason=reason,
            message="PayPal internal capture request denied.",
        )

        if current > max_attempts:
            logger.warning(
                "paypal_internal_capture_rate_limited",
                extra={"client_ip": client_ip, "attempts": current},
            )
            if current == max_attempts + 1:
                record_event(
                    action="security.paypal_internal_capture_rate_limited",
                    status=AuditLogEntry.Status.FAILURE,
                    message="PayPal internal capture rate limit reached.",
                    ip_address=_audit_ip(client_ip),
                    metadata={
                        "client_ip": client_ip,
                        "max_attempts": max_attempts,
                        "window_seconds": window,
                        "path": request.path,
                    },
                )
            return True
        return False

    def post(self, request):
        client_ip = _client_ip(request)
        provided_token = request.headers.get("X-Internal-Token", "")
        expected_token = settings.PAYPAL_INTERNAL_CONFIRM_TOKEN or ""
        if not expected_token:
            self._record_denied_attempt(
                request=request,
                client_ip=client_ip,
                reason="missing_expected_token",
                message="PayPal internal confirmation token is not configured.",
            )
            raise PermissionDenied("Invalid internal confirmation token.")

        if not provided_token:
            if self._register_denied_attempt(
                request=request,
                client_ip=client_ip,
                reason="missing_provided_token",
            ):
                return Response({"detail": ["Too many invalid confirmation attempts."]}, status=429)
            raise PermissionDenied("Invalid internal confirmation token.")

        if not compare_digest(provided_token, expected_token):
            if self._register_denied_attempt(
                request=request,
                client_ip=client_ip,
                reason="invalid_token",
            ):
                return Response({"detail": ["Too many invalid confirmation attempts."]}, status=429)
            raise PermissionDenied("Invalid internal confirmation token.")

        order_public_id = request.data.get("order_public_id")
        paypal_order_id = str(request.data.get("paypal_order_id", "")).strip()
        payment_public_id = request.data.get("payment_public_id")
        if not order_public_id or not paypal_order_id:
            raise DRFValidationError(
                {"detail": ["order_public_id and paypal_order_id are required."]}
            )

        try:
            order, payment, invoice = payment_service.confirm_capture(
                order_public_id=order_public_id,
                paypal_order_id=paypal_order_id,
                payment_public_id=payment_public_id,
                actor=None,
                source="backend_api",
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        if payment is None or order is None:
            raise Http404
        return Response(
            {
                "order_public_id": str(order.public_id),
                "payment": serialize_payment(payment),
                "invoice": serialize_invoice(invoice) if invoice else None,
            }
        )


class StaffBillingDetailView(APIView):
    permission_classes = [IsAuthenticated, HasStaffBillingReadAccess]

    def get(self, request, order_public_id):
        order, payment, invoice = payment_service.get_staff_billing(
            order_public_id=order_public_id,
            actor=request.user,
            source="staff_api",
        )
        if order is None:
            raise Http404
        return Response(
            {
                "order_public_id": str(order.public_id),
                "customer": {
                    "public_id": str(order.customer.public_id),
                    "name": order.customer.name,
                },
                "payment": serialize_payment(payment) if payment else None,
                "invoice": serialize_invoice(invoice) if invoice else None,
            }
        )
