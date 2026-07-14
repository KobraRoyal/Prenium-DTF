from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.graphics.barcode import code128
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Image as PdfImage,
)
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.orders.models import Order
from apps.production.models import ProductionJob
from apps.production.services.manufacturing_order_previews import (
    ManufacturingOrderPreviewService,
)
from apps.production.services.workflow import ProductionWorkflowService

INK = colors.HexColor("#17324D")
MUTED = colors.HexColor("#62748A")
ACCENT = colors.HexColor("#F97316")
LINE = colors.HexColor("#DCE4EC")
SURFACE = colors.HexColor("#F5F7FA")
SUCCESS_BG = colors.HexColor("#E8F7F1")
SUCCESS_TEXT = colors.HexColor("#12664F")
WARNING_BG = colors.HexColor("#FFF4D6")
WARNING_TEXT = colors.HexColor("#8A5A00")
DANGER_BG = colors.HexColor("#FDEBEC")
DANGER_TEXT = colors.HexColor("#A33A43")


def _text(value) -> str:
    return escape(str(value or "").strip())


def _paragraph(value, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_text(value), style)


def _multiline_paragraph(value, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_text(value).replace("\n", "<br/>"), style)


def _status_colors(status: str) -> tuple[colors.Color, colors.Color]:
    if status in {"ok", "approved"}:
        return SUCCESS_BG, SUCCESS_TEXT
    if status in {"warning", "pending"}:
        return WARNING_BG, WARNING_TEXT
    if status in {"error", "changes_requested"}:
        return DANGER_BG, DANGER_TEXT
    return SURFACE, MUTED


def _draw_footer(canvas: Canvas, doc, *, manufacturing_order_number: str) -> None:
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 1.15 * cm, A4[0] - doc.rightMargin, 1.15 * cm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    page_number = canvas.getPageNumber()
    left_label = "Document interne Atelier" if page_number == 1 else manufacturing_order_number
    canvas.drawString(doc.leftMargin, 0.78 * cm, left_label)
    canvas.drawRightString(
        A4[0] - doc.rightMargin,
        0.78 * cm,
        f"Page {page_number}",
    )
    canvas.restoreState()


def _build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle(
            "OFBrand",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9,
            textColor=ACCENT,
            spaceAfter=3,
        ),
        "title": ParagraphStyle(
            "OFTitle",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=23,
            textColor=INK,
            spaceAfter=10,
        ),
        "eyebrow": ParagraphStyle(
            "OFEyebrow",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=9,
            textColor=MUTED,
        ),
        "of_number": ParagraphStyle(
            "OFNumber",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=INK,
        ),
        "section": ParagraphStyle(
            "OFSection",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=INK,
            spaceBefore=3,
            spaceAfter=6,
        ),
        "meta": ParagraphStyle(
            "OFMeta",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=INK,
        ),
        "meta_label": ParagraphStyle(
            "OFMetaLabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=6.5,
            leading=8,
            textColor=MUTED,
        ),
        "body": ParagraphStyle(
            "OFBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10.5,
            textColor=INK,
        ),
        "body_muted": ParagraphStyle(
            "OFBodyMuted",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.2,
            leading=9.2,
            textColor=MUTED,
        ),
        "table_header": ParagraphStyle(
            "OFTableHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=8.5,
            textColor=colors.white,
        ),
        "table_center": ParagraphStyle(
            "OFTableCenter",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=INK,
            alignment=TA_CENTER,
        ),
        "status": ParagraphStyle(
            "OFStatus",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.1,
            leading=9,
            alignment=TA_LEFT,
        ),
        "preview_fallback": ParagraphStyle(
            "OFPreviewFallback",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=6.6,
            leading=8.2,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "note_label": ParagraphStyle(
            "OFNoteLabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=9,
            textColor=ACCENT,
        ),
        "check": ParagraphStyle(
            "OFCheck",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.8,
            leading=10,
            textColor=INK,
        ),
    }


def _meta_cell(*, label: str, value: str, styles: dict[str, ParagraphStyle]):
    return [
        Paragraph(_text(label).upper(), styles["meta_label"]),
        Spacer(1, 0.04 * cm),
        _paragraph(value or "-", styles["meta"]),
    ]


def _build_reference_card(
    *,
    manufacturing_order_number: str,
    styles: dict[str, ParagraphStyle],
) -> Table:
    barcode = code128.Code128(
        manufacturing_order_number,
        barHeight=0.82 * cm,
        barWidth=0.42,
        humanReadable=False,
    )
    left = [
        Paragraph("NUMÉRO D'OF", styles["eyebrow"]),
        Spacer(1, 0.09 * cm),
        _paragraph(manufacturing_order_number, styles["of_number"]),
        Spacer(1, 0.08 * cm),
        Paragraph("Référence unique Atelier et scan", styles["body_muted"]),
    ]
    right = [
        Paragraph("SCAN ATELIER", styles["eyebrow"]),
        Spacer(1, 0.08 * cm),
        barcode,
    ]
    table = Table([[left, right]], colWidths=[8.3 * cm, 7.5 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
                ("BOX", (0, 0), (-1, -1), 0.8, LINE),
                ("LINEBEFORE", (1, 0), (1, 0), 0.8, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def _build_identity_table(*, payload: dict, styles: dict[str, ParagraphStyle]) -> Table:
    order_summary = payload.get("order_summary") or {}
    production_summary = payload.get("production_summary") or {}
    customer = payload.get("customer") or {}
    rows = [
        [
            _meta_cell(
                label="Commande",
                value=f"#{order_summary.get('reference', '')}",
                styles=styles,
            ),
            _meta_cell(
                label="Client",
                value=str(customer.get("name") or "-"),
                styles=styles,
            ),
        ],
        [
            _meta_cell(
                label="Commande reçue",
                value=str(order_summary.get("created_at_label") or "-"),
                styles=styles,
            ),
            _meta_cell(
                label="Statut Atelier",
                value=str(production_summary.get("status_label") or "-"),
                styles=styles,
            ),
        ],
    ]
    table = Table(rows, colWidths=[7.9 * cm, 7.9 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.45, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _build_items_table(*, items: list[dict], styles: dict[str, ParagraphStyle]) -> Table:
    rows = [
        [
            Paragraph("PRESTATION", styles["table_header"]),
            Paragraph("QUANTITÉ", styles["table_header"]),
            Paragraph("UNITÉ", styles["table_header"]),
        ]
    ]
    for item in items:
        rows.append(
            [
                _paragraph(item.get("service_name") or item.get("service_code"), styles["body"]),
                _paragraph(item.get("quantity"), styles["table_center"]),
                _paragraph(item.get("unit") or "-", styles["body"]),
            ]
        )
    table = Table(rows, colWidths=[10.2 * cm, 2.7 * cm, 2.9 * cm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), INK),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 1), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
            ]
        )
    )
    return table


def _build_preview_cell(*, preview: bytes | None, styles: dict[str, ParagraphStyle]):
    if preview is None:
        return Paragraph("Aperçu<br/>indisponible", styles["preview_fallback"])

    image = PdfImage(BytesIO(preview))
    max_width = 2.05 * cm
    max_height = 2.05 * cm
    ratio = min(max_width / image.imageWidth, max_height / image.imageHeight)
    image.drawWidth = image.imageWidth * ratio
    image.drawHeight = image.imageHeight * ratio
    image.hAlign = "CENTER"
    return image


def _build_uploads_table(
    *,
    uploads: list[dict],
    previews: dict[str, bytes],
    styles: dict[str, ParagraphStyle],
) -> Table:
    rows = [
        [
            Paragraph("APERÇU", styles["table_header"]),
            Paragraph("FICHIER / CONSIGNES", styles["table_header"]),
            Paragraph("QTÉ", styles["table_header"]),
            Paragraph("DIAGNOSTIC AUTO", styles["table_header"]),
            Paragraph("DÉCISION ATELIER", styles["table_header"]),
        ]
    ]
    table_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
    ]

    for row_number, upload in enumerate(uploads, start=1):
        inspection_status = str(upload.get("inspection_status") or "")
        review_status = str(upload.get("atelier_review_status") or "pending")
        inspection_bg, inspection_text = _status_colors(inspection_status)
        review_bg, review_text = _status_colors(review_status)

        inspection_content = [
            Paragraph(_text(upload.get("inspection_status_label")), styles["status"]),
        ]
        if inspection_status != "ok" and upload.get("inspection_summary"):
            inspection_content.extend(
                [
                    Spacer(1, 0.04 * cm),
                    _paragraph(upload.get("inspection_summary"), styles["body_muted"]),
                ]
            )

        review_content = [
            Paragraph(_text(upload.get("atelier_review_status_label")), styles["status"]),
        ]
        review_details = [
            detail
            for detail in (
                upload.get("atelier_review_reason_label"),
                upload.get("atelier_review_comment"),
            )
            if detail
        ]
        for review_detail in review_details:
            review_content.extend(
                [
                    Spacer(1, 0.04 * cm),
                    _paragraph(review_detail, styles["body_muted"]),
                ]
            )

        rows.append(
            [
                _build_preview_cell(
                    preview=previews.get(str(upload.get("public_id") or "")),
                    styles=styles,
                ),
                [
                    _paragraph(upload.get("original_filename"), styles["body"]),
                    Spacer(1, 0.08 * cm),
                    Paragraph("TAILLE DEMANDÉE", styles["meta_label"]),
                    _paragraph(upload.get("dimensions_label"), styles["body_muted"]),
                    Spacer(1, 0.05 * cm),
                    Paragraph("COULEUR DU SUPPORT", styles["meta_label"]),
                    _paragraph(upload.get("support_color_label"), styles["body_muted"]),
                ],
                _paragraph(upload.get("quantity") or 1, styles["table_center"]),
                inspection_content,
                review_content,
            ]
        )
        table_styles.extend(
            [
                ("BACKGROUND", (0, row_number), (0, row_number), SURFACE),
                ("ALIGN", (0, row_number), (0, row_number), "CENTER"),
                ("VALIGN", (0, row_number), (0, row_number), "MIDDLE"),
                ("BACKGROUND", (3, row_number), (3, row_number), inspection_bg),
                ("TEXTCOLOR", (3, row_number), (3, row_number), inspection_text),
                ("BACKGROUND", (4, row_number), (4, row_number), review_bg),
                ("TEXTCOLOR", (4, row_number), (4, row_number), review_text),
                ("TOPPADDING", (0, row_number), (-1, row_number), 6),
                ("BOTTOMPADDING", (0, row_number), (-1, row_number), 6),
            ]
        )

    table = Table(
        rows,
        colWidths=[2.35 * cm, 4.25 * cm, 1.15 * cm, 3.35 * cm, 4.7 * cm],
        repeatRows=1,
    )
    table.setStyle(TableStyle(table_styles))
    return table


def _review_summary_label(summary: dict[str, object]) -> str:
    total = int(summary.get("total") or 0)
    approved = int(summary.get("approved") or 0)
    pending = int(summary.get("pending") or 0)
    changes = int(summary.get("changes_requested") or 0)
    details = [f"{approved}/{total} approuvé(s)"]
    if pending:
        details.append(f"{pending} à contrôler")
    if changes:
        details.append(f"{changes} correction(s) demandée(s)")
    return " - ".join(details)


def _build_note(*, note: str, styles: dict[str, ParagraphStyle]) -> Table:
    table = Table(
        [
            [
                [
                    Paragraph("NOTE CLIENT", styles["note_label"]),
                    Spacer(1, 0.06 * cm),
                    _multiline_paragraph(note, styles["body"]),
                ]
            ]
        ],
        colWidths=[15.8 * cm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF8F1")),
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#FED7AA")),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _build_checklist(*, styles: dict[str, ParagraphStyle]) -> Table:
    rows = [
        [
            Paragraph("[ ] Fichiers conformes", styles["check"]),
            Paragraph("[ ] Quantités contrôlées", styles["check"]),
            Paragraph("[ ] Qualité finale validée", styles["check"]),
        ],
        [
            Paragraph("Opérateur : ____________________", styles["check"]),
            Paragraph("Date : ____ / ____ / ______", styles["check"]),
            Paragraph("Heure : ____ : ____", styles["check"]),
        ],
    ]
    table = Table(rows, colWidths=[5.3 * cm, 5.3 * cm, 5.2 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SURFACE),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def render_manufacturing_order_pdf_bytes(*, order: Order, production_job: ProductionJob) -> bytes:
    payload = ProductionWorkflowService().build_manufacturing_order(
        order=order,
        production_job=production_job,
    )
    manufacturing_order_number = str(payload.get("number") or "OF")
    styles = _build_styles()
    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.6 * cm,
        leftMargin=1.6 * cm,
        topMargin=1.35 * cm,
        bottomMargin=1.55 * cm,
        title=manufacturing_order_number,
        author="Prenium DTF",
        subject="Ordre de fabrication Atelier",
    )

    story: list = [
        Paragraph("PRENIUM DTF / ATELIER", styles["brand"]),
        Paragraph("ORDRE DE FABRICATION", styles["title"]),
        _build_reference_card(
            manufacturing_order_number=manufacturing_order_number,
            styles=styles,
        ),
        Spacer(1, 0.28 * cm),
        _build_identity_table(payload=payload, styles=styles),
        Spacer(1, 0.35 * cm),
    ]

    items = payload.get("items") or []
    if items and payload.get("items_source") == "order_lines":
        story.extend(
            [
                Paragraph("Prestations à produire", styles["section"]),
                _build_items_table(items=items, styles=styles),
                Spacer(1, 0.32 * cm),
            ]
        )

    uploads = payload.get("uploads") or []
    if uploads:
        previews = ManufacturingOrderPreviewService().build_for_order(order=order)
        summary = payload.get("file_review_summary") or {}
        story.extend(
            [
                KeepTogether(
                    [
                        Paragraph("Fichiers de production", styles["section"]),
                        Paragraph(_review_summary_label(summary), styles["body_muted"]),
                        Spacer(1, 0.12 * cm),
                    ]
                ),
                _build_uploads_table(uploads=uploads, previews=previews, styles=styles),
                Spacer(1, 0.32 * cm),
            ]
        )
    else:
        story.extend(
            [
                Paragraph("Fichiers de production", styles["section"]),
                Paragraph("Aucun fichier de production disponible.", styles["body"]),
                Spacer(1, 0.32 * cm),
            ]
        )

    customer_note = str((payload.get("order_summary") or {}).get("customer_note") or "").strip()
    if customer_note:
        story.extend(
            [
                _build_note(note=customer_note, styles=styles),
                Spacer(1, 0.32 * cm),
            ]
        )

    story.extend(
        [
            Paragraph("Contrôle de fin de production", styles["section"]),
            _build_checklist(styles=styles),
        ]
    )

    footer = lambda canvas, doc: _draw_footer(  # noqa: E731
        canvas,
        doc,
        manufacturing_order_number=manufacturing_order_number,
    )
    pdf.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
