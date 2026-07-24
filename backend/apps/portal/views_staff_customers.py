from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from apps.customers.forms_staff import StaffCustomerAccountForm, StaffCustomerPricingForm
from apps.customers.services.administration import CustomerAdministrationService
from apps.portal.htmx import with_toast
from apps.portal.views_common import StaffDomainPermissionMixin

customer_admin_service = CustomerAdministrationService()


class StaffCustomerListView(StaffDomainPermissionMixin, View):
    required_permission = "customers.view_customer"
    template_name = "portal/staff/customers/list.html"

    def get(self, request):
        search = request.GET.get("q", "")
        status = request.GET.get("status", "active")
        active_only = None
        if status == "active":
            active_only = True
        elif status == "inactive":
            active_only = False
        queryset = customer_admin_service.list_customers(search=search, active_only=active_only)
        page_obj = customer_admin_service.paginate_customers(
            queryset,
            page_number=request.GET.get("page"),
            page_size=25,
        )
        return render(
            request,
            self.template_name,
            {
                "page_obj": page_obj,
                "search_query": search,
                "active_status": status,
                "can_manage_accounts": request.user.has_perm("customers.change_customer"),
                "can_manage_pricing": request.user.has_perm("customers.manage_customer_pricing"),
                "nav_mode": "staff",
                "nav_key": "staff-customers",
            },
        )


class StaffCustomerDetailView(StaffDomainPermissionMixin, View):
    required_permission = "customers.view_customer"
    template_name = "portal/staff/customers/detail.html"

    def get(self, request, customer_public_id):
        customer = customer_admin_service.get_customer(customer_public_id=customer_public_id)
        if customer is None:
            raise Http404
        return render(request, self.template_name, self._context(request, customer))

    def _context(self, request, customer, *, account_form=None, pricing_form=None):
        can_edit_account = request.user.has_perm("customers.change_customer")
        can_edit_pricing = request.user.has_perm("customers.manage_customer_pricing")
        return {
            "customer": customer,
            "memberships": customer_admin_service.list_memberships(customer=customer),
            "billing_profile": getattr(customer, "billing_profile", None),
            "account_form": account_form
            or (StaffCustomerAccountForm(instance=customer) if can_edit_account else None),
            "pricing_form": pricing_form
            or (StaffCustomerPricingForm.from_customer(customer) if can_edit_pricing else None),
            "can_edit_account": can_edit_account,
            "can_edit_pricing": can_edit_pricing,
            "nav_mode": "staff",
            "nav_key": "staff-customers",
        }


class StaffCustomerAccountUpdateView(StaffDomainPermissionMixin, View):
    required_permission = "customers.change_customer"

    def post(self, request, customer_public_id):
        customer = customer_admin_service.get_customer(customer_public_id=customer_public_id)
        if customer is None:
            raise Http404
        form = StaffCustomerAccountForm(request.POST, instance=customer)
        detail_url = reverse(
            "portal:staff-customer-detail",
            kwargs={"customer_public_id": customer.public_id},
        )
        if not form.is_valid():
            messages.error(request, "Corrigez les erreurs du formulaire compte.")
            response = render(
                request,
                "portal/staff/customers/detail.html",
                StaffCustomerDetailView()._context(request, customer, account_form=form),
            )
            return with_toast(response, message="Formulaire compte invalide.", variant="error")

        customer_admin_service.update_account(
            customer=customer,
            cleaned_data=form.cleaned_data,
            actor=request.user,
            source="staff_portal",
        )
        messages.success(request, "Compte client mis à jour.")
        response = redirect(detail_url)
        return with_toast(response, message="Compte client mis à jour.", variant="success")


class StaffCustomerPricingUpdateView(StaffDomainPermissionMixin, View):
    required_permission = "customers.manage_customer_pricing"

    def post(self, request, customer_public_id):
        if not request.user.has_perm("customers.manage_customer_pricing"):
            raise PermissionDenied
        customer = customer_admin_service.get_customer(customer_public_id=customer_public_id)
        if customer is None:
            raise Http404
        form = StaffCustomerPricingForm(request.POST)
        detail_url = reverse(
            "portal:staff-customer-detail",
            kwargs={"customer_public_id": customer.public_id},
        )
        if not form.is_valid():
            messages.error(request, "Corrigez les erreurs des conditions tarifaires.")
            response = render(
                request,
                "portal/staff/customers/detail.html",
                StaffCustomerDetailView()._context(request, customer, pricing_form=form),
            )
            return with_toast(
                response,
                message="Conditions tarifaires invalides.",
                variant="error",
            )

        customer_admin_service.update_pricing_conditions(
            customer=customer,
            cleaned_data=form.cleaned_data,
            actor=request.user,
            source="staff_portal",
        )
        messages.success(request, "Conditions tarifaires enregistrées.")
        response = redirect(detail_url)
        return with_toast(
            response,
            message="Conditions tarifaires enregistrées.",
            variant="success",
        )
