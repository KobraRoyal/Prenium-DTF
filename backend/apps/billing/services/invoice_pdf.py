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

    story: list = []
    story.append(Paragraph(f"Facture <b>{escape(invoice.invoice_number)}</b>", title_style))
    story.append(Paragraph("Prenium DTF", small))
    story.append(Spacer(1, 0.4 * cm))

    rows = [
        ["Commande", escape(short_public_ref(order.public_id))],
        ["Client", escape(order.customer.name)],
        [
            "Email facturation",
            escape(order.customer.billing_email or "—"),
        ],
        ["Devise", escape(order.currency)],
        ["Sous-total", f"{order.subtotal_amount:.2f} {order.currency}"],
        ["Total", f"{order.total_amount:.2f} {order.currency}"],
        ["Paiement", escape(payment.get_provider_display())],
        [
            "Réf. PayPal",
            escape(str(payment.paypal_capture_id or payment.paypal_order_id or "—")),
        ],
        [
            "Date d'émission",
            escape(invoice.issued_at.isoformat() if invoice.issued_at else "—"),
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
            "Document généré automatiquement — merci de conserver ce PDF pour votre comptabilité.",
            normal,
        )
    )

    doc.build(story)
    return buffer.getvalue()
