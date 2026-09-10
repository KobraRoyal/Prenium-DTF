"""Placement quality, without rasterizing sources or changing the RIP contract."""

from __future__ import annotations

import hashlib
import json

from django.conf import settings

from apps.gang_sheets.services.cropping import CropBox
from apps.gang_sheets.services.text_items import is_text_item

POLICY_VERSION = 1
RASTER_MIMES = {"image/png", "image/jpeg", "image/tiff"}


class GangSheetPreflightService:
    def evaluate(self, *, sheet, items):
        sources = {
            entry.asset_id: entry
            for entry in sheet.source_assets.filter(customer_id=sheet.customer_id)
        }
        qualities, warnings, blocking, placements = {}, [], [], []
        for item in items:
            version = item.asset_version if item.asset_version_id else None
            source = sources.get(version.asset_id) if version else None
            crop = CropBox.from_source_asset(source) if source else CropBox.full()
            quality = self.item_quality(
                item=item,
                source=source,
                crop=crop,
                expected_customer_id=sheet.customer_id,
            )
            qualities[str(item.public_id)] = quality
            for issue in quality["issues"]:
                row = {**issue, "item_public_ids": [str(item.public_id)]}
                (blocking if issue["level"] == "blocked" else warnings).append(row)
            placements.append(
                {
                    "id": str(item.public_id),
                    "version": str(version.public_id) if version else None,
                    "layout": [
                        str(getattr(item, key))
                        for key in (
                            "x_mm",
                            "y_mm",
                            "width_mm",
                            "height_mm",
                            "rotation",
                        )
                    ],
                    "crop": crop.to_metadata(),
                    "quality": quality,
                }
            )
        canonical = {
            "policy": POLICY_VERSION,
            "sheet": str(sheet.public_id),
            "revision": sheet.revision,
            "items": sorted(placements, key=lambda row: row["id"]),
        }
        fingerprint = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, ensure_ascii=True).encode()
        ).hexdigest()
        return {
            "revision": sheet.revision,
            "fingerprint": fingerprint,
            "policy_version": POLICY_VERSION,
            "state": "blocked" if blocking else "needs_acknowledgement" if warnings else "ready",
            "requires_acknowledgement": bool(warnings),
            "blocking": blocking,
            "warnings": warnings,
            "items": qualities,
        }

    @staticmethod
    def item_quality(*, item, source, crop, expected_customer_id):
        recommended = int(settings.B2B_RECOMMENDED_DPI)
        minimum = int(settings.B2B_MIN_ACCEPTABLE_DPI)
        quality = {
            "effective_dpi": None,
            "resolution_display": "Non déterminé",
            "source_width_px": None,
            "source_height_px": None,
            "source_ratio": None,
            "recommended_dpi": recommended,
            "minimum_dpi": minimum,
            "is_vector": False,
            "information": [],
            "issues": [],
        }
        if is_text_item(item) and item.customer_id == expected_customer_id:
            quality.update(is_vector=True, resolution_display="Vectoriel")
            return quality
        version = item.asset_version if item.asset_version_id else None
        if (
            item.customer_id != expected_customer_id
            or version is None
            or version.customer_id != expected_customer_id
        ):
            quality["issues"].append(
                {
                    "code": "source_unavailable",
                    "level": "blocked",
                    "message": "La source de ce visuel est indisponible.",
                }
            )
            return quality
        quality["analysis_status"] = version.analysis_status
        if version.analysis_status not in {"ready", "warning"}:
            quality["issues"].append(
                {
                    "code": "analysis_unavailable",
                    "level": "blocked",
                    "message": "L’analyse du fichier doit être terminée avant confirmation.",
                }
            )
        analysis = getattr(version, "analysis", None)
        if analysis is not None and analysis.customer_id != item.customer_id:
            analysis = None
        metadata = analysis.metadata if analysis else {}
        quality["is_vector"] = metadata.get("is_pure_vector") is True
        if quality["is_vector"]:
            quality["resolution_display"] = "Vectoriel"
        if source and source.effective_width_mm and source.effective_height_mm:
            quality["source_ratio"] = float(source.effective_width_mm / source.effective_height_mm)
        if analysis and version.mime_type in RASTER_MIMES and not quality["is_vector"]:
            width, height = analysis.image_width, analysis.image_height
            if width and height:
                left, top, right, bottom = crop.pixel_box(width=width, height=height)
                pixel_w, pixel_h = right - left, bottom - top
                quality.update(source_width_px=pixel_w, source_height_px=pixel_h)
                if quality["source_ratio"] is None:
                    quality["source_ratio"] = pixel_w / pixel_h
                if item.width_mm > 0 and item.height_mm > 0:
                    dpi = min(
                        pixel_w * 25.4 / float(item.width_mm),
                        pixel_h * 25.4 / float(item.height_mm),
                    )
                    quality["effective_dpi"] = round(dpi, 2)
                    quality["resolution_display"] = f"{dpi:.0f} DPI"
                    if dpi < recommended:
                        quality["issues"].append(
                            {
                                "code": "low_effective_dpi",
                                "level": "warning",
                                "message": (
                                    f"{dpi:.0f} DPI à la taille d’impression : "
                                    + (
                                        f"pixellisation probable sous {minimum} DPI."
                                        if dpi < minimum
                                        else f"{recommended} DPI recommandés."
                                    )
                                ),
                            }
                        )
        messages = list(analysis.warnings or []) if analysis else []
        # The analysis may report detections separately from its summary warnings.
        for key, message in (
            ("thin_zone", "Des détails fins nécessitent un contrôle atelier."),
            ("semi_transparency", "Des zones semi-transparentes nécessitent un contrôle atelier."),
        ):
            detection = metadata.get(key) or {}
            if detection.get("detected") is True:
                messages.append(message)
        if version.analysis_status == "warning" and not messages:
            messages.append("Le fichier comporte un avertissement d’analyse à vérifier.")
        for message in dict.fromkeys(str(value) for value in messages if value):
            if message.startswith("Document vectoriel ou sans image embarquée") or (
                message.startswith("DPI source absent") and quality["effective_dpi"] is not None
            ):
                quality["information"].append(message)
                continue
            quality["issues"].append(
                {
                    "code": "source_warning",
                    "level": "warning",
                    "message": message,
                }
            )
        return quality
