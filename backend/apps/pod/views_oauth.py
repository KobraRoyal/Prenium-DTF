from __future__ import annotations

from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.pod.services.shopify_connect import ShopifyConnectService
from apps.pod.services.validation import validation_message

connect_service = ShopifyConnectService()


@method_decorator(csrf_exempt, name="dispatch")
class ShopifyPodOAuthCallbackView(View):
    def get(self, request):
        shops_url = reverse("portal:staff-pod-shops")
        try:
            store = connect_service.complete_oauth(query=request.GET)
            request.session["pod_shopify_flash"] = f"Boutique {store.shop_domain} connectée."
        except ValidationError as exc:
            request.session["pod_shopify_flash_error"] = validation_message(exc)
        return HttpResponseRedirect(shops_url)
