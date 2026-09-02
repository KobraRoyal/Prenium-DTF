from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.barcode import code128, qr
from reportlab.graphics.shapes import Circle, Drawing, String, Wedge
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Image as PdfImage
from reportlab.platypus import (
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

INK = colors.HexColor("#111827")
MUTED = colors.HexColor("#6B7280")
LINE = colors.HexColor("#E5E7EB")
SURFACE = colors.HexColor("#F9FAFB")
MULTICOLOR_SWATCH = (
    colors.HexColor("#EF4444"),
    colors.HexColor("#F59E0B"),
    colors.HexColor("#10B981"),
    colors.HexColor("#3B82F6"),
)

CONTENT_WIDTH = 16.6 * cm
PAD_H = 6
PAD_V = 5


def _text(value) -> str:
    return escape(str(value or "").strip())


def _paragraph(value, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_text(value), style)


def _multiline_paragraph(value, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_text(value).replace("\n", "<br/>"), style)


def _draw_footer(canvas: Canvas, doc, *, manufacturing_order_number: str) -> None:
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.6)
    canvas.line(doc.leftMargin, 1.1 * cm, A4[0] - doc.rightMargin, 1.1 * cm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    page_number = canvas.getPageNumber()
    canvas.drawString(doc.leftMargin, 0.72 * cm, manufacturing_order_number)
    canvas.drawRightString(A4[0] - doc.rightMargin, 0.72 * cm, str(page_number))
    canvas.restoreState()


def _build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "barcode_caption": ParagraphStyle(
            "OFBarcodeCaption",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            textColor=INK,
            alignment=TA_CENTER,
        ),
        "section": ParagraphStyle(
            "OFSection",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            textColor=INK,
            alignment=TA_LEFT,
            spaceBefore=2,
            spaceAfter=5,
        ),
        "meta": ParagraphStyle(
            "OFMeta",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            textColor=INK,
            alignment=TA_LEFT,
        ),
        "meta_label": ParagraphStyle(
            "OFMetaLabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=6.5,
            leading=8,
            textColor=MUTED,
            alignment=TA_LEFT,
        ),
        "body": ParagraphStyle(
            "OFBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=INK,
            alignment=TA_LEFT,
        ),
        "body_muted": ParagraphStyle(
            "OFBodyMuted",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            textColor=MUTED,
            alignment=TA_LEFT,
        ),
        "table_header": ParagraphStyle(
            "OFTableHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=6.5,
            leading=8,
            textColor=colors.white,
            alignment=TA_LEFT,
        ),
        "table_center": ParagraphStyle(
            "OFTableCenter",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12,
            textColor=INK,
            alignment=TA_CENTER,
        ),
        "preview_fallback": ParagraphStyle(
            "OFPreviewFallback",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=6.5,
            leading=8,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "check": ParagraphStyle(
            "OFCheck",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9.5,
            textColor=INK,
            alignment=TA_LEFT,
        ),
        "sign": ParagraphStyle(
            "OFSign",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9.5,
            textColor=MUTED,
            alignment=TA_RIGHT,
        ),
    }


def _meta_cell(*, label: str, value: str, styles: dict[str, ParagraphStyle]):
    return [
        Paragraph(_text(label).upper(), styles["meta_label"]),
        Spacer(1, 0.03 * cm),
        _paragraph(value or "—", styles["meta"]),
    ]


def _content_padding_style(*, bottom: int = 0) -> TableStyle:
    return TableStyle(
        [
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), PAD_H),
            ("RIGHTPADDING", (0, 0), (-1, -1), PAD_H),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), bottom),
        ]
    )


def _build_section_heading(
    *,
    title: str,
    styles: dict[str, ParagraphStyle],
    subtitle: str | None = None,
) -> Table:
    rows: list[list] = [[Paragraph(_text(title), styles["section"])]]
    if subtitle:
        rows.append([Paragraph(_text(subtitle), styles["body_muted"])])
    table = Table(rows, colWidths=[CONTENT_WIDTH])
    table.setStyle(_content_padding_style(bottom=5 if subtitle else 4))
    return table


def _build_padded_paragraph(*, content: Paragraph, bottom: int = 4) -> Table:
    table = Table([[content]], colWidths=[CONTENT_WIDTH])
    table.setStyle(_content_padding_style(bottom=bottom))
    return table


def _table_padding_style(*extra) -> list:
    return [
        ("LEFTPADDING", (0, 0), (-1, -1), PAD_H),
        ("RIGHTPADDING", (0, 0), (-1, -1), PAD_H),
        ("TOPPADDING", (0, 0), (-1, -1), PAD_V),
        ("BOTTOMPADDING", (0, 0), (-1, -1), PAD_V),
        *extra,
    ]


def _build_scan_banner(
    *,
    manufacturing_order_number: str,
    styles: dict[str, ParagraphStyle],
) -> Table:
    """Code-barres seul, sans cadre — numéro OF lisible une seule fois en dessous."""
    barcode = code128.Code128(
        manufacturing_order_number,
        barHeight=1.85 * cm,
        barWidth=1.15,
        humanReadable=False,
    )
    body = [
        barcode,
        Spacer(1, 0.1 * cm),
        Paragraph(manufacturing_order_number, styles["barcode_caption"]),
    ]
    table = Table([[body]], colWidths=[CONTENT_WIDTH])
    table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _build_identity_row(*, payload: dict, styles: dict[str, ParagraphStyle]) -> Table:
    order_summary = payload.get("order_summary") or {}
    customer = payload.get("customer") or {}
    rows = [
        [
            _meta_cell(label="Client", value=str(customer.get("name") or "—"), styles=styles),
            _meta_cell(
                label="Commande",
                value=f"#{order_summary.get('reference', '')}",
                styles=styles,
            ),
            _meta_cell(
                label="Reçue",
                value=str(order_summary.get("created_at_label") or "—"),
                styles=styles,
            ),
        ],
        [
            _meta_cell(
                label="Transport",
                value=str(order_summary.get("shipping_method_name") or "—"),
                styles=styles,
            ),
            _meta_cell(
                label="Livraison souhaitée",
                value=str(order_summary.get("requested_date_label") or "—"),
                styles=styles,
            ),
            "",
        ],
    ]
    table = Table(rows, colWidths=[5.5 * cm, 5.5 * cm, 5.6 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.45, LINE),
                ("SPAN", (1, 1), (2, 1)),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                *_table_padding_style(),
            ]
        )
    )
    return table


def _note_for_document(*, order_summary: dict) -> str:
    note = str(order_summary.get("customer_note") or "").strip()
    if not note:
        return ""
    if order_summary.get("requested_date_label"):
        lines = [
            line
            for line in note.splitlines()
            if not line.strip().lower().startswith("date souhaitée")
        ]
        note = "\n".join(lines).strip()
    return note


def _build_preview_cell(*, preview: bytes | None, styles: dict[str, ParagraphStyle]):
    if preview is None:
        return Paragraph("Aperçu<br/>indisponible", styles["preview_fallback"])

    image = PdfImage(BytesIO(preview))
    max_width = 2.2 * cm
    max_height = 2.2 * cm
    ratio = min(max_width / image.imageWidth, max_height / image.imageHeight)
    image.drawWidth = image.imageWidth * ratio
    image.drawHeight = image.imageHeight * ratio
    image.hAlign = "CENTER"
    return image


def _filename_without_extension(value) -> str:
    filename = str(value or "").strip()
    return Path(filename).stem if filename else ""


def _build_file_qr_code(*, filename: str):
    qr_code = qr.QrCode(
        value=_filename_without_extension(filename) or "upload",
        qrLevel="M",
        qrBorder=4,
        width=2.35 * cm,
        height=2.35 * cm,
    )
    qr_code.hAlign = "CENTER"
    return qr_code


def _build_support_color_cell(*, upload: dict) -> Drawing:
    support_color = str(upload.get("support_color") or "").strip()
    support_color_label = str(upload.get("support_color_label") or "Non renseignée").strip()
    is_multicolor = bool(upload.get("support_color_is_multicolor")) or (
        support_color.casefold() == "#multicolor"
    )

    drawing = Drawing(width=3 * cm, height=0.65 * cm)
    center_x = 0.22 * cm
    center_y = 0.325 * cm
    radius = 0.19 * cm

    if is_multicolor:
        for index, swatch_color in enumerate(MULTICOLOR_SWATCH):
            drawing.add(
                Wedge(
                    center_x,
                    center_y,
                    radius,
                    startangledegrees=index * 90,
                    endangledegrees=(index + 1) * 90,
                    fillColor=swatch_color,
                    strokeColor=swatch_color,
                    strokeWidth=0,
                )
            )
        drawing.add(
            Circle(
                center_x,
                center_y,
                radius,
                fillColor=None,
                strokeColor=MUTED,
                strokeWidth=0.5,
            )
        )
    else:
        try:
            fill_color = colors.HexColor(support_color) if support_color else SURFACE
        except (TypeError, ValueError):
            fill_color = SURFACE
        drawing.add(
            Circle(
                center_x,
                center_y,
                radius,
                fillColor=fill_color,
                strokeColor=MUTED,
                strokeWidth=0.5,
            )
        )

    drawing.add(
        String(
            0.55 * cm,
            0.2 * cm,
            support_color_label or "Non renseignée",
            fontName="Helvetica",
            fontSize=7.5,
            fillColor=INK,
        )
    )
    return drawing


def _build_uploads_table(
    *,
    uploads: list[dict],
    previews: dict[str, bytes],
    styles: dict[str, ParagraphStyle],
) -> Table:
    rows = [
        [
            Paragraph("APERÇU", styles["table_header"]),
            Paragraph("FICHIER", styles["table_header"]),
            Paragraph("QTÉ", styles["table_header"]),
            Paragraph("TAILLE", styles["table_header"]),
            Paragraph("SUPPORT", styles["table_header"]),
        ]
    ]
    table_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        *_table_padding_style(),
    ]

    for row_number, upload in enumerate(uploads, start=1):
        qr_filename = str(upload.get("drive_filename") or upload.get("original_filename") or "")
        file_block = [
            _paragraph(upload.get("original_filename"), styles["body"]),
            Spacer(1, 0.12 * cm),
            _build_file_qr_code(filename=qr_filename),
        ]
        rows.append(
            [
                _build_preview_cell(
                    preview=previews.get(str(upload.get("public_id") or "")),
                    styles=styles,
                ),
                file_block,
                _paragraph(upload.get("quantity") or 1, styles["table_center"]),
                _paragraph(upload.get("dimensions_label") or "—", styles["body"]),
                _build_support_color_cell(upload=upload),
            ]
        )
        table_styles.extend(
            [
                ("BACKGROUND", (0, row_number), (0, row_number), SURFACE),
                ("ALIGN", (0, row_number), (0, row_number), "CENTER"),
                ("ALIGN", (2, row_number), (2, row_number), "CENTER"),
                ("TOPPADDING", (0, row_number), (-1, row_number), 6),
                ("BOTTOMPADDING", (0, row_number), (-1, row_number), 6),
            ]
        )

    table = Table(
        rows,
        colWidths=[2.3 * cm, 7.1 * cm, 1.2 * cm, 2.5 * cm, 3.5 * cm],
        repeatRows=1,
    )
    table.setStyle(TableStyle(table_styles))
    return table


def _build_note(*, note: str, styles: dict[str, ParagraphStyle]) -> Table:
    table = Table(
        [
            [
                _multiline_paragraph(note, styles["body"]),
            ]
        ],
        colWidths=[CONTENT_WIDTH],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF7ED")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#FDBA74")),
                *_table_padding_style(),
            ]
        )
    )
    return table


def _build_checklist(*, styles: dict[str, ParagraphStyle]) -> Table:
    rows = [
        [
            Paragraph("[ ] Fichier", styles["check"]),
            Paragraph("[ ] Qté", styles["check"]),
            Paragraph("[ ] Qualité", styles["check"]),
            Paragraph("Opérateur ____________  Date __/__/____", styles["sign"]),
        ]
    ]
    table = Table(rows, colWidths=[2.8 * cm, 2.4 * cm, 2.8 * cm, 8.6 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                *_table_padding_style(),
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
        rightMargin=1.35 * cm,
        leftMargin=1.35 * cm,
        topMargin=1.1 * cm,
        bottomMargin=1.45 * cm,
        title=manufacturing_order_number,
        author="Prenium DTF",
        subject="OF Atelier",
    )

    story: list = [
        _build_scan_banner(
            manufacturing_order_number=manufacturing_order_number,
            styles=styles,
        ),
        Spacer(1, 0.28 * cm),
        _build_identity_row(payload=payload, styles=styles),
        Spacer(1, 0.28 * cm),
    ]

    uploads = payload.get("uploads") or []
    if uploads:
        previews = ManufacturingOrderPreviewService().build_for_order(order=order)
        story.extend(
            [
                _build_section_heading(title="FICHIERS", styles=styles),
                _build_uploads_table(uploads=uploads, previews=previews, styles=styles),
                Spacer(1, 0.26 * cm),
            ]
        )
    else:
        story.extend(
            [
                _build_section_heading(title="FICHIERS", styles=styles),
                _build_padded_paragraph(
                    content=Paragraph("Aucun fichier.", styles["body"]),
                ),
                Spacer(1, 0.26 * cm),
            ]
        )

    customer_note = _note_for_document(order_summary=payload.get("order_summary") or {})
    if customer_note:
        story.extend(
            [
                _build_section_heading(title="NOTE", styles=styles),
                _build_note(note=customer_note, styles=styles),
                Spacer(1, 0.26 * cm),
            ]
        )

    story.extend(
        [
            _build_section_heading(title="CONTRÔLE", styles=styles),
            _build_checklist(styles=styles),
        ]
    )

    def _footer(canvas, doc):
        _draw_footer(canvas, doc, manufacturing_order_number=manufacturing_order_number)

    pdf.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
