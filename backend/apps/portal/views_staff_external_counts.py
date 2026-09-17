from django.core.exceptions import ValidationError
from django.views import View

from apps.portal.htmx import with_toast
from apps.portal.views_common import upload_service
from apps.portal.views_staff_operations import StaffAtelierOperationsContextMixin


class StaffAtelierExternalCountView(StaffAtelierOperationsContextMixin, View):
    required_permissions = (
        *StaffAtelierOperationsContextMixin.required_permissions,
        "orders.change_order",
    )

    def post(self, request, order_public_id):
        order = self._staff_order(order_public_id)
        try:
            upload_service.set_staff_external_visual_count(
                order=order,
                actor=request.user,
                value=request.POST.get("external_visual_count", ""),
            )
        except ValidationError as error:
            message = "; ".join(error.messages)
            tone = "error"
        else:
            message = "Nombre de fichiers enregistré."
            tone = "success"
        response = self._render_workspace(request, feedback=message, feedback_tone=tone)
        return with_toast(response, message, tone)
