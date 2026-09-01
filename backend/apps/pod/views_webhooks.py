from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.pod.services.validation import validation_message
from apps.pod.tasks import ingest_shopify_pod_fulfillment_task


@method_decorator(csrf_exempt, name="dispatch")
class ShopifyPodFulfillmentWebhookView(View):
    def post(self, request):
        try:
            async_result = ingest_shopify_pod_fulfillment_task.delay(
                raw_body=request.body.decode("latin-1"),
                hmac_header=request.headers.get("X-Shopify-Hmac-Sha256", ""),
                shop_domain=request.headers.get("X-Shopify-Shop-Domain", ""),
                webhook_id=request.headers.get("X-Shopify-Webhook-Id", ""),
            )
        except ValidationError as exc:
            message = validation_message(exc)
            status = 401 if "HMAC" in message else 400
            return JsonResponse({"ok": False, "error": message}, status=status)
        if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
            result = async_result.result
            if isinstance(result, Exception):
                message = str(result)
                status = 401 if "HMAC" in message else 400
                return JsonResponse({"ok": False, "error": message}, status=status)
            return JsonResponse({"ok": True, **result})
        return JsonResponse({"ok": True, "accepted": True})
