from __future__ import annotations

from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.portal.views_common import StaffPortalMixin
from apps.production.services.manufacturing_order_batch import (
    ManufacturingOrderBatchService,
)

manufacturing_order_batch_service = ManufacturingOrderBatchService()


class StaffManufacturingOrderBatchPdfView(StaffPortalMixin, View):
    def dispatch(self, request, *args, **kwargs):
        if not (
            request.user.has_perm("orders.view_order")
            and request.user.has_perm("production.view_productionjob")
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        try:
            pdf_bytes, orders = manufacturing_order_batch_service.build_batch_pdf(
                actor=request.user,
                order_public_ids=request.POST.getlist("order_public_ids"),
                mode=request.POST.get("batch_mode", "selected"),
                source="staff_portal.dashboard",
            )
        except ValidationError as exc:
            message = " ".join(getattr(exc, "messages", None) or [str(exc)])
            query = urlencode({"batch_error": message[:240]})
            return HttpResponseRedirect(f"{reverse('portal:staff-dashboard')}?{query}")

        timestamp = timezone.localtime().strftime("%Y%m%d-%H%M")
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="OF-lot-{timestamp}-{len(orders)}.pdf"'
        )
        response["Cache-Control"] = "private, no-store"
        return response
