from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.auditlog.services import record_event
from apps.b2b_order_projects.services.quote_requests import (
    accept_link_quote,
    get_open_quote_request,
    open_quote_requests,
    price_quote_request,
)
from apps.portal.views_b2b_order_projects import ClientProjectFeatureMixin
from apps.portal.views_common import StaffDomainPermissionMixin
from apps.uploads.validators import validate_external_url


class StaffQuoteRequestListView(StaffDomainPermissionMixin, View):
    required_permission = "orders.view_order"
    template_name = "portal/staff/quote_requests_list.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            {
                "projects": open_quote_requests(),
                "nav_mode": "staff",
                "nav_key": "staff-quotes",
            },
        )


class StaffQuoteRequestDetailView(StaffQuoteRequestListView):
    required_permission = "orders.view_order"
    template_name = "portal/staff/quote_request_detail.html"

    def get(self, request, project_public_id):
        project = get_open_quote_request(project_public_id=project_public_id)
        if project is None:
            raise Http404
        return render(
            request,
            self.template_name,
            {
                "project": project,
                "form_error": "",
                "nav_mode": "staff",
                "nav_key": "staff-quotes",
            },
        )

    def post(self, request, project_public_id):
        if not request.user.has_perm("orders.change_order"):
            raise PermissionDenied
        project = get_open_quote_request(project_public_id=project_public_id)
        if project is None:
            raise Http404
        try:
            price_quote_request(
                project=project,
                actor=request.user,
                raw_meterage=request.POST.get("meterage_linear_m"),
            )
        except ValidationError as error:
            return render(
                request,
                self.template_name,
                {
                    "project": project,
                    "form_error": "; ".join(error.messages),
                    "nav_mode": "staff",
                    "nav_key": "staff-quotes",
                },
                status=400,
            )
        return HttpResponseRedirect(
            reverse(
                "portal:staff-quote-request-detail",
                kwargs={"project_public_id": project.public_id},
            )
        )


class StaffQuoteRequestLinkView(StaffQuoteRequestListView):
    required_permission = "orders.view_order"

    def get(self, request, project_public_id):
        project = get_open_quote_request(project_public_id=project_public_id)
        if project is None or not project.external_url:
            raise Http404
        try:
            destination = validate_external_url(project.external_url)
        except ValidationError as error:
            raise Http404 from error
        record_event(
            action="b2b_order_project.external_link_opened",
            actor=request.user,
            target=project,
            metadata={
                "project_public_id": str(project.public_id),
                "customer_public_id": str(project.customer.public_id),
                "audience": "staff",
            },
        )
        response = HttpResponseRedirect(destination)
        response["Referrer-Policy"] = "no-referrer"
        response["Cache-Control"] = "private, no-store"
        return response


class ClientQuoteAcceptView(ClientProjectFeatureMixin, View):
    def post(self, request, customer_public_id, project_public_id):
        project = self.get_project_or_404(project_public_id)
        detail = reverse(
            "portal:client-order-project-detail",
            kwargs={
                "customer_public_id": self.customer.public_id,
                "project_public_id": project.public_id,
            },
        )
        try:
            order = accept_link_quote(project=project, customer=self.customer, actor=request.user)
        except ValidationError:
            return HttpResponseRedirect(f"{detail}?submit_error=validation")
        return HttpResponseRedirect(
            reverse(
                "portal:client-order-detail",
                kwargs={
                    "customer_public_id": self.customer.public_id,
                    "order_public_id": order.public_id,
                },
            )
        )
