from __future__ import annotations

from collections import defaultdict
from io import BytesIO

from django.utils import timezone
from reportlab.graphics.barcode import code128
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from apps.pod.models import PodPickSession


def _active_lines(session: PodPickSession):
    return list(session.lines.filter(voided_at__isnull=True))


def _fit(value: str, font: str, size: float, max_width: float) -> str:
    """Keep catalogue and order text inside a fixed print area."""
    value = " ".join(str(value or "").split())
    if pdfmetrics.stringWidth(value, font, size) <= max_width:
        return value
    while value and pdfmetrics.stringWidth(value + "...", font, size) > max_width:
        value = value[:-1]
    return value.rstrip() + "..." if value else "..."


def write_picking_list_pdf(session: PodPickSession) -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    _draw_picking_pages(canvas, session, _active_lines(session))
    canvas.save()
    return buffer.getvalue()


def write_zebra_labels_pdf(session: PodPickSession) -> bytes:
    buffer = BytesIO()
    page = (100 * mm, 50 * mm)
    canvas = Canvas(buffer, pagesize=page)
    lines = _active_lines(session)
    for index, line in enumerate(lines):
        if index:
            canvas.showPage()
        _draw_zebra_label(canvas, session, line, page)
    if not lines:
        canvas.setFont("Helvetica", 10)
        canvas.drawString(5 * mm, 25 * mm, "Session vide - aucune étiquette active")
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def _draw_picking_pages(canvas: Canvas, session: PodPickSession, lines) -> None:
    width, height = A4
    left, right = 15 * mm, width - 15 * mm
    grouped = defaultdict(list)
    for line in lines:
        key = (
            line.location_code or "EMPLACEMENT NON DÉFINI",
            line.blank_sku or "",
            line.blank_name or "Support",
            line.size_label or "",
            line.color_name or "",
        )
        grouped[key].append(line)
    groups = sorted(grouped.items(), key=lambda item: tuple(part.lower() for part in item[0]))
    page_number = 0

    def new_page():
        nonlocal page_number
        if page_number:
            canvas.showPage()
        page_number += 1
        canvas.setFillColor(colors.HexColor("#111827"))
        canvas.setFont("Helvetica-Bold", 17)
        canvas.drawString(left, height - 20 * mm, "PICKING POD")
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawRightString(right, height - 19 * mm, session.code)
        canvas.setStrokeColor(colors.HexColor("#d1d5db"))
        canvas.line(left, height - 24 * mm, right, height - 24 * mm)
        canvas.setFont("Helvetica", 9)
        created = timezone.localtime(session.created_at).strftime("%d/%m/%Y %H:%M")
        canvas.drawString(left, height - 31 * mm, f"Session du {created}")
        canvas.drawRightString(
            right, height - 31 * mm, f"{len(lines)} pièce(s)  |  {len(groups)} emplacement(s)"
        )
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#4b5563"))
        canvas.drawString(
            left,
            height - 38 * mm,
            "Prélever le support, scanner la pièce et le bac, puis coller l'étiquette.",
        )
        canvas.setStrokeColor(colors.HexColor("#d1d5db"))
        canvas.line(left, 14 * mm, right, 14 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(left, 10 * mm, "Atelier POD - document de prélèvement interne")
        canvas.drawRightString(right, 10 * mm, f"Page {page_number}")
        canvas.setFillColor(colors.HexColor("#111827"))
        return height - 50 * mm

    y = new_page()
    if not groups:
        canvas.setFont("Helvetica", 11)
        canvas.drawString(left, y, "Aucune pièce active dans cette session.")
        return

    for (location, sku, name, size, color), group_lines in groups:
        group_height = 16 * mm
        row_height = 11 * mm
        if y - group_height - row_height < 14 * mm:
            y = new_page()
        canvas.setFillColor(colors.HexColor("#eef2f7"))
        canvas.rect(left, y - 12 * mm, right - left, 13 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor("#111827"))
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(left + 3 * mm, y - 3 * mm, _fit(location, "Helvetica-Bold", 10, 48 * mm))
        canvas.drawRightString(right - 3 * mm, y - 3 * mm, f"{len(group_lines)} pièce(s)")
        canvas.setFont("Helvetica-Bold", 9)
        description = "  |  ".join(part for part in (name, sku, size, color) if part)
        canvas.drawString(
            left + 3 * mm, y - 9 * mm, _fit(description, "Helvetica-Bold", 9, right - left - 6 * mm)
        )
        y -= group_height
        for line in sorted(
            group_lines,
            key=lambda item: (item.shopify_order_number, item.sequence, item.scan_identifier),
        ):
            if y - row_height < 14 * mm:
                y = new_page()
                canvas.setFont("Helvetica-Bold", 9)
                canvas.drawString(
                    left, y, _fit(f"{location} - suite", "Helvetica-Bold", 9, right - left)
                )
                y -= 8 * mm
            canvas.setStrokeColor(colors.HexColor("#6b7280"))
            canvas.rect(left + 1 * mm, y - 1 * mm, 4 * mm, 4 * mm, stroke=1, fill=0)
            canvas.setFillColor(colors.HexColor("#111827"))
            canvas.setFont("Helvetica-Bold", 9)
            canvas.drawString(
                left + 9 * mm, y, _fit(line.shopify_order_number, "Helvetica-Bold", 9, 48 * mm)
            )
            canvas.setFont("Courier-Bold", 9)
            canvas.drawString(
                left + 61 * mm, y, _fit(line.scan_identifier, "Courier-Bold", 9, 58 * mm)
            )
            canvas.setFont("Helvetica", 8)
            canvas.drawRightString(
                right - 2 * mm, y, _fit(line.shopify_sku, "Helvetica", 8, 50 * mm)
            )
            canvas.setFillColor(colors.HexColor("#4b5563"))
            canvas.drawString(
                left + 9 * mm,
                y - 5 * mm,
                _fit(line.markings or "Sans marquage", "Helvetica", 8, right - left - 12 * mm),
            )
            canvas.setStrokeColor(colors.HexColor("#e5e7eb"))
            canvas.line(left + 9 * mm, y - 8 * mm, right, y - 8 * mm)
            canvas.setFillColor(colors.HexColor("#111827"))
            y -= row_height
        y -= 2 * mm


def _draw_zebra_label(canvas: Canvas, session: PodPickSession, line, page) -> None:
    width, height = page
    margin = 3 * mm
    usable = width - 2 * margin
    canvas.setFillColor(colors.black)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawString(margin, height - 5 * mm, "POD / PIÈCE")
    canvas.drawRightString(
        width - margin, height - 5 * mm, _fit(session.code, "Helvetica-Bold", 7, 55 * mm)
    )
    canvas.setStrokeColor(colors.black)
    canvas.line(margin, height - 7 * mm, width - margin, height - 7 * mm)
    product = line.blank_name or line.blank_sku or "Support"
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(margin, height - 12 * mm, _fit(product, "Helvetica-Bold", 11, usable))
    variant = "  /  ".join(
        part for part in (line.blank_sku, line.size_label, line.color_name) if part
    )
    canvas.setFont("Helvetica", 8)
    canvas.drawString(margin, height - 17 * mm, _fit(variant, "Helvetica", 8, usable))
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(
        margin,
        height - 23 * mm,
        _fit(line.location_code or "BAC NON DÉFINI", "Helvetica-Bold", 8, 43 * mm),
    )
    canvas.drawRightString(
        width - margin,
        height - 23 * mm,
        _fit(line.shopify_order_number, "Helvetica-Bold", 8, 46 * mm),
    )
    canvas.setFont("Helvetica", 7)
    canvas.drawString(
        margin, height - 28 * mm, _fit(line.markings or "Sans marquage", "Helvetica", 7, usable)
    )
    barcode = code128.Code128(
        line.scan_identifier, barHeight=11 * mm, barWidth=0.9, humanReadable=False
    )
    scale = min(1, usable / barcode.width)
    canvas.saveState()
    canvas.translate((width - barcode.width * scale) / 2, 7 * mm)
    canvas.scale(scale, 1)
    barcode.drawOn(canvas, 0, 0)
    canvas.restoreState()
    canvas.setFont("Courier-Bold", 8)
    canvas.drawCentredString(
        width / 2, 3 * mm, _fit(line.scan_identifier, "Courier-Bold", 8, usable)
    )
