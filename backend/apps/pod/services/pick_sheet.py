from __future__ import annotations

from io import BytesIO

from reportlab.graphics.barcode import code128
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from apps.pod.models import PodPickSession


def write_picking_list_pdf(session: PodPickSession) -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    _draw_picking_pages(canvas, session)
    canvas.save()
    return buffer.getvalue()


def write_zebra_labels_pdf(session: PodPickSession) -> bytes:
    buffer = BytesIO()
    page = (100 * mm, 50 * mm)
    canvas = Canvas(buffer, pagesize=page)
    lines = list(session.lines.filter(voided_at__isnull=True))
    if not lines:
        canvas.setFont("Helvetica", 10)
        canvas.drawString(5 * mm, 25 * mm, "Session vide (lignes annulées)")
        canvas.showPage()
    for index, line in enumerate(lines):
        if index:
            canvas.showPage()
        _draw_zebra_label(canvas, session, line, page)
    canvas.save()
    return buffer.getvalue()


def _draw_picking_pages(canvas: Canvas, session: PodPickSession) -> None:
    width, height = A4
    y = height - 18 * mm
    canvas.setFont("Helvetica-Bold", 16)
    canvas.drawString(15 * mm, y, f"Picking {session.code}")
    y -= 7 * mm
    active = list(session.lines.filter(voided_at__isnull=True))
    canvas.setFont("Helvetica", 10)
    canvas.drawString(
        15 * mm,
        y,
        f"{len(active)} support(s) actifs — les commandes suivantes iront dans une autre session.",
    )
    y -= 10 * mm
    current_key = None
    for line in active:
        key = (line.location_code, line.blank_sku)
        if key != current_key:
            current_key = key
            if y < 35 * mm:
                canvas.showPage()
                y = height - 18 * mm
            canvas.setFont("Helvetica-Bold", 12)
            title = line.blank_name or "Support"
            if line.blank_sku:
                title = f"{title} · {line.blank_sku}"
            canvas.drawString(15 * mm, y, title[:90])
            y -= 5 * mm
            canvas.setFont("Helvetica", 9)
            place = line.location_code or "emplacement non défini"
            canvas.drawString(
                15 * mm,
                y,
                f"{line.size_label} {line.color_name} · {place}".strip(),
            )
            y -= 6 * mm
        if y < 22 * mm:
            canvas.showPage()
            y = height - 18 * mm
        canvas.setFont("Helvetica", 9)
        canvas.drawString(
            18 * mm,
            y,
            f"{line.shopify_order_number}  {line.scan_identifier}  {line.shopify_sku}"[:100],
        )
        y -= 4 * mm
        canvas.setFont("Helvetica", 8)
        canvas.drawString(22 * mm, y, (line.markings or "Aucun marquage")[:110])
        y -= 6 * mm


def _draw_zebra_label(canvas: Canvas, session: PodPickSession, line, page) -> None:
    width, height = page
    canvas.setFillColorRGB(0.1, 0.09, 0.08)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(3 * mm, height - 5 * mm, session.code)
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(3 * mm, height - 11 * mm, line.shopify_order_number[:18])
    canvas.setFont("Helvetica", 8)
    canvas.drawString(3 * mm, height - 16 * mm, (line.blank_sku or line.blank_name)[:22])
    canvas.drawString(
        3 * mm,
        height - 20 * mm,
        f"{line.size_label} {line.color_name} · {line.location_code}".strip()[:28],
    )
    canvas.setFont("Helvetica", 7)
    canvas.drawString(3 * mm, 3 * mm, (line.markings or "Aucun marquage")[:32])
    barcode = code128.Code128(
        line.scan_identifier,
        barHeight=12 * mm,
        barWidth=0.45,
        humanReadable=False,
    )
    barcode.drawOn(canvas, width - 48 * mm, 14 * mm)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawString(width - 48 * mm, 10 * mm, line.scan_identifier)
