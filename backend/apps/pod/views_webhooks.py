from __future__ import annotations

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.pod.services.shopify_ingest import ShopifyFulfillmentIngestService
from apps.pod.services.validation import validation_message

ingest_service = ShopifyFulfillmentIngestService()


@method_decorator(csrf_exempt, name="dispatch")
class ShopifyPodFulfillmentWebhookView(View):
    def post(self, request):
        try:
            result = ingest_service.ingest(
                raw_body=request.body,
                hmac_header=request.headers.get("X-Shopify-Hmac-Sha256", ""),
                shop_domain=request.headers.get("X-Shopify-Shop-Domain", ""),
            )
        except ValidationError as exc:
            message = validation_message(exc)
            status = 401 if "HMAC" in message else 400
            return JsonResponse({"ok": False, "error": message}, status=status)
        return JsonResponse({"ok": True, **result})
