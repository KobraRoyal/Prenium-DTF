from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.billing.models import Invoice, Payment
from apps.core.public_refs import short_public_ref
from apps.orders.models import Order


def render_invoice_pdf_bytes(*, invoice: Invoice, order: Order, payment: Payment) -> bytes:
    """PDF de justificatif de paiement (preuve d’encaissement).

    La facture fiscale / comptable est émise hors plateforme (outil RCA).
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=invoice.invoice_number,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name="InvTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=14,
    )
    normal = ParagraphStyle(
        name="InvBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
    )
    small = ParagraphStyle(
        name="InvSmall",
        parent=styles["Normal"],
        fontSize=8,
        leading=11,
        textColor=colors.grey,
    )

    provider_label = payment.get_provider_display()
    if payment.provider == Payment.Provider.PAYPAL:
        provider_ref = str(payment.paypal_capture_id or payment.paypal_order_id or "—")
        provider_ref_label = "Réf. PayPal"
    elif payment.provider == Payment.Provider.STRIPE:
        provider_ref = str(
            payment.stripe_payment_intent_id or payment.stripe_checkout_session_id or "—"
        )
        provider_ref_label = "Réf. Stripe"
    else:
        provider_ref = "—"
        provider_ref_label = "Réf. paiement"

    story: list = []
    story.append(
        Paragraph(
            f"Justificatif de paiement <b>{escape(invoice.invoice_number)}</b>",
            title_style,
        )
    )
    story.append(Paragraph("Prenium DTF — preuve d’encaissement", small))
    story.append(Spacer(1, 0.4 * cm))

    rows = [
        ["Commande", escape(short_public_ref(order.public_id))],
        ["Client", escape(order.customer.name)],
        [
            "Email facturation",
            escape(order.customer.billing_email or "—"),
        ],
        ["Devise", escape(order.currency)],
        ["Sous-total HT", f"{order.subtotal_amount:.2f} {order.currency}"],
        [
            "Livraison",
            (
                f"{getattr(order, 'shipping_amount', 0):.2f} {order.currency}"
                + (
                    f" ({order.shipping_method_name})"
                    if getattr(order, "shipping_method_name", "")
                    else ""
                )
            ),
        ],
        ["TVA", f"{getattr(order, 'tax_amount', 0):.2f} {order.currency}"],
        ["Total réglé", f"{order.total_amount:.2f} {order.currency}"],
        ["Moyen de paiement", escape(provider_label)],
        [provider_ref_label, escape(provider_ref)],
        [
            "Confirmé le",
            escape(
                payment.captured_at.isoformat()
                if payment.captured_at
                else (invoice.issued_at.isoformat() if invoice.issued_at else "—")
            ),
        ],
    ]
    table = Table(rows, colWidths=[5.5 * cm, 10 * cm])
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 10),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#374151")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, -1), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 0.6 * cm))
    story.append(
        Paragraph(
            "Ce document atteste du règlement en ligne. "
            "La facture fiscale est émise séparément via l’outil comptable RCA.",
            normal,
        )
    )

    doc.build(story)
    return buffer.getvalue()
