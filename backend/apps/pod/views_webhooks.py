from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.auditlog.services import record_event
from apps.pod.services.shopify_ingest import (
    SUPPORTED_TOPICS,
    ShopifyFulfillmentIngestService,
)
from apps.pod.services.shopify_webhook_security import authenticate_shopify_webhook
from apps.pod.services.validation import validation_message
from apps.pod.tasks import (
    ingest_shopify_pod_fulfillment_task,
    process_shopify_pod_inbox_task,
)


@method_decorator(csrf_exempt, name="dispatch")
class ShopifyPodFulfillmentWebhookView(View):
    def post(self, request):
        raw_body = request.body
        hmac_header = request.headers.get("X-Shopify-Hmac-Sha256", "")
        shop_domain = request.headers.get("X-Shopify-Shop-Domain", "")
        try:
            authenticate_shopify_webhook(
                raw_body=raw_body,
                hmac_header=hmac_header,
                shop_domain=shop_domain,
            )
        except ValidationError as exc:
            return JsonResponse(
                {"ok": False, "error": validation_message(exc)},
                status=401,
            )

        webhook_id = request.headers.get("X-Shopify-Webhook-Id", "").strip()
        if not webhook_id:
            record_event(
                action="pod.shopify.webhook_rejected",
                status="failure",
                message="Identifiant de livraison Shopify manquant.",
                metadata={"shop": shop_domain, "reason": "missing_delivery_id"},
            )
            return JsonResponse(
                {"ok": False, "error": "Identifiant de livraison Shopify manquant."},
                status=400,
            )

        topic = request.headers.get("X-Shopify-Topic", "orders/create")
        if (topic or "orders/create").strip().lower() not in SUPPORTED_TOPICS:
            return JsonResponse({"ok": True, "ignored": True})

        if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
            try:
                async_result = ingest_shopify_pod_fulfillment_task.delay(
                    raw_body=raw_body.decode("latin-1"),
                    hmac_header=hmac_header,
                    shop_domain=shop_domain,
                    webhook_id=webhook_id,
                    topic=topic,
                )
            except ValidationError as exc:
                return JsonResponse(
                    {"ok": False, "error": validation_message(exc)}, status=400
                )
            result = async_result.result
            if isinstance(result, Exception):
                return JsonResponse({"ok": False, "error": str(result)}, status=400)
            return JsonResponse({"ok": True, **result})

        try:
            receipt, created = ShopifyFulfillmentIngestService().accept_delivery(
                raw_body=raw_body,
                hmac_header=hmac_header,
                shop_domain=shop_domain,
                webhook_id=webhook_id,
                topic=topic,
            )
        except ValidationError as exc:
            return JsonResponse({"ok": False, "error": validation_message(exc)}, status=400)
        if created:
            try:
                process_shopify_pod_inbox_task.delay(str(receipt.public_id))
            except Exception:
                record_event(
                    action="pod.shopify.webhook_dispatch_failed",
                    status="failure",
                    message="Livraison persistée ; reprise périodique requise.",
                    metadata={"receipt_public_id": str(receipt.public_id)},
                )
        return JsonResponse(
            {"ok": True, "accepted": True, "duplicate": not created}
        )
