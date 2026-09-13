from __future__ import annotations

import json
import logging
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
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
    CROP_MODE_MANUAL,
    CropBox,
    CropInstruction,
    CropValidationError,
    crop_image,
    parse_crop_manifest,
)
from apps.portal.htmx import with_toast
from apps.portal.views_b2b_order_projects import ClientProjectFeatureMixin
from apps.portal.views_common import StaffDomainPermissionMixin
from apps.uploads.services.asset_preview import AssetPreviewError, AssetPreviewRenderer

gang_sheet_service = GangSheetService()
asset_preview_renderer = AssetPreviewRenderer()
logger = logging.getLogger(__name__)

GANG_SHEET_MAX_FILES_PER_UPLOAD = 20
GANG_SHEET_MAX_TOTAL_UPLOAD_BYTES = 60 * 1024 * 1024
GANG_SHEET_UPLOAD_BATCH_SESSION_PREFIX = "gang_sheet_upload_batch"
GANG_SHEET_UPLOAD_ERROR_SESSION_PREFIX = "gang_sheet_upload_error"


def _decimal_display(value) -> str:
    if value is None:
        return ""
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


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

    def preview_url(self, *, sheet, version, overlay=""):
        url = reverse(
            "portal:client-gang-sheet-asset-preview",
            kwargs={
                "customer_public_id": self.customer.public_id,
                "sheet_public_id": sheet.public_id,
                "asset_version_public_id": version.public_id,
            },
        )
        if overlay:
            return f"{url}?{urlencode({'overlay': overlay})}"
        return url

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
            assets.append(
                {
                    "source_public_id": str(entry.public_id),
                    "public_id": str(version.public_id) if version else "",
                    "name": entry.asset.name,
                    "preview_url": (
                        self.preview_url(sheet=sheet, version=version) if is_ready else ""
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
                    "is_recent_import": is_recent,
                    "is_ready": is_ready,
                    "width_mm": entry.effective_width_mm,
                    "height_mm": entry.effective_height_mm,
                    "has_crop": entry.has_crop,
                    "usage_count": usage_count,
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
            "can_edit": can_edit,
            "can_manage_gallery": can_manage_gallery,
            "recent_import_version_public_ids": sorted(batch_ids),
            "has_pending_recent_imports": recent_pending,
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
                    sheet=sheet, item_public_id=item_public_id, actor=request.user
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
            return _json_error(error)
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
        crop = CropBox.from_source_asset(source_asset)
        analysis = getattr(version, "analysis", None)
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
