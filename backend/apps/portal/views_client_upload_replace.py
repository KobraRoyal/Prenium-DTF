from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.views import View

from apps.portal.htmx import with_toast
from apps.portal.views_client import ClientOrderContextMixin
from apps.portal.views_common import upload_service


class ClientOrderUploadReplaceView(ClientOrderContextMixin, View):
    template_name = "portal/client/panels/uploads.html"

    def post(self, request, customer_public_id, order_public_id, upload_public_id):
        order = self.get_order_or_404(order_public_id)
        form_error = ""
        try:
            upload_service.replace_after_correction(
                customer=self.customer,
                actor=request.user,
                uploaded_file=request.FILES.get("file"),
                customer_membership=self.customer_membership,
                order_public_id=order.public_id,
                upload_public_id=upload_public_id,
                source="client_portal.order_upload_correction",
            )
        except ValidationError as error:
            form_error = " ".join(error.messages)
        _order, uploads = upload_service.list_customer_order_uploads(
            customer=self.customer,
            order_public_id=order.public_id,
        )
        response = render(
            request,
            self.template_name,
            self.client_order_context(
                order=order,
                uploads=uploads,
                active_panel="uploads",
                replace_error=form_error,
                replace_error_upload_id=str(upload_public_id) if form_error else "",
            ),
        )
        if form_error:
            return with_toast(response, form_error, "error")
        return with_toast(
            response,
            "Fichier corrigé envoyé. L’atelier va le contrôler à nouveau.",
            "success",
        )
