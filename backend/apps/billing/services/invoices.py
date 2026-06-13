from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.billing.models import Invoice, Payment
from apps.billing.services.invoice_pdf import render_invoice_pdf_bytes
from apps.orders.models import Order


class InvoiceService:
    def ensure_invoice_for_captured_payment(
        self,
        *,
        order: Order,
        payment: Payment,
        source: str,
    ) -> Invoice:
        if payment.status != Payment.Status.CAPTURED:
            raise ValueError("Invoice can only be generated from a captured payment.")

        with transaction.atomic():
            invoice, created = Invoice.objects.select_for_update().get_or_create(
                order=order,
                defaults=self._build_defaults(order=order, payment=payment, source=source),
            )
            if not created:
                to_update: list[str] = []
                if invoice.payment_id is None:
                    invoice.payment = payment
                    to_update.append("payment")
                if invoice.paid_at is None and payment.status == Payment.Status.CAPTURED:
                    invoice.paid_at = invoice.issued_at or timezone.now()
                    to_update.append("paid_at")
                if to_update:
                    to_update.append("updated_at")
                    invoice.save(update_fields=to_update)
                return invoice

            content = render_invoice_pdf_bytes(invoice=invoice, order=order, payment=payment)
            invoice.file.save(invoice.file_name, ContentFile(content), save=False)
            invoice.save()

        record_event(
            action="billing.invoice_issued",
            actor=(
                payment.created_by
                if getattr(payment.created_by, "is_authenticated", False)
                else None
            ),
            target=invoice,
            metadata={
                "order_public_id": str(order.public_id),
                "customer_public_id": str(order.customer.public_id),
                "payment_public_id": str(payment.public_id),
                "invoice_number": invoice.invoice_number,
                "source": source,
            },
        )
        return invoice

    def mark_invoice_paid_by_staff(
        self,
        *,
        invoice: Invoice,
        actor,
        source: str,
    ) -> Invoice:
        """Enregistre le paiement d’une facture (typiquement virement reçu)."""
        if invoice.paid_at is not None:
            raise ValidationError("La facture est déjà marquée comme payée.")
        with transaction.atomic():
            locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
            if locked.paid_at is not None:
                return locked
            now = timezone.now()
            locked.paid_at = now
            locked.paid_recorded_by = actor if getattr(actor, "is_authenticated", False) else None
            locked.save(update_fields=["paid_at", "paid_recorded_by", "updated_at"])
        record_event(
            action="billing.invoice_marked_paid",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=locked,
            metadata={
                "order_public_id": str(locked.order.public_id),
                "customer_public_id": str(locked.order.customer.public_id),
                "invoice_number": locked.invoice_number,
                "source": source,
            },
        )
        return locked

    def _build_defaults(self, *, order: Order, payment: Payment, source: str) -> dict[str, object]:
        invoice_number = self._build_invoice_number(order=order)
        issued_at = timezone.now()
        return {
            "payment": payment,
            "status": Invoice.Status.ISSUED,
            "invoice_number": invoice_number,
            "subtotal_amount": Decimal(order.subtotal_amount),
            "total_amount": Decimal(order.total_amount),
            "currency": order.currency,
            "billing_name": order.customer.name,
            "billing_email": order.customer.billing_email,
            "file_name": f"{invoice_number}.pdf",
            "file_mime_type": "application/pdf",
            "source": source,
            "issued_at": issued_at,
            "paid_at": issued_at if payment.status == Payment.Status.CAPTURED else None,
            "snapshot": {
                "order_public_id": str(order.public_id),
                "customer_public_id": str(order.customer.public_id),
                "payment_public_id": str(payment.public_id),
                "total_amount": f"{order.total_amount:.2f}",
                "currency": order.currency,
                "issued_at": issued_at.isoformat(),
                "document_format": "application/pdf",
            },
        }

    def _build_invoice_number(self, *, order: Order) -> str:
        return f"INV-{order.public_id.hex.upper()}"
