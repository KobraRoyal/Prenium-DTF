from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse, Http404
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasStaffBillingReadAccess
from apps.customers.permissions import HasScopedCustomerAccess

from .services.payments import PaymentService

payment_service = PaymentService()


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

    def post(self, request):
        provided_token = request.headers.get("X-Internal-Token", "")
        expected_token = settings.PAYPAL_INTERNAL_CONFIRM_TOKEN
        if not expected_token or provided_token != expected_token:
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

