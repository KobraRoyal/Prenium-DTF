from __future__ import annotations

import json
from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.portal.htmx import with_toast
from apps.portal.views_common import StaffPortalMixin
from apps.production.services.manufacturing_order_batch import (
    ManufacturingOrderBatchService,
)

manufacturing_order_batch_service = ManufacturingOrderBatchService()


class StaffManufacturingOrderBatchPdfView(StaffPortalMixin, View):
    async_batch_header = "X-Atelier-Batch"

    def dispatch(self, request, *args, **kwargs):
        if not (
            request.user.has_perm("orders.view_order")
            and request.user.has_perm("production.view_productionjob")
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def _is_async_batch(self, request) -> bool:
        return request.headers.get(self.async_batch_header) == "1"

    def post(self, request):
        is_async = self._is_async_batch(request)
        try:
            pdf_bytes, orders = manufacturing_order_batch_service.build_batch_pdf(
                actor=request.user,
                order_public_ids=request.POST.getlist("order_public_ids"),
                mode=request.POST.get("batch_mode", "selected"),
                source="staff_portal.dashboard",
            )
        except ValidationError as exc:
            message = " ".join(getattr(exc, "messages", None) or [str(exc)])
            if is_async:
                response = HttpResponse(status=422)
                return with_toast(response, message, "error")
            query = urlencode({"batch_error": message[:240]})
            return HttpResponseRedirect(f"{reverse('portal:staff-dashboard')}?{query}")

        timestamp = timezone.localtime().strftime("%Y%m%d-%H%M")
        filename = f"OF-lot-{timestamp}-{len(orders)}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        response["Cache-Control"] = "private, no-store"
        if is_async:
            count = len(orders)
            label = f"{count} OF émis — aperçu ouvert, imprimez depuis le navigateur."
            response = with_toast(response, label, "success")
            response["X-Prenium-Batch-Order-Ids"] = json.dumps(
                [str(order.public_id) for order in orders],
                ensure_ascii=True,
            )
            return response
        return response
