from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.inventory.services.stock_ops import StockOpsService
from apps.inventory.services.warehouse import WarehouseLayoutService
from apps.pod.services import BlankCatalogService, PrintTechniqueService
from apps.pod.services.pose import PodPoseService
from apps.pod.services.unit_access import PodUnitAccessService
from apps.pod.services.validation import validation_message
from apps.portal.views_staff_pod import StaffPodPermissionMixin, _nav, _render_error

pose_service = PodPoseService()
stock_ops = StockOpsService()
warehouse_layout_service = WarehouseLayoutService()
blank_catalog_service = BlankCatalogService()
print_technique_service = PrintTechniqueService()
unit_access = PodUnitAccessService()


class StaffPodPoseDtfView(StaffPodPermissionMixin, View):
    template_name = "portal/staff/pod/pose_dtf.html"

    def _context(self, request, lookup=None, form_error=""):
        return {
            **_nav(),
            "lookup": lookup,
            "form_error": form_error,
            "can_operate_production": request.user.has_perm("pod.operate_pod_production"),
            "scan_identifier": request.POST.get("scan_identifier") or request.GET.get("scan", ""),
        }

    def get(self, request):
        lookup = None
        scan = request.GET.get("scan", "").strip()
        if scan:
            try:
                lookup = pose_service.lookup(actor=request.user, scan_identifier=scan)
            except ValidationError as exc:
                return _render_error(request, self.template_name, self._context(request), exc)
        return render(request, self.template_name, self._context(request, lookup=lookup))

    def post(self, request):
        try:
            if request.POST.get("intent") == "press":
                pose_service.mark_pressed(
                    actor=request.user,
                    scan_identifier=request.POST.get("scan_identifier", ""),
                    source="staff_pod",
                )
                return HttpResponseRedirect(
                    reverse("portal:staff-pod-pose-dtf")
                    + f"?scan={request.POST.get('scan_identifier', '').strip().upper()}"
                )
            if request.POST.get("intent", "lookup") != "lookup":
                raise ValidationError("Action de pose inconnue.")
            lookup = pose_service.lookup(
                actor=request.user,
                scan_identifier=request.POST.get("scan_identifier", ""),
            )
        except PermissionDenied:
            raise
        except ValidationError as exc:
            return _render_error(request, self.template_name, self._context(request), exc)
        return render(request, self.template_name, self._context(request, lookup=lookup))


class StaffPodStockView(StaffPodPermissionMixin, View):
    template_name = "portal/staff/pod/stock.html"
    _tabs_by_intent = {
        "receive": "receive",
        "pick": "pick",
        "putaway": "putaway",
        "receive_finished": "fin_receive",
        "pick_finished": "fin_pick",
    }

    def _context(self, request, form_error="", active_stock_tab="receive"):
        zones = warehouse_layout_service.list_zones(actor=request.user)
        locations = [
            location
            for zone in zones
            if zone.is_active and zone.warehouse.is_active
            for location in zone.locations.all()
            if location.is_active
        ]
        can_manage_warehouse = request.user.has_perm("inventory.manage_warehouse")
        search_query = request.GET.get("q", "").strip()[:160]
        page_obj = (
            Paginator(stock_ops.list_balances(actor=request.user, query=search_query), 30).get_page(
                request.GET.get("page")
            )
            if can_manage_warehouse
            else None
        )
        return {
            **_nav(),
            "blanks": blank_catalog_service.list_blanks(actor=request.user).filter(is_active=True),
            "locations": locations,
            "customers": stock_ops.eligible_customers(actor=request.user),
            "can_manage_warehouse": can_manage_warehouse,
            "page_obj": page_obj,
            "search_query": search_query,
            "form_error": form_error,
            "active_stock_tab": active_stock_tab,
        }

    def get(self, request):
        return render(request, self.template_name, self._context(request))

    def post(self, request):
        intent = request.POST.get("intent", "receive")
        try:
            if intent not in self._tabs_by_intent:
                raise ValidationError("Action de stock inconnue.")
            qty = int(request.POST.get("quantity") or 0)
            owner_kwargs = {
                "owner_kind": request.POST.get("owner_kind") or "atelier",
                "customer_public_id": request.POST.get("customer_public_id") or None,
            }
            if intent == "pick_finished":
                stock_ops.pick_finished(
                    actor=request.user,
                    source="staff_pod",
                    finished_sku=request.POST.get("finished_sku", ""),
                    scanned_bin_code=request.POST.get("scanned_bin_code", ""),
                    quantity=qty,
                    **owner_kwargs,
                )
            elif intent == "receive_finished":
                stock_ops.receive_finished(
                    actor=request.user,
                    source="staff_pod",
                    finished_sku=request.POST.get("finished_sku", ""),
                    location_public_id=request.POST.get("location_public_id"),
                    quantity=qty,
                    **owner_kwargs,
                )
            elif intent == "pick":
                stock_ops.pick_blank(
                    actor=request.user,
                    source="staff_pod",
                    blank_variant_public_id=request.POST.get("blank_variant_public_id"),
                    scanned_bin_code=request.POST.get("scanned_bin_code", ""),
                    quantity=qty,
                    **owner_kwargs,
                )
            elif intent == "putaway":
                stock_ops.putaway_return(
                    actor=request.user,
                    source="staff_pod",
                    blank_variant_public_id=request.POST.get("blank_variant_public_id"),
                    location_public_id=request.POST.get("location_public_id"),
                    quantity=qty,
                    **owner_kwargs,
                )
            elif intent == "receive":
                stock_ops.receive_blank(
                    actor=request.user,
                    source="staff_pod",
                    blank_variant_public_id=request.POST.get("blank_variant_public_id"),
                    location_public_id=request.POST.get("location_public_id"),
                    quantity=qty,
                    **owner_kwargs,
                )
        except PermissionDenied:
            raise
        except (ValidationError, ValueError) as exc:
            message = (
                validation_message(exc)
                if isinstance(exc, ValidationError)
                else "Quantité invalide."
            )
            return _render_error(
                request,
                self.template_name,
                self._context(
                    request,
                    active_stock_tab=self._tabs_by_intent.get(intent, "receive"),
                ),
                ValidationError(message),
            )
        messages.success(request, "Mouvement de stock enregistré.")
        return HttpResponseRedirect(reverse("portal:staff-pod-stock"))


class StaffPodUnitDocumentView(StaffPodPermissionMixin, View):
    def get(self, request, unit_public_id, document_kind):
        try:
            unit, path = unit_access.document_path(
                actor=request.user,
                unit_public_id=unit_public_id,
                kind=document_kind,
            )
        except ValidationError as exc:
            raise Http404(validation_message(exc)) from exc
        return FileResponse(path.open("rb"), as_attachment=True, filename=path.name)
