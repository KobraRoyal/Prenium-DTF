from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.pod.services import PodRipLotService, ShopifyCatalogService
from apps.pod.services.validation import validation_message
from apps.portal.views_staff_pod import StaffPodPermissionMixin, _nav, _render_error

rip_lot_service = PodRipLotService()
shopify_catalog_service = ShopifyCatalogService()


class StaffPodRipLotListView(StaffPodPermissionMixin, View):
    template_name = "portal/staff/pod/rip_lots.html"

    def _context(self, request, form_error: str = ""):
        return {
            **_nav(),
            "queue": rip_lot_service.list_queue(actor=request.user),
            "lots": rip_lot_service.list_lots(actor=request.user),
            "products": shopify_catalog_service.list_products(actor=request.user),
            "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
            "form_error": form_error,
        }

    def get(self, request):
        return render(request, self.template_name, self._context(request))

    def post(self, request):
        intent = request.POST.get("intent", "enqueue")
        try:
            if intent == "prepare":
                lot = rip_lot_service.prepare_dtf_lot(actor=request.user, source="staff_pod")
                return HttpResponseRedirect(
                    reverse(
                        "portal:staff-pod-rip-lot-detail",
                        kwargs={"lot_public_id": lot.public_id},
                    )
                )
            rip_lot_service.enqueue(
                actor=request.user,
                source="staff_pod",
                variant_public_id=request.POST.get("variant_public_id"),
                shopify_order_number=request.POST.get("shopify_order_number", ""),
                quantity=int(request.POST.get("quantity") or 1),
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
                self._context(request),
                ValidationError(message),
            )
        return HttpResponseRedirect(reverse("portal:staff-pod-rip-lots"))


class StaffPodRipLotDetailView(StaffPodPermissionMixin, View):
    template_name = "portal/staff/pod/rip_lot_detail.html"

    def get(self, request, lot_public_id):
        try:
            lot = rip_lot_service.get_lot(actor=request.user, lot_public_id=lot_public_id)
        except ValidationError as exc:
            raise Http404(validation_message(exc)) from exc
        return render(
            request,
            self.template_name,
            {
                **_nav(),
                "lot": lot,
                "files": lot.files.select_related("variant", "work_item", "technique"),
            },
        )
