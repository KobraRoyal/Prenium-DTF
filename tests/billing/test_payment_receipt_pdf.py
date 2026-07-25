from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from apps.billing.models import Payment
from apps.billing.services.invoice_pdf import render_invoice_pdf_bytes


def test_payment_receipt_pdf_is_not_labeled_as_fiscal_invoice():
    order = SimpleNamespace(
        public_id=UUID("7458b2ae-59f5-4b08-844f-464542e8bb22"),
        currency="EUR",
        subtotal_amount=Decimal("147.50"),
        total_amount=Decimal("147.50"),
        customer=SimpleNamespace(name="Compte T", billing_email="t@test.com"),
    )
    payment = SimpleNamespace(
        provider=Payment.Provider.PAYPAL,
        paypal_order_id="ORDER123",
        paypal_capture_id="CAPTURE123",
        stripe_payment_intent_id="",
        stripe_checkout_session_id="",
        status=Payment.Status.CAPTURED,
        captured_at=None,
        get_provider_display=lambda: "PayPal",
    )
    invoice = SimpleNamespace(
        invoice_number="JP-TEST",
        issued_at=None,
    )

    pdf = render_invoice_pdf_bytes(invoice=invoice, order=order, payment=payment)

    import pymupdf

    text = "\n".join(page.get_text() for page in pymupdf.open(stream=pdf, filetype="pdf"))
    assert "Justificatif de paiement" in text
    assert "RCA" in text
    assert "facture fiscale" in text.lower()
    assert "Facture JP-TEST" not in text
