from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.pod.services.shopify_connect import ShopifyConnectService
from apps.pod.services.validation import validation_message
from apps.portal.views_staff_pod import StaffPodPermissionMixin, _nav, _render_error

connect_service = ShopifyConnectService()


class StaffPodShopifyStoresView(StaffPodPermissionMixin, View):
    template_name = "portal/staff/pod/shops.html"

    def _context(self, request, form_error: str = ""):
        flash = request.session.pop("pod_shopify_flash", "")
        flash_error = request.session.pop("pod_shopify_flash_error", "")
        return {
            **_nav(),
            "stores": connect_service.list_stores(actor=request.user),
            "oauth_ready": connect_service.oauth_is_configured(),
            "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
            "form_error": form_error or flash_error,
            "flash": flash,
        }

    def get(self, request):
        return render(request, self.template_name, self._context(request))

    def post(self, request):
        intent = request.POST.get("intent", "")
        try:
            if intent == "oauth":
                url = connect_service.authorization_url(
                    actor=request.user,
                    shop_domain=request.POST.get("shop_domain", ""),
                )
                return HttpResponseRedirect(url)
            if intent == "save_token":
                connect_service.save_manual_token(
                    actor=request.user,
                    shop_domain=request.POST.get("shop_domain", ""),
                    token=request.POST.get("access_token", ""),
                    name=request.POST.get("name", ""),
                )
            else:
                connect_service.run_store_action(
                    actor=request.user,
                    store_public_id=request.POST.get("store_public_id"),
                    intent=intent,
                )
        except PermissionDenied:
            raise
        except ValidationError as exc:
            return _render_error(
                request,
                self.template_name,
                self._context(request),
                ValidationError(validation_message(exc)),
            )
        return HttpResponseRedirect(reverse("portal:staff-pod-shops"))
