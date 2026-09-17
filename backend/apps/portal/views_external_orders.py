from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.b2b_order_projects.permissions import customer_requires_gang_sheet_orders
from apps.orders.services.external_orders import ExternalOrderService
from apps.portal.forms_external_orders import (
    ExternalOrderForm,
    ProjectExternalOrderForm,
    StaffExternalOrderForm,
)
from apps.portal.views_common import ScopedCustomerMixin, StaffDomainPermissionMixin
from apps.uploads.services.external_links import ExternalUploadLinkService


def external_link_response(**kwargs):
    try:
        destination = ExternalUploadLinkService().open_link(**kwargs)
    except ValidationError as error:
        raise Http404 from error
    response = HttpResponseRedirect(destination)
    response["Referrer-Policy"] = "no-referrer"
    response["Cache-Control"] = "private, no-store"
    return response


class ClientExternalUploadLinkView(ScopedCustomerMixin, View):
    def get(self, request, customer_public_id, order_public_id, upload_public_id):
        return external_link_response(
            actor=request.user,
            customer=self.customer,
            order_public_id=order_public_id,
            upload_public_id=upload_public_id,
        )


class StaffExternalUploadLinkView(StaffDomainPermissionMixin, View):
    required_permission = "uploads.view_orderupload"

    def get(self, request, order_public_id, upload_public_id):
        return external_link_response(
            actor=request.user,
            order_public_id=order_public_id,
            upload_public_id=upload_public_id,
        )


class ClientExternalOrderCreateView(ScopedCustomerMixin, View):
    def get(self, request, customer_public_id):
        return self._render(request, ExternalOrderForm())

    def post(self, request, customer_public_id):
        form = ExternalOrderForm(request.POST)
        if form.is_valid():
            try:
                order = ExternalOrderService().create_client_order(
                    customer=self.customer, actor=request.user, **form.cleaned_data
                )
            except ValidationError as error:
                form.add_error(None, "; ".join(error.messages))
            else:
                return HttpResponseRedirect(
                    reverse(
                        "portal:client-order-detail",
                        kwargs={
                            "customer_public_id": self.customer.public_id,
                            "order_public_id": order.public_id,
                        },
                    )
                )
        return self._render(request, form, status=400)

    def _render(self, request, form, status=200):
        if customer_requires_gang_sheet_orders(self.customer):
            raise PermissionDenied
        return render(
            request,
            "portal/client/external_order_form.html",
            {
                "customer": self.customer,
                "external_order_form": form,
                "nav_mode": "client",
                "nav_key": "client-checkout",
            },
            status=status,
        )


def create_external_order_from_project_form(request, *, customer, context):
    form = ProjectExternalOrderForm(request.POST)
    if form.is_valid():
        try:
            order = ExternalOrderService().create_client_order(
                customer=customer, actor=request.user, **form.cleaned_data
            )
        except ValidationError as error:
            form.add_error(None, "; ".join(error.messages))
        else:
            return HttpResponseRedirect(
                reverse("portal:client-order-detail", args=[customer.public_id, order.public_id])
            )
    return render(
        request,
        "portal/client/order_project_form.html",
        {**context, "external_order_form": form, "submitted": request.POST},
        status=400,
    )


class StaffExternalOrderCreateView(StaffDomainPermissionMixin, View):
    required_permission = "orders.add_order"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.has_perms(
            ["orders.view_order", "orders.change_order"]
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return self._render(request, StaffExternalOrderForm())

    def post(self, request):
        form = StaffExternalOrderForm(request.POST)
        if form.is_valid():
            try:
                order = ExternalOrderService().create_staff_order(
                    actor=request.user, **form.cleaned_data
                )
            except ValidationError as error:
                form.add_error(None, "; ".join(error.messages))
            else:
                return HttpResponseRedirect(
                    reverse(
                        "portal:staff-order-detail", kwargs={"order_public_id": order.public_id}
                    )
                )
        return self._render(request, form, status=400)

    def _render(self, request, form, status=200):
        return render(
            request,
            "portal/staff/external_order_form.html",
            {
                "form": form,
                "dtf_laize_cm": settings.DTF_LAIZE_CM,
                "nav_mode": "staff",
                "nav_key": "staff-orders",
            },
            status=status,
        )
