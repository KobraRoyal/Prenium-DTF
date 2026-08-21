from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import View

from apps.portal.views_common import production_workflow_service
from apps.portal.views_staff import StaffOrderContextMixin


class StaffOrderPanelScanView(StaffOrderContextMixin, View):
    """Compatibilité : l'ancien panneau renvoie vers la console dédiée."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("production.scan_productionjob"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, order_public_id):
        job = production_workflow_service.get_or_create_for_order(order=self.order)
        console_url = reverse("portal:staff-atelier-operations")
        return HttpResponseRedirect(f"{console_url}?{urlencode({'q': job.scan_identifier})}")

    def post(self, request, order_public_id):
        return self.get(request, order_public_id)
