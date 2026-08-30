from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import Path

from reportlab.graphics.barcode import code128
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from django.core.exceptions import ValidationError

from apps.pod.models import PodRipLot, PodUnit
from apps.pod.services.rip_naming import ascii_token

OF_DIRECTORY = "03_of"
LABEL_DIRECTORY = "04_labels"


def new_scan_identifier() -> str:
    return f"POD-{uuid.uuid4().hex[:10].upper()}"


def _write_of_pdf(*, scan_id: str, title: str, lines: list[str]) -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    width, height = A4
    canvas.setFont("Helvetica-Bold", 16)
    canvas.drawString(20 * mm, height - 25 * mm, "OF POD — pièce")
    canvas.setFont("Helvetica", 11)
    canvas.drawString(20 * mm, height - 35 * mm, title)
    y = height - 50 * mm
    for line in lines:
        canvas.drawString(20 * mm, y, line[:110])
        y -= 7 * mm
    barcode = code128.Code128(scan_id, barHeight=18 * mm, barWidth=1.1, humanReadable=False)
    barcode.drawOn(canvas, 20 * mm, 40 * mm)
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(20 * mm, 32 * mm, scan_id)
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def _write_label_pdf(*, scan_id: str, sku: str) -> bytes:
    buffer = BytesIO()
    width, height = 50 * mm, 30 * mm
    canvas = Canvas(buffer, pagesize=(width, height))
    barcode = code128.Code128(scan_id, barHeight=12 * mm, barWidth=0.7, humanReadable=False)
    barcode.drawOn(canvas, 3 * mm, 12 * mm)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawString(3 * mm, 7 * mm, scan_id)
    canvas.setFont("Helvetica", 6)
    canvas.drawString(3 * mm, 3 * mm, sku[:28])
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


class PodUnitDocumentService:
    def create_units_for_lot(self, *, lot: PodRipLot, planned: list[dict]) -> list[PodUnit]:
        lot_root = Path(lot.nas_relative_path)
        of_dir = Path(self._nas_root()) / lot.nas_relative_path / OF_DIRECTORY
        label_dir = Path(self._nas_root()) / lot.nas_relative_path / LABEL_DIRECTORY
        of_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        seen_items = []
        units = []
        for entry in planned:
            item = entry["work_item"]
            if item.pk in seen_items:
                continue
            seen_items.append(item.pk)
            qty = max(int(item.quantity or 1), 1)
            config = getattr(item.variant, "ids_config", None)
            blank_sku = ""
            if config and config.blank_variant_id:
                blank_sku = config.blank_variant.sku
            slots = ", ".join(
                f"{file_entry['slot'].placement}/{file_entry['slot'].technique.code}"
                for file_entry in planned
                if file_entry["work_item"].pk == item.pk
            )
            for sequence in range(1, qty + 1):
                scan_id = new_scan_identifier()
                of_name = f"{ascii_token(item.shopify_order_number)}_{sequence}_{scan_id}.pdf"
                label_name = f"{scan_id}.pdf"
                of_bytes = _write_of_pdf(
                    scan_id=scan_id,
                    title=f"{item.store.slug} {item.shopify_order_number}",
                    lines=[
                        f"SKU Shopify: {item.variant.sku}",
                        f"Blank: {blank_sku}",
                        f"Slots: {slots}",
                        f"Pièce {sequence}/{qty}",
                    ],
                )
                label_bytes = _write_label_pdf(scan_id=scan_id, sku=item.variant.sku or blank_sku)
                (of_dir / of_name).write_bytes(of_bytes)
                (label_dir / label_name).write_bytes(label_bytes)
                units.append(
                    PodUnit.objects.create(
                        lot=lot,
                        work_item=item,
                        variant=item.variant,
                        sequence=sequence,
                        scan_identifier=scan_id,
                        of_relative_path=str(lot_root / OF_DIRECTORY / of_name),
                        label_relative_path=str(lot_root / LABEL_DIRECTORY / label_name),
                    )
                )
        return units

    def document_path(self, *, unit: PodUnit, kind: str) -> Path:
        relative = unit.of_relative_path if kind == "of" else unit.label_relative_path
        if kind not in {"of", "etiquette"} or not relative:
            raise ValidationError("Document pièce introuvable.")
        root = self._nas_root().resolve()
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValidationError("Chemin document invalide.") from exc
        if not path.is_file():
            raise ValidationError("Fichier NAS introuvable.")
        return path

    def _nas_root(self):
        from django.conf import settings

        return Path(settings.MEDIA_ROOT) / "pod_rip"
