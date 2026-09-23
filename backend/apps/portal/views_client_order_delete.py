from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import View

from apps.portal.client_order_presentation import client_may_delete_unpaid_order
from apps.portal.views_client import ClientOrderContextMixin
from apps.portal.views_common import order_service


class ClientOrderDeleteView(ClientOrderContextMixin, View):
    """Annule une commande comptant CB tant que le paiement n'est pas capturé."""

    def post(self, request, customer_public_id, order_public_id):
        if not client_may_delete_unpaid_order(self.customer_membership):
            raise PermissionDenied
        order = self.get_order_or_404(order_public_id)
        next_target = request.POST.get("next")
        try:
            order_service.delete_client_order(
                customer=self.customer,
                order_public_id=order.public_id,
                actor=request.user,
                source="client_portal.order_delete",
            )
        except ValidationError as exc:
            messages.error(request, " ".join(getattr(exc, "messages", None) or [str(exc)]))
        else:
            messages.success(
                request,
                "Commande supprimée. Elle reste visible avec le statut Annulée.",
            )
        if next_target == "list":
            return HttpResponseRedirect(
                reverse(
                    "portal:client-order-list",
                    kwargs={"customer_public_id": self.customer.public_id},
                )
            )
        return HttpResponseRedirect(
            reverse(
                "portal:client-order-detail",
                kwargs={
                    "customer_public_id": self.customer.public_id,
                    "order_public_id": order.public_id,
                },
            )
        )
