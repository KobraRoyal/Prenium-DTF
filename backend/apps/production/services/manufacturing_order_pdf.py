from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from django.utils.formats import date_format
from reportlab.graphics.barcode import code128
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.orders.models import Order
from apps.production.models import ProductionJob
from apps.production.services.workflow import ProductionWorkflowService


def render_manufacturing_order_pdf_bytes(*, order: Order, production_job: ProductionJob) -> bytes:
    svc = ProductionWorkflowService()
    doc_payload = svc.build_manufacturing_order(order=order, production_job=production_job)

    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.8 * cm,
        leftMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title=str(doc_payload.get("number", "OF")),
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(name="OFh1", parent=styles["Heading1"], fontSize=15, spaceAfter=10)
    h2 = ParagraphStyle(name="OFh2", parent=styles["Heading2"], fontSize=11, spaceAfter=6)
    body = ParagraphStyle(name="OFbody", parent=styles["Normal"], fontSize=9, leading=12)
    bc_caption = ParagraphStyle(
        name="OFbcap",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
        fontName="Courier",
    )

    story: list = []
    mo_num = escape(str(doc_payload["number"]))
    story.append(Paragraph(f"Ordre de fabrication — <b>{mo_num}</b>", h1))
    cust_label = escape(str(doc_payload.get("customer", {}).get("name", "")))
    created_at = order.created_at
    date_label = escape(date_format(created_at, "SHORT_DATETIME_FORMAT"))
    story.append(
        Paragraph(
            f"Client : <b>{cust_label}</b> — entrée atelier / commande : {date_label}",
            body,
        )
    )
    story.append(
        Paragraph(
            "Traçabilité : scanner le code-barres ci-dessous (Code 128) ou saisir la référence.",
            body,
        )
    )
    story.append(Spacer(1, 0.25 * cm))

    mo_raw = str(doc_payload.get("number") or "").strip()
    if mo_raw:
        story.append(Paragraph("<b>Code-barres (Code 128)</b>", h2))
        barcode = code128.Code128(
            mo_raw,
            barHeight=1.0 * cm,
            barWidth=0.45,
            humanReadable=False,
        )
        story.append(barcode)
        story.append(Spacer(1, 0.12 * cm))
        story.append(Paragraph(escape(mo_raw), bc_caption))
    story.append(Spacer(1, 0.35 * cm))

    osum = doc_payload.get("order_summary") or {}
    story.append(Paragraph("<b>Récapitulatif commande</b>", h2))
    summary_rows = [
        ["Statut commande", escape(str(osum.get("status", "")))],
        ["Total TTC", f"{osum.get('total_amount', '')} {osum.get('currency', '')}"],
        ["Note client", escape(str(osum.get("customer_note") or "—"))],
    ]
    st = Table(summary_rows, colWidths=[4.5 * cm, 11 * cm])
    st.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(st)
    story.append(Spacer(1, 0.35 * cm))

    ps = doc_payload.get("production_summary") or {}
    story.append(Paragraph("<b>Production</b>", h2))
    pr_rows = [
        ["Statut atelier", escape(str(ps.get("status", "")))],
        ["Dernière transition", escape(str(ps.get("last_transition_at") or "—"))],
    ]
    pt = Table(pr_rows, colWidths=[4.5 * cm, 11 * cm])
    pt.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9)]))
    story.append(pt)
    story.append(Spacer(1, 0.35 * cm))

    items = doc_payload.get("items") or []
    if items:
        story.append(Paragraph("<b>Lignes & fichiers</b>", h2))
        item_rows = [["Service / fichier", "Qté", "Détails"]]
        for it in items:
            item_rows.append(
                [
                    escape(str(it.get("service_name", "")))[:80],
                    escape(str(it.get("quantity", ""))),
                    escape(str(it.get("service_code", ""))),
                ]
            )
        itable = Table(item_rows, colWidths=[9 * cm, 2 * cm, 4.5 * cm])
        itable.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
                ]
            )
        )
        story.append(itable)
        story.append(Spacer(1, 0.3 * cm))

    uploads = doc_payload.get("uploads") or []
    if len(uploads) > 6:
        story.append(PageBreak())
    if uploads:
        story.append(Paragraph("<b>Fichiers client</b>", h2))
        up_rows = [["Fichier", "Contrôle", "Sync Drive"]]
        for u in uploads[:40]:
            up_rows.append(
                [
                    escape(str(u.get("original_filename", "")))[:70],
                    escape(str(u.get("inspection_status") or "—")),
                    escape(str(u.get("drive_sync_status") or "—")),
                ]
            )
        ut = Table(up_rows, colWidths=[7 * cm, 3 * cm, 5.5 * cm])
        ut.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), "Helvetica", 7),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
                ]
            )
        )
        story.append(ut)

    pdf.build(story)
    return buffer.getvalue()
