from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from apps.billing.forms import BillingStatementMonthForm
from apps.billing.services.statements import BillingStatementService
from apps.customers.services.administration import CustomerAdministrationService
from apps.portal.htmx import with_toast
from apps.portal.views_common import StaffDomainPermissionMixin
from apps.portal.views_staff_customers import StaffCustomerDetailView

billing_statement_service = BillingStatementService()
customer_admin_service = CustomerAdministrationService()


class StaffCustomerBillingStatementCreateView(StaffDomainPermissionMixin, View):
    required_permission = "billing.add_billingstatement"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("customers.view_customer"):
            raise PermissionDenied
        if not request.user.has_perm("billing.view_billingstatement"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, customer_public_id):
        customer = customer_admin_service.get_customer(customer_public_id=customer_public_id)
        if customer is None:
            raise Http404
        form = BillingStatementMonthForm(request.POST, prefix="statement")
        detail_url = reverse(
            "portal:staff-customer-detail",
            kwargs={"customer_public_id": customer.public_id},
        )
        if form.is_valid():
            try:
                statement = billing_statement_service.generate_monthly_statement(
                    customer=customer,
                    month=form.cleaned_data["month"],
                    actor=request.user,
                    source="staff_portal.customer_billing_statement",
                )
            except ValidationError as exc:
                form.add_error(None, exc)

        if not form.is_valid() or form.non_field_errors():
            messages.error(request, "Le récapitulatif n’a pas pu être généré.")
            response = render(
                request,
                "portal/staff/customers/detail.html",
                StaffCustomerDetailView()._context(
                    request,
                    customer,
                    billing_statement_form=form,
                ),
            )
            return with_toast(response, "Récapitulatif non généré.", "error")

        message = (
            f"Récapitulatif généré : {statement.orders.count()} commande(s), "
            f"{statement.total_amount:.2f} {statement.currency} HT."
        )
        messages.success(request, message)
        return with_toast(
            redirect(f"{detail_url}#billing-statements"),
            message,
            "success",
        )


class StaffCustomerBillingStatementExportView(StaffDomainPermissionMixin, View):
    required_permission = "billing.view_billingstatement"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("customers.view_customer"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, customer_public_id, statement_public_id):
        customer = customer_admin_service.get_customer(customer_public_id=customer_public_id)
        if customer is None:
            raise Http404
        statement = billing_statement_service.get_for_customer(
            customer=customer,
            statement_public_id=statement_public_id,
        )
        if statement is None:
            raise Http404

        try:
            content = billing_statement_service.render_csv(statement=statement)
        except ValidationError:
            billing_statement_service.record_export_failure(
                statement=statement,
                actor=request.user,
                source="staff_portal.customer_billing_statement.csv",
                reason_code="snapshot_integrity_validation_failed",
            )
            response = HttpResponse(
                "Ce récapitulatif ne peut pas être exporté. Contactez un administrateur.",
                status=409,
                content_type="text/plain; charset=utf-8",
            )
            response["Cache-Control"] = "private, no-store"
            response["X-Content-Type-Options"] = "nosniff"
            return response
        billing_statement_service.record_export(
            statement=statement,
            actor=request.user,
            source="staff_portal.customer_billing_statement.csv",
        )
        filename = f"recap-facturation-{statement.period_start:%Y-%m}-{statement.public_id}.csv"
        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
