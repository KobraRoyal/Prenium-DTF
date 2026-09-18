from __future__ import annotations

import json
import logging
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, urlencode
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views import View
from PIL import Image

from apps.customers.models import CustomerMembership
from apps.gang_sheets.forms import GangSheetSiteSettingsForm
from apps.gang_sheets.models import GangSheet, GangSheetSiteSettings
from apps.gang_sheets.services import GangSheetDomainError, GangSheetService
from apps.gang_sheets.services.cropping import (
    CROP_MODE_AUTO,
    CROP_MODE_MANUAL,
    VALID_CROP_MODES,
    CropBox,
    CropInstruction,
    CropValidationError,
    crop_image,
    parse_crop_manifest,
)
from apps.portal.htmx import with_toast
from apps.portal.views_b2b_order_projects import (
    ClientProjectFeatureMixin,
    redirect_after_b2b_checkout,
)
from apps.portal.views_common import StaffDomainPermissionMixin
from apps.uploads.services.asset_preview import AssetPreviewError, AssetPreviewRenderer

gang_sheet_service = GangSheetService()
asset_preview_renderer = AssetPreviewRenderer()
logger = logging.getLogger(__name__)

GANG_SHEET_MAX_FILES_PER_UPLOAD = 5
GANG_SHEET_MAX_TOTAL_UPLOAD_BYTES = 60 * 1024 * 1024
GANG_SHEET_UPLOAD_BATCH_SESSION_PREFIX = "gang_sheet_upload_batch"
GANG_SHEET_UPLOAD_ERROR_SESSION_PREFIX = "gang_sheet_upload_error"


def _decimal_display(value) -> str:
    if value is None:
        return ""
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _quote_quantity(raw) -> int:
    try:
        quantity = int(raw)
    except (TypeError, ValueError):
        quantity = 1
    return max(1, min(quantity, 200))


def _quote_json(quote: dict) -> dict:
    payload = {}
    for key, value in quote.items():
        payload[key] = format(value, "f") if isinstance(value, Decimal) else value
    return payload


def _build_studio_sheet_quote(*, customer, sheet, quantity=1, shipping_method_code=None):
    surface = getattr(sheet, "surface_sqm", None)
    if surface is None or surface <= 0:
        return None
    from apps.orders.services.pricing import OrderPricingService
    from apps.shipping.services.methods import ShippingMethodService

    ShippingMethodService().ensure_default_methods()
    billing_mode = getattr(customer, "default_billing_mode", "deferred")
    try:
        return OrderPricingService().estimate_gang_sheet_quote(
            customer=customer,
            surface_sqm=surface,
            quantity=quantity,
            file_count=1,
            shipping_method_code=shipping_method_code,
            billing_mode=billing_mode,
        )
    except ValidationError:
        return None


def _safe_analysis_error(version) -> str:
    if version and version.analysis_status == version.AnalysisStatus.FAILED:
        return (
            "L’analyse technique n’a pas abouti. Réimportez le fichier ou contactez "
            "l’atelier si le problème persiste."
        )
    return ""


def _safe_analysis_warnings(analysis) -> list[str]:
    if analysis is None:
        return []
    return list(
        dict.fromkeys(
            str(value).strip()[:240] for value in (analysis.warnings or []) if str(value).strip()
        )
    )


def _source_quality_review(*, version, analysis, thin_zone, semi_transparency):
    if version is None or version.analysis_status in {
        version.AnalysisStatus.PENDING,
        version.AnalysisStatus.PROCESSING,
    }:
        level, label, resolution = "pending", "Analyse en cours", "Analyse…"
    elif version.analysis_status == version.AnalysisStatus.FAILED:
        level, label, resolution = "error", "Analyse impossible", "À corriger"
    else:
        metadata = (analysis.metadata or {}) if analysis else {}
        if metadata.get("is_pure_vector") is True:
            level, label, resolution = "good", "Résolution validée", "Vectoriel · OK"
        else:
            dpi_values = [
                float(value)
                for value in (
                    getattr(analysis, "dpi_x", None),
                    getattr(analysis, "dpi_y", None),
                )
                if value is not None
            ]
            dpi = min(dpi_values) if dpi_values else None
            recommended = int(settings.B2B_RECOMMENDED_DPI)
            minimum = int(settings.B2B_MIN_ACCEPTABLE_DPI)
            resolution = f"{dpi:.0f} DPI" if dpi is not None else "DPI à contrôler"
            if dpi is None:
                level, label = "warning", "Résolution à vérifier"
            elif round(dpi) >= recommended:
                level, label = "good", "Résolution source validée"
            elif round(dpi) >= minimum:
                level, label = "warning", "Résolution source acceptable"
            else:
                level, label = "error", "Résolution source insuffisante"
    return {
        "level": level,
        "label": label,
        "resolution_display": resolution,
        "thin_zone": thin_zone,
        "semi_transparency": semi_transparency if analysis is not None else None,
    }


def _format_upload_size(size_bytes: int) -> str:
    size_bytes = max(0, int(size_bytes or 0))
    mebibyte = 1024 * 1024
    kibibyte = 1024
    if size_bytes >= mebibyte:
        value = size_bytes / mebibyte
        label = f"{value:.1f}".rstrip("0").rstrip(".").replace(".", ",")
        return f"{label} Mo"
    if size_bytes >= kibibyte:
        value = size_bytes / kibibyte
        label = f"{value:.1f}".rstrip("0").rstrip(".").replace(".", ",")
        return f"{label} Ko"
    return f"{size_bytes} octet{'s' if size_bytes != 1 else ''}"


def _upload_display_name(uploaded_file) -> str:
    name = Path(str(getattr(uploaded_file, "name", "Visuel") or "Visuel")).name
    return name.replace("\r", " ").replace("\n", " ")[:120] or "Visuel"


def _gang_sheet_upload_rate_limited(*, customer, actor) -> bool:
    customer_id = str(customer.public_id)
    actor_id = str(getattr(actor, "pk", "anonymous"))
    key = f"gang-sheet-upload:{customer_id}:{actor_id}"
    window = int(settings.GANG_SHEET_UPLOAD_RATE_LIMIT_WINDOW_SECONDS)
    maximum = int(settings.GANG_SHEET_UPLOAD_RATE_LIMIT_MAX_REQUESTS)
    if maximum <= 0:
        return False
    if cache.add(key, 1, timeout=window):
        return False
    try:
        attempts = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window)
        return False
    return attempts > maximum


def _gang_sheet_auto_crop_rate_limited(*, customer, actor) -> bool:
    customer_id = str(customer.public_id)
    actor_id = str(getattr(actor, "pk", "anonymous"))
    key = f"gang-sheet-auto-crop:{customer_id}:{actor_id}"
    window = int(settings.GANG_SHEET_AUTO_CROP_RATE_LIMIT_WINDOW_SECONDS)
    maximum = int(settings.GANG_SHEET_AUTO_CROP_RATE_LIMIT_MAX_REQUESTS)
    if maximum <= 0:
        return False
    if cache.add(key, 1, timeout=window):
        return False
    try:
        attempts = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window)
        return False
    return attempts > maximum


def _json_error(error: GangSheetDomainError, *, status=400):
    return JsonResponse(
        {"ok": False, "error": {"code": error.code, "message": error.message, **error.details}},
        status=status,
    )


class ClientGangSheetMixin(ClientProjectFeatureMixin):
    sheet = None

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        return response

    def get_sheet_or_404(self, sheet_public_id):
        sheet = gang_sheet_service.get_customer_sheet(
            customer=self.customer, sheet_public_id=sheet_public_id
        )
        if sheet is None:
            raise Http404
        return sheet

    def require_write_access(self):
        if self.customer_membership.role == CustomerMembership.Role.READONLY:
            raise PermissionDenied

    def preview_url(self, *, sheet, version, overlay="", original=False):
        url = reverse(
            "portal:client-gang-sheet-asset-preview",
            kwargs={
                "customer_public_id": self.customer.public_id,
                "sheet_public_id": sheet.public_id,
                "asset_version_public_id": version.public_id,
            },
        )
        query = {}
        if overlay:
            query["overlay"] = overlay
        if original:
            query["original"] = "1"
        if query:
            return f"{url}?{urlencode(query)}"
        return url

    def source_crop_url(self, *, sheet, source_asset):
        return reverse(
            "portal:client-gang-sheet-source-asset-crop",
            kwargs={
                "customer_public_id": self.customer.public_id,
                "sheet_public_id": sheet.public_id,
                "source_asset_public_id": source_asset.public_id,
            },
        )

    @staticmethod
    def _upload_batch_session_key(sheet):
        return f"{GANG_SHEET_UPLOAD_BATCH_SESSION_PREFIX}:{sheet.public_id}"

    @staticmethod
    def _upload_error_session_key(sheet):
        return f"{GANG_SHEET_UPLOAD_ERROR_SESSION_PREFIX}:{sheet.public_id}"

    def store_import_error(self, *, sheet, message):
        safe_message = " ".join(str(message or "").split())[:400]
        if safe_message:
            self.request.session[self._upload_error_session_key(sheet)] = safe_message

    def consume_import_error(self, *, sheet):
        value = self.request.session.pop(self._upload_error_session_key(sheet), "")
        return value if isinstance(value, str) else ""

    def _recent_upload_batch(self, *, sheet):
        raw = self.request.session.get(self._upload_batch_session_key(sheet), {})
        if not isinstance(raw, dict):
            return {"version_public_ids": set(), "open_results": False}
        values = raw.get("version_public_ids", [])
        if not isinstance(values, list):
            values = []
        return {
            "version_public_ids": {
                str(value) for value in values[:GANG_SHEET_MAX_FILES_PER_UPLOAD]
            },
            "open_results": raw.get("open_results") is True,
        }

    def consume_recent_upload_signal(self, *, sheet, available_version_public_ids):
        key = self._upload_batch_session_key(sheet)
        batch = self._recent_upload_batch(sheet=sheet)
        scoped_ids = batch["version_public_ids"] & set(available_version_public_ids)
        should_open = bool(batch["open_results"] and scoped_ids)
        if should_open:
            self.request.session[key] = {
                "version_public_ids": sorted(scoped_ids),
                "open_results": False,
            }
        elif not scoped_ids:
            self.request.session.pop(key, None)
        return {
            "should_open": should_open,
            "version_public_ids": sorted(scoped_ids),
        }

    def _analysis_detection_context(self, *, sheet, version, analysis, key, overlay):
        metadata = (analysis.metadata or {}) if analysis else {}
        detection = metadata.get(key) or {}
        detected = detection.get("detected") is True
        overlay_field = getattr(analysis, overlay, None) if analysis else None
        overlay_available = bool(
            detected
            and overlay_field
            and version.analysis_status
            in {version.AnalysisStatus.READY, version.AnalysisStatus.WARNING}
        )
        return {
            "detected": detected,
            "coverage_percent": detection.get("coverage_percent"),
            "resolution_limited": detection.get("resolution_limited") is True,
            "overlay_available": overlay_available,
            "overlay_url": (
                self.preview_url(sheet=sheet, version=version, overlay=key)
                if overlay_available
                else ""
            ),
        }

    def asset_gallery_context(self, *, sheet):
        assets = []
        has_pending_assets = False
        recent_batch = self._recent_upload_batch(sheet=sheet)
        available_version_public_ids = set()
        recent_pending = False
        has_ready_auto_placement = False
        usage_by_asset_id = {}
        for item in sheet.items.all():
            if not item.asset_version_id:
                continue
            asset_id = item.asset_version.asset_id
            usage_by_asset_id[asset_id] = usage_by_asset_id.get(asset_id, 0) + 1
        can_edit = self.customer_membership.role != CustomerMembership.Role.READONLY
        can_manage_gallery = can_edit and sheet.status in gang_sheet_service.editable_statuses
        for entry in gang_sheet_service.source_asset_entries(sheet=sheet):
            version = entry.asset.current_version
            if version and (
                version.customer_id != sheet.customer_id or version.asset_id != entry.asset_id
            ):
                version = None
            version_public_id = str(version.public_id) if version else ""
            if version_public_id:
                available_version_public_ids.add(version_public_id)
            usage_count = usage_by_asset_id.get(entry.asset_id, 0)
            is_pending = bool(
                version
                and version.analysis_status
                in {version.AnalysisStatus.PENDING, version.AnalysisStatus.PROCESSING}
            )
            is_ready = bool(
                version
                and version.analysis_status
                in {version.AnalysisStatus.READY, version.AnalysisStatus.WARNING}
            )
            has_pending_assets = has_pending_assets or is_pending
            is_recent = version_public_id in recent_batch["version_public_ids"]
            recent_pending = recent_pending or (is_recent and is_pending)
            analysis = getattr(version, "analysis", None) if version else None
            if analysis and analysis.customer_id != sheet.customer_id:
                analysis = None
            warnings = _safe_analysis_warnings(analysis)
            thin_zone = (
                self._analysis_detection_context(
                    sheet=sheet,
                    version=version,
                    analysis=analysis,
                    key="thin_zone",
                    overlay="thin_zone_overlay",
                )
                if version
                else {}
            )
            semi_transparency = (
                self._analysis_detection_context(
                    sheet=sheet,
                    version=version,
                    analysis=analysis,
                    key="semi_transparency",
                    overlay="semi_transparency_overlay",
                )
                if version
                else {}
            )
            auto_placement_status = entry.auto_placement_status
            ready_for_auto_placement = bool(
                is_ready and auto_placement_status == entry.AutoPlacementStatus.AWAITING_ANALYSIS
            )
            has_ready_auto_placement = has_ready_auto_placement or ready_for_auto_placement
            quality_review = _source_quality_review(
                version=version,
                analysis=analysis,
                thin_zone=thin_zone,
                semi_transparency=semi_transparency,
            )
            assets.append(
                {
                    "source_public_id": str(entry.public_id),
                    "asset_public_id": str(entry.asset.public_id),
                    "public_id": str(version.public_id) if version else "",
                    "name": entry.asset.name,
                    "preview_url": (
                        self.preview_url(sheet=sheet, version=version) if is_ready else ""
                    ),
                    "original_preview_url": (
                        self.preview_url(sheet=sheet, version=version, original=True)
                        if is_ready
                        else ""
                    ),
                    "analysis_status": version.analysis_status if version else "failed",
                    "analysis_label": version.get_analysis_status_display() if version else "Échec",
                    "analysis_error": _safe_analysis_error(version),
                    "analysis_warnings": warnings,
                    "has_analysis_warnings": bool(
                        warnings or thin_zone.get("detected") or semi_transparency.get("detected")
                    ),
                    "source_width_px": analysis.image_width if analysis else None,
                    "source_height_px": analysis.image_height if analysis else None,
                    "dpi_x": analysis.dpi_x if analysis else None,
                    "dpi_y": analysis.dpi_y if analysis else None,
                    "resolution_label": (
                        f"{analysis.image_width} × {analysis.image_height} px"
                        if analysis and analysis.image_width and analysis.image_height
                        else ""
                    ),
                    "dpi_label": (
                        f"{_decimal_display(analysis.dpi_x)} × "
                        f"{_decimal_display(analysis.dpi_y)} DPI"
                        if analysis and analysis.dpi_x is not None and analysis.dpi_y is not None
                        else ""
                    ),
                    "has_alpha": analysis.has_alpha if analysis else None,
                    "probable_white_background": (
                        analysis.probable_white_background if analysis else None
                    ),
                    "thin_zone": thin_zone,
                    "semi_transparency": semi_transparency,
                    "quality_review": quality_review,
                    "is_recent_import": is_recent,
                    "is_ready": is_ready,
                    "width_mm": entry.effective_width_mm,
                    "height_mm": entry.effective_height_mm,
                    "has_crop": entry.has_crop,
                    "crop_mode": CROP_MODE_MANUAL,
                    "crop_x": str(entry.crop_x),
                    "crop_y": str(entry.crop_y),
                    "crop_width": str(entry.crop_width),
                    "crop_height": str(entry.crop_height),
                    "crop_update_url": self.source_crop_url(
                        sheet=sheet,
                        source_asset=entry,
                    ),
                    "expected_revision": sheet.revision,
                    "usage_count": usage_count,
                    "auto_placement_status": auto_placement_status,
                    "auto_placement_error": entry.auto_placement_error,
                    "ready_for_auto_placement": ready_for_auto_placement,
                    "can_crop": can_manage_gallery,
                    "can_remove": can_manage_gallery and usage_count == 0,
                }
            )
        batch_ids = recent_batch["version_public_ids"] & available_version_public_ids
        if recent_batch["version_public_ids"] and not batch_ids:
            self.request.session.pop(self._upload_batch_session_key(sheet), None)
        elif batch_ids and not recent_pending and not recent_batch["open_results"]:
            self.request.session.pop(self._upload_batch_session_key(sheet), None)
        return {
            "sheet": sheet,
            "assets": assets,
            "has_pending_assets": has_pending_assets,
            "has_ready_auto_placement": has_ready_auto_placement,
            "can_edit": can_edit,
            "can_manage_gallery": can_manage_gallery,
            "recent_import_version_public_ids": sorted(batch_ids),
            "has_pending_recent_imports": recent_pending,
        }

    def studio_checkout_context(self, *, sheet, assets):
        placed_files = [asset for asset in assets if asset.get("usage_count")]
        exact_color_required = any(
            (asset.get("thin_zone") or {}).get("detected") for asset in placed_files
        )
        checkout_item = None
        if sheet.project_id:
            checkout_item = sheet.project.items.order_by("sort_order", "created_at").first()
        from apps.shipping.services.methods import ShippingMethodService

        shipping_service = ShippingMethodService()
        shipping_service.ensure_default_methods()
        locks_pickup = shipping_service.customer_locks_shipping_to_pickup(self.customer)
        if locks_pickup:
            selected_shipping_code = "pickup"
            show_shipping_choice = False
            shipping_choice_widget = "hidden"
        else:
            selected_shipping_code = shipping_service.resolve_default_code_for_customer(
                self.customer
            )
            show_shipping_choice = True
            shipping_choice_widget = "radios"
        quantity = _quote_quantity(self.request.GET.get("quantity") or 1)
        gang_sheet_quote = _build_studio_sheet_quote(
            customer=self.customer,
            sheet=sheet,
            quantity=quantity,
            shipping_method_code=selected_shipping_code,
        )
        error_code = str(self.request.GET.get("checkout_error") or "").strip().lower()
        error_messages = {
            "validated_sheet_required": "Confirmez d’abord la composition de la planche.",
            "sheet_items_required": "Ajoutez au moins un visuel avant de commander.",
            "analyses_not_ready": (
                "L’analyse d’un visuel n’est pas terminée. Réessayez dans un instant."
            ),
            "support_color_required": "Choisissez Multicouleur ou la couleur du support.",
            "invalid_support_color": (
                "Couleur du support invalide. Utilisez #RRGGBB ou Multicouleur."
            ),
            "analysis_not_ready": (
                "Le fichier HD est encore en analyse. Patientez quelques secondes puis réessayez."
            ),
            "gang_sheet_drive_sync_required": (
                self.request.GET.get("checkout_message")
                or (
                    "La sauvegarde sécurisée du PDF HD est encore en cours. "
                    "Réessayez dans un instant."
                )
            ),
            "validation": (
                self.request.GET.get("checkout_message")
                or "Impossible de finaliser la commande. Réessayez."
            ),
            "delivery_address_required": "Indiquez l’adresse de livraison avant de confirmer.",
            "delivery_recipient_required": (
                "Indiquez le destinataire, un email de suivi et le n° de voie."
            ),
            "invalid_requested_date": "La date souhaitée est invalide.",
        }
        from apps.customers.services.company_profile import (
            COUNTRY_LABELS,
            CompanyProfileService,
            format_customer_address,
            shipping_same_as_billing,
        )
        from apps.portal.views_payments import (
            available_payment_providers,
            default_online_provider,
        )

        payment_providers = available_payment_providers()
        online_provider = default_online_provider(self.customer)
        shipping_snapshot = {}
        if sheet.project_id:
            shipping_snapshot = sheet.project.shipping_address or {}
        delivery_defaults = CompanyProfileService().checkout_delivery_defaults(
            self.customer,
            shipping_snapshot,
        )
        return {
            "studio_checkout_files": placed_files,
            "studio_checkout_item": checkout_item,
            "studio_checkout_exact_color": exact_color_required,
            "studio_inline_checkout": True,
            "shipping_methods": shipping_service.list_active_methods(),
            "selected_shipping_method_code": selected_shipping_code,
            "show_shipping_choice": show_shipping_choice,
            "shipping_choice_widget": shipping_choice_widget,
            "shipping_locked_to_pickup": locks_pickup,
            "gang_sheet_quote": gang_sheet_quote,
            "studio_payment_providers": payment_providers,
            "studio_online_provider": online_provider,
            "studio_billing_address": format_customer_address(self.customer, kind="billing"),
            "studio_shipping_address": format_customer_address(self.customer, kind="shipping"),
            "studio_shipping_same_as_billing": shipping_same_as_billing(self.customer),
            "studio_billing_complete": bool(
                (self.customer.billing_address_line1 or "").strip()
                and (self.customer.billing_postal_code or "").strip()
                and (self.customer.billing_city or "").strip()
            ),
            "studio_country_choices": list(COUNTRY_LABELS.items()),
            "studio_shipping_contact_name": delivery_defaults["name"],
            "studio_shipping_email": delivery_defaults["email"],
            "studio_shipping_phone": delivery_defaults["phone"],
            "studio_shipping_company": delivery_defaults["company_name"],
            "studio_shipping_house_number": delivery_defaults["house_number"],
            "studio_checkout_error": error_messages.get(error_code, ""),
            "studio_checkout_error_code": error_code,
        }


class ClientGangSheetListCreateView(ClientGangSheetMixin, View):
    template_name = "portal/client/gang_sheets/list.html"

    def paginated_sheets(self, request):
        page = Paginator(
            gang_sheet_service.list_customer_sheets(self.customer),
            settings.GANG_SHEET_LIST_PAGE_SIZE,
        ).get_page(request.GET.get("page"))
        sheets = gang_sheet_service.attach_can_delete(list(page.object_list))
        return sheets, page

    def get(self, request, customer_public_id):
        sheets, page = self.paginated_sheets(request)
        return render(
            request,
            self.template_name,
            self.context(
                sheets=sheets,
                page_obj=page,
                can_edit=self.customer_membership.role != CustomerMembership.Role.READONLY,
                nav_key="client-gang-sheets",
            ),
        )

    def post(self, request, customer_public_id):
        self.require_write_access()
        try:
            sheet = gang_sheet_service.create_sheet(
                customer=self.customer,
                actor=request.user,
                name=request.POST.get("name", ""),
            )
        except GangSheetDomainError as error:
            sheets, page = self.paginated_sheets(request)
            return with_toast(
                render(
                    request,
                    self.template_name,
                    self.context(
                        sheets=sheets,
                        page_obj=page,
                        can_edit=True,
                        form_error=error.message,
                        nav_key="client-gang-sheets",
                    ),
                    status=400,
                ),
                error.message,
                "error",
            )
        return HttpResponseRedirect(
            reverse(
                "portal:client-gang-sheet-editor",
                kwargs={
                    "customer_public_id": self.customer.public_id,
                    "sheet_public_id": sheet.public_id,
                },
            )
        )


class ClientGangSheetEditorView(ClientGangSheetMixin, View):
    template_name = "portal/client/gang_sheets/editor.html"

    def get(self, request, customer_public_id, sheet_public_id):
        sheet = self.get_sheet_or_404(sheet_public_id)
        sheet.can_delete = gang_sheet_service.can_client_delete(sheet)
        state = gang_sheet_service.serialize_sheet(
            sheet,
            preview_url_resolver=lambda version: self.preview_url(sheet=sheet, version=version),
        )
        gallery_context = self.asset_gallery_context(sheet=sheet)
        recent_import_batch = self.consume_recent_upload_signal(
            sheet=sheet,
            available_version_public_ids={
                asset["public_id"] for asset in gallery_context["assets"]
            },
        )
        import_error = self.consume_import_error(sheet=sheet)
        prep_fee = "0.00"
        try:
            from apps.orders.services.pricing import OrderPricingService

            prep_fee = str(
                OrderPricingService().resolve_file_preparation_fee_per_file(customer=self.customer)
            )
        except Exception:
            prep_fee = "0.00"
        return render(
            request,
            self.template_name,
            self.context(
                gang_sheet_state=state,
                **gallery_context,
                gang_sheet_import_batch=recent_import_batch,
                gang_sheet_import_error=import_error,
                reopen_gang_sheet_import_results=recent_import_batch["should_open"],
                reopen_gang_sheet_import_dialog=bool(
                    import_error or recent_import_batch["should_open"]
                ),
                can_create_order=sheet.status == GangSheet.Status.VALIDATED
                and bool(sheet.final_file),
                create_order_project_url=reverse(
                    "portal:client-gang-sheet-create-order-project",
                    kwargs={
                        "customer_public_id": self.customer.public_id,
                        "sheet_public_id": sheet.public_id,
                    },
                ),
                gang_sheet_prep_fee_eur=prep_fee,
                gang_sheet_upload_max_bytes=settings.ORDER_UPLOAD_MAX_BYTES,
                gang_sheet_upload_max_size_label=_format_upload_size(
                    settings.ORDER_UPLOAD_MAX_BYTES
                ),
                gang_sheet_upload_max_files=GANG_SHEET_MAX_FILES_PER_UPLOAD,
                gang_sheet_upload_max_total_bytes=GANG_SHEET_MAX_TOTAL_UPLOAD_BYTES,
                gang_sheet_upload_max_total_size_label=_format_upload_size(
                    GANG_SHEET_MAX_TOTAL_UPLOAD_BYTES
                ),
                nav_key="client-gang-sheets",
                **self.studio_checkout_context(
                    sheet=sheet,
                    assets=gallery_context["assets"],
                ),
            ),
        )


class ClientGangSheetAssetGalleryView(ClientGangSheetMixin, View):
    template_name = "portal/client/gang_sheets/partials/asset_gallery.html"
    import_results_template_name = "portal/client/gang_sheets/partials/import_analysis_results.html"

    def get(self, request, customer_public_id, sheet_public_id):
        sheet = self.get_sheet_or_404(sheet_public_id)
        template_name = (
            self.import_results_template_name
            if request.GET.get("view") == "import-results"
            else self.template_name
        )
        response = render(
            request,
            template_name,
            self.context(**self.asset_gallery_context(sheet=sheet)),
        )
        response["Cache-Control"] = "private, no-store"
        return response


class ClientGangSheetSourceAssetRemoveView(ClientGangSheetMixin, View):
    template_name = "portal/client/gang_sheets/partials/asset_gallery.html"

    def post(
        self,
        request,
        customer_public_id,
        sheet_public_id,
        source_asset_public_id,
    ):
        self.require_write_access()
        sheet = self.get_sheet_or_404(sheet_public_id)
        message = "Visuel retiré de la galerie."
        variant = "success"
        try:
            gang_sheet_service.remove_source_asset(
                sheet=sheet,
                source_asset_public_id=source_asset_public_id,
                actor=request.user,
                source="client_portal",
            )
        except GangSheetDomainError as error:
            message = error.message
            variant = "error"

        if request.headers.get("HX-Request"):
            refreshed_sheet = self.get_sheet_or_404(sheet_public_id)
            response = render(
                request,
                self.template_name,
                self.context(**self.asset_gallery_context(sheet=refreshed_sheet)),
                status=400 if variant == "error" else 200,
            )
            response["Cache-Control"] = "private, no-store"
            return with_toast(response, message, variant)

        editor_url = reverse(
            "portal:client-gang-sheet-editor",
            kwargs={
                "customer_public_id": self.customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        )
        return with_toast(HttpResponseRedirect(editor_url), message, variant)


class ClientGangSheetSourceAssetCropView(ClientGangSheetMixin, View):
    def post(
        self,
        request,
        customer_public_id,
        sheet_public_id,
        source_asset_public_id,
    ):
        self.require_write_access()
        sheet = self.get_sheet_or_404(sheet_public_id)
        crop_mode = request.POST.get("crop_mode", CROP_MODE_MANUAL)
        if crop_mode not in VALID_CROP_MODES:
            response = _json_error(
                GangSheetDomainError(
                    "INVALID_CROP_MODE",
                    "Le mode de recadrage est invalide.",
                ),
            )
            response["Cache-Control"] = "private, no-store"
            return response
        if crop_mode == CROP_MODE_AUTO and _gang_sheet_auto_crop_rate_limited(
            customer=self.customer,
            actor=request.user,
        ):
            response = _json_error(
                GangSheetDomainError(
                    "AUTO_CROP_RATE_LIMITED",
                    "Trop de recadrages automatiques ont été lancés. Patientez avant de réessayer.",
                ),
                status=429,
            )
            response["Retry-After"] = str(settings.GANG_SHEET_AUTO_CROP_RATE_LIMIT_WINDOW_SECONDS)
            response["Cache-Control"] = "private, no-store"
            return response
        crop = None
        if crop_mode != CROP_MODE_AUTO:
            try:
                crop = CropBox.from_values(
                    x=request.POST.get("crop_x"),
                    y=request.POST.get("crop_y"),
                    width=request.POST.get("crop_width"),
                    height=request.POST.get("crop_height"),
                )
            except CropValidationError as error:
                response = _json_error(
                    GangSheetDomainError("INVALID_CROP", str(error)),
                )
                response["Cache-Control"] = "private, no-store"
                return response
        try:
            updated_sheet, source_asset = gang_sheet_service.update_source_asset_crop(
                sheet=sheet,
                source_asset_public_id=source_asset_public_id,
                crop=crop,
                crop_mode=crop_mode,
                expected_revision=request.POST.get("expected_revision"),
                actor=request.user,
                source="client_portal",
            )
        except GangSheetDomainError as error:
            response = _json_error(
                error,
                status=404 if error.code == "SOURCE_ASSET_NOT_FOUND" else 400,
            )
            response["Cache-Control"] = "private, no-store"
            return response

        response = JsonResponse(
            {
                "ok": True,
                "revision": updated_sheet.revision,
                "crop": CropBox.from_source_asset(source_asset).to_metadata(),
                "width_mm": (
                    str(source_asset.effective_width_mm)
                    if source_asset.effective_width_mm is not None
                    else None
                ),
                "height_mm": (
                    str(source_asset.effective_height_mm)
                    if source_asset.effective_height_mm is not None
                    else None
                ),
            }
        )
        response["Cache-Control"] = "private, no-store"
        return response


class ClientGangSheetDeleteView(ClientGangSheetMixin, View):
    def post(self, request, customer_public_id, sheet_public_id):
        self.require_write_access()
        sheet = self.get_sheet_or_404(sheet_public_id)
        list_url = reverse(
            "portal:client-gang-sheet-list-create",
            kwargs={"customer_public_id": self.customer.public_id},
        )
        return_url = list_url
        if request.POST.get("return_to") == "editor":
            return_url = reverse(
                "portal:client-gang-sheet-editor",
                kwargs={
                    "customer_public_id": self.customer.public_id,
                    "sheet_public_id": sheet.public_id,
                },
            )
        try:
            gang_sheet_service.delete_sheet(
                sheet=sheet,
                actor=request.user,
                source="client_portal",
            )
        except GangSheetDomainError as error:
            return with_toast(HttpResponseRedirect(return_url), error.message, "error")
        return with_toast(
            HttpResponseRedirect(list_url),
            "Planche DTF supprimée.",
            "success",
        )


class ClientGangSheetAssetUploadView(ClientGangSheetMixin, View):
    max_files_per_request = GANG_SHEET_MAX_FILES_PER_UPLOAD

    def post(self, request, customer_public_id, sheet_public_id):
        self.require_write_access()
        sheet = self.get_sheet_or_404(sheet_public_id)
        if _gang_sheet_upload_rate_limited(customer=self.customer, actor=request.user):
            response = self._reject(
                request=request,
                sheet=sheet,
                message="Trop d’imports ont été lancés. Patientez avant de réessayer.",
                status=429,
            )
            response["Retry-After"] = str(settings.GANG_SHEET_UPLOAD_RATE_LIMIT_WINDOW_SECONDS)
            return response
        uploaded_files = request.FILES.getlist("files")
        if not uploaded_files:
            return self._reject(
                request=request,
                sheet=sheet,
                message="Sélectionnez au moins un fichier.",
            )
        if len(uploaded_files) > self.max_files_per_request:
            return self._reject(
                request=request,
                sheet=sheet,
                message=f"Importez au maximum {self.max_files_per_request} fichiers à la fois.",
            )
        total_size_bytes = sum(
            int(getattr(uploaded_file, "size", 0) or 0) for uploaded_file in uploaded_files
        )
        if total_size_bytes > GANG_SHEET_MAX_TOTAL_UPLOAD_BYTES:
            return self._reject(
                request=request,
                sheet=sheet,
                message=(
                    "La sélection dépasse la limite de "
                    f"{_format_upload_size(GANG_SHEET_MAX_TOTAL_UPLOAD_BYTES)} par import. "
                    "Réduisez le nombre de fichiers puis réessayez."
                ),
            )
        oversized_file = next(
            (
                uploaded_file
                for uploaded_file in uploaded_files
                if int(getattr(uploaded_file, "size", 0) or 0) > settings.ORDER_UPLOAD_MAX_BYTES
            ),
            None,
        )
        if oversized_file is not None:
            display_name = _upload_display_name(oversized_file)
            logger.warning(
                "Gang Sheet source upload rejected before asset creation: file too large",
                extra={
                    "customer_public_id": str(self.customer.public_id),
                    "gang_sheet_public_id": str(sheet.public_id),
                    "upload_size_bytes": int(getattr(oversized_file, "size", 0) or 0),
                    "upload_max_bytes": settings.ORDER_UPLOAD_MAX_BYTES,
                },
            )
            return self._reject(
                request=request,
                sheet=sheet,
                message=(
                    f"{display_name} dépasse la limite de "
                    f"{_format_upload_size(settings.ORDER_UPLOAD_MAX_BYTES)} par fichier. "
                    "Réduisez ou compressez le visuel avant de réessayer."
                ),
            )
        try:
            crops = parse_crop_manifest(
                request.POST.get("crop_manifest", ""),
                file_count=len(uploaded_files),
            )
        except CropValidationError as error:
            return self._reject(
                request=request,
                sheet=sheet,
                message=str(error),
            )
        uploads = []
        for index, uploaded_file in enumerate(uploaded_files):
            instruction = crops.get(
                index,
                CropInstruction(mode=CROP_MODE_MANUAL, crop=CropBox.full()),
            )
            uploads.append((uploaded_file, instruction.crop, instruction.mode))
        try:
            imported = gang_sheet_service.upload_source_assets(
                sheet=sheet,
                actor=request.user,
                uploads=uploads,
            )
        except GangSheetDomainError as error:
            return self._reject(request=request, sheet=sheet, message=error.message)
        else:
            request.session.pop(self._upload_error_session_key(sheet), None)
            request.session[self._upload_batch_session_key(sheet)] = {
                "version_public_ids": [str(version.public_id) for _source, version in imported],
                "open_results": True,
            }
            message = f"{len(imported)} fichier(s) importé(s). Analyse technique lancée."
        return with_toast(HttpResponseRedirect(self._editor_url(sheet)), message, "success")

    def _reject(self, *, request, sheet, message, status=302):
        self.store_import_error(sheet=sheet, message=message)
        response = with_toast(
            HttpResponseRedirect(self._editor_url(sheet)),
            message,
            "error",
        )
        response.status_code = status
        return response

    def _editor_url(self, sheet):
        return reverse(
            "portal:client-gang-sheet-editor",
            kwargs={
                "customer_public_id": self.customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        )


class ClientGangSheetStateView(ClientGangSheetMixin, View):
    def get(self, request, customer_public_id, sheet_public_id):
        sheet = self.get_sheet_or_404(sheet_public_id)
        return JsonResponse(
            {
                "ok": True,
                "sheet": gang_sheet_service.serialize_sheet(
                    sheet,
                    preview_url_resolver=lambda version: self.preview_url(
                        sheet=sheet, version=version
                    ),
                ),
            }
        )


class ClientGangSheetAutoPlaceReadySourcesView(ClientGangSheetMixin, View):
    def post(self, request, customer_public_id, sheet_public_id):
        self.require_write_access()
        sheet = self.get_sheet_or_404(sheet_public_id)
        retry_source_public_id = request.POST.get("retry_source_public_id") or None
        if retry_source_public_id:
            try:
                retry_source_public_id = UUID(retry_source_public_id)
            except (TypeError, ValueError, AttributeError):
                return _json_error(
                    GangSheetDomainError(
                        "INVALID_SOURCE_ASSET_ID", "L’identifiant du visuel est invalide."
                    ),
                    status=400,
                )
        try:
            sheet, items, no_space_count = gang_sheet_service.auto_place_ready_sources(
                sheet=sheet,
                expected_revision=request.POST.get("expected_revision"),
                retry_source_public_id=retry_source_public_id,
                actor=request.user,
            )
        except GangSheetDomainError as error:
            return _json_error(error, status=409 if error.code == "STALE_REVISION" else 400)
        return JsonResponse(
            {
                "ok": True,
                "created_count": len(items),
                "no_space_count": no_space_count,
                "revision": sheet.revision,
            }
        )


class ClientGangSheetLayoutView(ClientGangSheetMixin, View):
    def post(self, request, customer_public_id, sheet_public_id):
        self.require_write_access()
        sheet = self.get_sheet_or_404(sheet_public_id)
        try:
            body = json.loads(request.body or b"{}")
            if not isinstance(body, dict):
                raise GangSheetDomainError("INVALID_JSON", "Le corps JSON doit être un objet.")
            if not isinstance(body.get("items"), list):
                raise GangSheetDomainError(
                    "INVALID_LAYOUT", "La liste des occurrences est invalide."
                )
            sheet, issues = gang_sheet_service.save_layout(
                sheet=sheet,
                payload=body.get("items", []),
                expected_revision=body.get("revision"),
                actor=request.user,
            )
        except (json.JSONDecodeError, UnicodeDecodeError, GangSheetDomainError) as error:
            if isinstance(error, GangSheetDomainError):
                return _json_error(error, status=409 if error.code == "STALE_REVISION" else 400)
            return _json_error(GangSheetDomainError("INVALID_JSON", "Requête invalide."))
        return JsonResponse(
            {
                "ok": True,
                "revision": sheet.revision,
                "height_mm": float(sheet.height_mm),
                "surface_sqm": float(sheet.surface_sqm),
                "estimated_price_eur": float(sheet.estimated_price_eur),
                "issues": issues,
            }
        )


class ClientGangSheetAddItemView(ClientGangSheetMixin, View):
    def post(self, request, customer_public_id, sheet_public_id):
        self.require_write_access()
        sheet = self.get_sheet_or_404(sheet_public_id)
        try:
            if request.POST.get("kind") == "text":
                item = gang_sheet_service.add_text_item(
                    sheet=sheet,
                    actor=request.user,
                    content=request.POST.get("text_content"),
                    font=request.POST.get("text_font"),
                    size_mm=request.POST.get("text_size_mm"),
                    color=request.POST.get("text_color"),
                    align=request.POST.get("text_align"),
                    bold=request.POST.get("text_bold"),
                )
                return JsonResponse(
                    {
                        "ok": True,
                        "created_count": 1,
                        "item_public_id": str(item.public_id),
                        "kind": "text",
                    },
                    status=201,
                )
            items = gang_sheet_service.add_occurrences(
                sheet=sheet,
                asset_version_public_id=request.POST.get("asset_version_public_id"),
                quantity=request.POST.get("quantity", 1),
                auto_place=request.POST.get("auto_place") == "1",
                actor=request.user,
            )
        except GangSheetDomainError as error:
            return _json_error(error)
        return JsonResponse({"ok": True, "created_count": len(items)}, status=201)


class ClientGangSheetSourceQuantityView(ClientGangSheetMixin, View):
    def post(self, request, customer_public_id, sheet_public_id, source_asset_public_id):
        self.require_write_access()
        sheet = self.get_sheet_or_404(sheet_public_id)
        try:
            updated_sheet, quantity = gang_sheet_service.set_source_quantity(
                sheet=sheet,
                source_asset_public_id=source_asset_public_id,
                quantity=request.POST.get("quantity"),
                expected_revision=request.POST.get("expected_revision"),
                actor=request.user,
            )
        except GangSheetDomainError as error:
            return _json_error(error, status=409 if error.code == "STALE_REVISION" else 400)
        return JsonResponse({"ok": True, "quantity": quantity, "revision": updated_sheet.revision})


class ClientGangSheetBatchDeleteItemsView(ClientGangSheetMixin, View):
    def post(self, request, customer_public_id, sheet_public_id):
        self.require_write_access()
        sheet = self.get_sheet_or_404(sheet_public_id)
        try:
            body = json.loads(request.body or b"{}")
            if not isinstance(body, dict):
                raise GangSheetDomainError("INVALID_JSON", "Requête invalide.")
            deleted_count = gang_sheet_service.delete_occurrences(
                sheet=sheet,
                item_public_ids=body.get("item_public_ids"),
                actor=request.user,
            )
        except (json.JSONDecodeError, UnicodeDecodeError, GangSheetDomainError) as error:
            if isinstance(error, GangSheetDomainError):
                return _json_error(error)
            return _json_error(GangSheetDomainError("INVALID_JSON", "Requête invalide."))
        return JsonResponse({"ok": True, "deleted_count": deleted_count})


class ClientGangSheetItemActionView(ClientGangSheetMixin, View):
    def post(self, request, customer_public_id, sheet_public_id, item_public_id, action):
        self.require_write_access()
        sheet = self.get_sheet_or_404(sheet_public_id)
        try:
            if action == "duplicate":
                gang_sheet_service.duplicate_occurrence(
                    sheet=sheet,
                    item_public_id=item_public_id,
                    expected_revision=request.POST.get("expected_revision"),
                    actor=request.user,
                )
            elif action == "delete":
                gang_sheet_service.delete_occurrence(
                    sheet=sheet, item_public_id=item_public_id, actor=request.user
                )
            elif action == "grid":
                gang_sheet_service.repeat_occurrence_grid(
                    sheet=sheet,
                    item_public_id=item_public_id,
                    rows=request.POST.get("rows"),
                    columns=request.POST.get("columns"),
                    spacing_x_mm=request.POST.get("spacing_x_mm", sheet.item_spacing_mm),
                    spacing_y_mm=request.POST.get("spacing_y_mm", sheet.item_spacing_mm),
                    actor=request.user,
                )
            else:
                raise Http404
        except GangSheetDomainError as error:
            return _json_error(error, status=409 if error.code == "STALE_REVISION" else 400)
        return JsonResponse({"ok": True})


class ClientGangSheetWorkflowActionView(ClientGangSheetMixin, View):
    def post(self, request, customer_public_id, sheet_public_id, action):
        self.require_write_access()
        sheet = self.get_sheet_or_404(sheet_public_id)
        try:
            if action == "auto-place":
                gang_sheet_service.auto_place(
                    sheet=sheet,
                    actor=request.user,
                    spacing_x_mm=request.POST.get("spacing_x_mm"),
                    spacing_y_mm=request.POST.get("spacing_y_mm"),
                )
                message = "Espacement appliqué et planche réorganisée."
            elif action == "render":
                gang_sheet_service.request_render(sheet=sheet, actor=request.user)
                message = "Rendu haute définition lancé."
            elif action == "validate":
                if not request.POST.get("expected_revision") or not request.POST.get(
                    "preflight_fingerprint"
                ):
                    raise GangSheetDomainError(
                        "STALE_PREFLIGHT", "Actualisez le contrôle qualité avant de confirmer."
                    )
                gang_sheet_service.validate_sheet(
                    sheet=sheet,
                    actor=request.user,
                    expected_revision=request.POST.get("expected_revision"),
                    preflight_fingerprint=request.POST.get("preflight_fingerprint", ""),
                    acknowledge_quality=request.POST.get("acknowledge_quality") == "true",
                )
                message = "Composition confirmée. Le contrôle du PDF reste requis à la commande."
            elif action == "create-order-project":
                project = gang_sheet_service.create_order_project(
                    sheet=sheet,
                    actor=request.user,
                    quantity=request.POST.get("quantity", 1),
                    name=request.POST.get("name"),
                    requested_date=request.POST.get("requested_date"),
                    customer_comment=request.POST.get("customer_comment"),
                )
                return JsonResponse(
                    {
                        "ok": True,
                        "message": "Commande préparée.",
                        "redirect_url": reverse(
                            "portal:client-order-project-detail",
                            kwargs={
                                "customer_public_id": self.customer.public_id,
                                "project_public_id": project.public_id,
                            },
                        ),
                    }
                )
            else:
                raise Http404
        except GangSheetDomainError as error:
            return _json_error(error)
        return JsonResponse({"ok": True, "message": message})


class ClientGangSheetQuoteView(ClientGangSheetMixin, View):
    def get(self, request, customer_public_id, sheet_public_id):
        sheet = self.get_sheet_or_404(sheet_public_id)
        quote = _build_studio_sheet_quote(
            customer=self.customer,
            sheet=sheet,
            quantity=_quote_quantity(request.GET.get("quantity")),
            shipping_method_code=((request.GET.get("shipping_method_code") or "").strip() or None),
        )
        return JsonResponse({"ok": True, "quote": _quote_json(quote) if quote else None})


class ClientGangSheetCheckoutView(ClientGangSheetMixin, View):
    def post(self, request, customer_public_id, sheet_public_id):
        self.require_write_access()
        sheet = self.get_sheet_or_404(sheet_public_id)
        editor_url = reverse(
            "portal:client-gang-sheet-editor",
            kwargs={
                "customer_public_id": self.customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        )
        if sheet.order_id:
            from apps.billing.services.production_payment_gate import (
                order_awaits_client_payment,
            )

            if order_awaits_client_payment(sheet.order):
                return redirect_after_b2b_checkout(
                    request=request,
                    customer=self.customer,
                    order=sheet.order,
                    source="client_portal.studio_checkout_pay",
                    requested_provider=(request.POST.get("provider") or "").strip(),
                )
            return HttpResponseRedirect(
                reverse(
                    "portal:client-order-detail",
                    kwargs={
                        "customer_public_id": self.customer.public_id,
                        "order_public_id": sheet.order.public_id,
                    },
                )
            )
        try:
            shipping_code = (request.POST.get("shipping_method_code") or "").strip() or None
            delivery_destination = (
                (request.POST.get("delivery_destination") or "billing").strip().lower()
            )
            same_as_billing = delivery_destination != "other"
            delivery_payload = {
                "shipping_address_line1": request.POST.get("shipping_address_line1", ""),
                "shipping_address_line2": request.POST.get("shipping_address_line2", ""),
                "shipping_postal_code": request.POST.get("shipping_postal_code", ""),
                "shipping_city": request.POST.get("shipping_city", ""),
                "shipping_country": request.POST.get("shipping_country", ""),
            }
            recipient_payload = {
                "name": request.POST.get("shipping_contact_name", ""),
                "email": request.POST.get("shipping_email", ""),
                "phone": request.POST.get("shipping_phone", ""),
                "company_name": request.POST.get("shipping_company_name", ""),
                "house_number": request.POST.get("shipping_house_number", ""),
            }
            delivery_snapshot = None
            if shipping_code != "pickup":
                from apps.customers.services.company_profile import CompanyProfileService

                profile = CompanyProfileService()
                customer = profile.apply_checkout_delivery(
                    customer=self.customer,
                    actor=request.user,
                    same_as_billing=same_as_billing,
                    payload=delivery_payload,
                    source="client_portal.studio_checkout",
                )
                self.customer = customer
                delivery_snapshot = profile.build_checkout_delivery_snapshot(
                    customer=customer,
                    payload=recipient_payload,
                )
            order = gang_sheet_service.checkout_studio_sheet(
                sheet=sheet,
                actor=request.user,
                customer_membership=self.customer_membership,
                support_color_hex=request.POST.get("support_color_hex", ""),
                support_color_multicolor=request.POST.get("support_color_multicolor"),
                quantity=request.POST.get("quantity") or 1,
                shipping_method_code=shipping_code,
                billing_mode=str(
                    getattr(self.customer, "default_billing_mode", "deferred")
                ).strip(),
                name=request.POST.get("name"),
                requested_date=request.POST.get("requested_date"),
                customer_comment=request.POST.get("customer_comment"),
                delivery_address=delivery_snapshot if shipping_code != "pickup" else None,
                source="client_portal.studio_checkout",
            )
        except GangSheetDomainError as error:
            submit_error = error.code.lower()
            if error.code == "GANG_SHEET_DRIVE_SYNC_REQUIRED":
                from apps.gang_sheets.services.drive import GangSheetDriveSyncService

                if sheet.final_file:
                    GangSheetDriveSyncService().schedule_sync(
                        sheet=sheet,
                        actor=request.user,
                        source="client_portal.studio_checkout_retry",
                    )
                message = quote(error.message or "")
                return HttpResponseRedirect(
                    f"{editor_url}?checkout_error={submit_error}&checkout_message={message}"
                )
            return HttpResponseRedirect(f"{editor_url}?checkout_error={submit_error}")
        except ValidationError as error:
            messages = "; ".join(getattr(error, "messages", []) or [str(error)])
            error_codes = [
                getattr(error, "code", None),
                *[getattr(item, "code", None) for item in getattr(error, "error_list", [])],
            ]
            checkout_error = "validation"
            if "delivery_recipient_required" in error_codes:
                checkout_error = "delivery_recipient_required"
            elif "delivery_address_required" in error_codes:
                checkout_error = "delivery_address_required"
            return HttpResponseRedirect(
                f"{editor_url}?checkout_error={checkout_error}&checkout_message={quote(messages)}"
            )
        return redirect_after_b2b_checkout(
            request=request,
            customer=self.customer,
            order=order,
            source="client_portal.studio_checkout_pay",
            requested_provider=(request.POST.get("provider") or "").strip(),
        )


class ClientGangSheetCreateOrderProjectView(ClientGangSheetMixin, View):
    """Parcours aligné sur order-projects/new : nom, date, commentaire (+ exemplaires)."""

    template_name = "portal/client/gang_sheets/create_order_project.html"

    def get(self, request, customer_public_id, sheet_public_id):
        self.require_write_access()
        sheet = self.get_sheet_or_404(sheet_public_id)
        if sheet.project_id:
            return HttpResponseRedirect(
                reverse(
                    "portal:client-order-project-detail",
                    kwargs={
                        "customer_public_id": self.customer.public_id,
                        "project_public_id": sheet.project.public_id,
                    },
                )
            )
        if sheet.status != GangSheet.Status.VALIDATED or not sheet.final_file:
            return HttpResponseRedirect(
                reverse(
                    "portal:client-gang-sheet-editor",
                    kwargs={
                        "customer_public_id": self.customer.public_id,
                        "sheet_public_id": sheet.public_id,
                    },
                )
            )
        initial_quantity = request.GET.get("quantity") or "1"
        return render(
            request,
            self.template_name,
            self.context(
                sheet=sheet,
                form_error="",
                submitted={},
                initial_quantity=initial_quantity,
            ),
        )

    def post(self, request, customer_public_id, sheet_public_id):
        self.require_write_access()
        sheet = self.get_sheet_or_404(sheet_public_id)
        try:
            project = gang_sheet_service.create_order_project(
                sheet=sheet,
                actor=request.user,
                quantity=request.POST.get("quantity", 1),
                name=request.POST.get("name"),
                requested_date=request.POST.get("requested_date"),
                customer_comment=request.POST.get("customer_comment"),
            )
        except GangSheetDomainError as error:
            return render(
                request,
                self.template_name,
                self.context(
                    sheet=sheet,
                    form_error=error.message,
                    submitted=request.POST,
                    initial_quantity=request.POST.get("quantity") or "1",
                ),
                status=400,
            )
        return HttpResponseRedirect(
            reverse(
                "portal:client-order-project-detail",
                kwargs={
                    "customer_public_id": self.customer.public_id,
                    "project_public_id": project.public_id,
                },
            )
        )


class ClientGangSheetAssetPreviewView(ClientGangSheetMixin, View):
    def get(self, request, customer_public_id, sheet_public_id, asset_version_public_id):
        sheet = self.get_sheet_or_404(sheet_public_id)
        version = (
            gang_sheet_service.available_asset_versions(sheet=sheet)
            .filter(public_id=asset_version_public_id)
            .first()
        )
        if version is None:
            raise Http404
        source_asset = (
            sheet.source_assets.filter(
                customer=sheet.customer,
                asset=version.asset,
            )
            .order_by("sort_order")
            .first()
        )
        if source_asset is None:
            raise Http404
        crop = (
            CropBox.full()
            if request.GET.get("original") == "1"
            else CropBox.from_source_asset(source_asset)
        )
        analysis = getattr(version, "analysis", None)
        if analysis is not None and analysis.customer_id != sheet.customer_id:
            raise Http404
        requested_overlay = (request.GET.get("overlay") or "").strip()
        overlay_fields = {
            "thin_zone": "thin_zone_overlay",
            "semi_transparency": "semi_transparency_overlay",
        }
        if requested_overlay:
            overlay_field_name = overlay_fields.get(requested_overlay)
            detection = ((analysis.metadata or {}).get(requested_overlay) or {}) if analysis else {}
            overlay_file = (
                getattr(analysis, overlay_field_name, None) if overlay_field_name else None
            )
            if detection.get("detected") is not True or not overlay_file:
                raise Http404
            overlay_file.open("rb")
            response = FileResponse(overlay_file, content_type="image/webp")
            response["Cache-Control"] = "private, max-age=300"
            response["X-Content-Type-Options"] = "nosniff"
            return response
        if analysis is not None and analysis.thumbnail and crop.is_full:
            analysis.thumbnail.open("rb")
            response = FileResponse(analysis.thumbnail, content_type="image/webp")
        else:
            try:
                if analysis is not None and analysis.thumbnail:
                    analysis.thumbnail.open("rb")
                    with Image.open(analysis.thumbnail) as stored_thumbnail:
                        stored_thumbnail.load()
                        image = stored_thumbnail.convert("RGBA")
                    analysis.thumbnail.close()
                else:
                    rendered = asset_preview_renderer.render(version=version)
                    image = rendered.image.convert("RGBA")
                    rendered.image.close()
                cropped = crop_image(image, crop)
                image.close()
                image = cropped
                image.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                output = BytesIO()
                image.save(output, format="PNG", optimize=True)
                image.close()
            except AssetPreviewError as error:
                raise Http404 from error
            output.seek(0)
            response = FileResponse(output, content_type="image/png")
        response["Cache-Control"] = "private, max-age=300"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ClientGangSheetPreviewDownloadView(ClientGangSheetMixin, View):
    def get(self, request, customer_public_id, sheet_public_id):
        sheet = self.get_sheet_or_404(sheet_public_id)
        if not sheet.preview_file:
            raise Http404
        sheet.preview_file.open("rb")
        response = FileResponse(
            sheet.preview_file,
            content_type="image/png",
            as_attachment=request.GET.get("display") != "inline",
            filename=f"{sheet.name[:80]}-apercu.png",
        )
        response["Cache-Control"] = "private, no-store"
        return response


class StaffGangSheetSettingsView(StaffDomainPermissionMixin, View):
    required_permission = "gang_sheets.configure_gangsheet"
    template_name = "portal/staff/gang_sheets/settings.html"

    def get(self, request):
        config = GangSheetSiteSettings.current()
        return render(
            request,
            self.template_name,
            {
                "form": GangSheetSiteSettingsForm(instance=config),
                "nav_mode": "staff",
                "nav_key": "staff-gang-sheet-settings",
            },
        )

    def post(self, request):
        config = GangSheetSiteSettings.current()
        form = GangSheetSiteSettingsForm(request.POST, instance=config)
        if form.is_valid():
            config = form.save(commit=False)
            config.updated_by = request.user
            config.save()
            from apps.auditlog.services import record_event

            record_event(
                action="gang_sheet.settings_updated",
                actor=request.user,
                target=config,
                metadata={"roll_width_mm": str(config.roll_width_mm), "source": "staff_portal"},
            )
            response = HttpResponseRedirect(reverse("portal:staff-gang-sheet-settings"))
            return with_toast(response, "Réglages de planche enregistrés.", "success")
        return render(
            request,
            self.template_name,
            {"form": form, "nav_mode": "staff", "nav_key": "staff-gang-sheet-settings"},
            status=400,
        )


class StaffGangSheetFinalDownloadView(StaffDomainPermissionMixin, View):
    required_permission = "gang_sheets.download_final_gangsheet"

    def get(self, request, sheet_public_id):
        sheet = (
            GangSheet.objects.select_related("customer", "order")
            .filter(
                public_id=sheet_public_id,
                status=GangSheet.Status.VALIDATED,
            )
            .first()
        )
        if sheet is None or not sheet.final_file:
            raise Http404
        sheet.final_file.open("rb")
        response = FileResponse(
            sheet.final_file,
            content_type="application/pdf",
            as_attachment=True,
            filename=f"{sheet.name[:80]}-production.pdf",
        )
        response["Cache-Control"] = "private, no-store"
        return response
