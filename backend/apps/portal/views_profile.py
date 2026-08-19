from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.accounts.forms import ProfileInformationForm
from apps.accounts.services.profile import AccountProfileService
from apps.customers.forms_client import ClientCompanyProfileForm
from apps.customers.services.company_profile import CompanyProfileService
from apps.portal.htmx import with_toast
from apps.portal.views_common import ScopedCustomerMixin, access_scope_service

account_profile_service = AccountProfileService()
company_profile_service = CompanyProfileService()


def _is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _nav_mode(request) -> str:
    requested_space = request.POST.get("space") or request.GET.get("space")
    if requested_space == "staff" and access_scope_service.can_access_staff_portal(
        request.user
    ):
        return "staff"
    return "client"


def _profile_redirect(request, *, saved: bool = False) -> HttpResponseRedirect:
    url = f"{reverse('portal:profile')}?space={_nav_mode(request)}"
    if saved:
        url += "&saved=1"
    return HttpResponseRedirect(url)


class PortalProfileView(LoginRequiredMixin, View):
    template_name = "portal/profile.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            self._context(request, saved=request.GET.get("saved") == "1"),
        )

    def post(self, request):
        form = ProfileInformationForm(request.POST, instance=request.user)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                self._context(request, saved=False),
                status=400,
            )

        account_profile_service.update_personal_information(
            user=request.user,
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
        )
        return _profile_redirect(request, saved=True)

    def _context(self, request, *, saved: bool) -> dict[str, object]:
        nav_mode = _nav_mode(request)
        context: dict[str, object] = {
            "nav_key": "account-profile",
            "nav_mode": nav_mode,
            "saved": saved,
        }
        if nav_mode == "client":
            scope = access_scope_service.get_user_scope(request.user)
            selected_membership = scope.memberships[0] if scope.memberships else None
            customer = None
            if selected_membership is not None:
                customer = (
                    access_scope_service.get_customer_queryset(request.user)
                    .filter(public_id=selected_membership.customer_public_id)
                    .first()
                )
            can_edit_company = bool(
                selected_membership is not None and selected_membership.can_manage_team
            )
            context.update(
                {
                    "customer": customer,
                    "selected_membership": selected_membership,
                    "can_edit_company": can_edit_company,
                    "company_profile": (
                        company_profile_service.present(customer) if customer else None
                    ),
                }
            )
        return context


class PortalProfileIdentityView(LoginRequiredMixin, View):
    display_template = "portal/partials/profile_identity_display.html"
    form_template = "portal/partials/profile_identity_form.html"

    def get(self, request):
        if not _is_htmx(request):
            return _profile_redirect(request)
        if request.GET.get("edit") == "1":
            return render(
                request,
                self.form_template,
                self._form_context(ProfileInformationForm(instance=request.user)),
            )
        return render(request, self.display_template, self._display_context(request))

    def post(self, request):
        form = ProfileInformationForm(request.POST, instance=request.user)
        if not form.is_valid():
            response = render(
                request,
                self.form_template,
                self._form_context(form),
                status=400,
            )
            if _is_htmx(request):
                return with_toast(response, "Vérifiez les champs indiqués.", "error")
            return response

        account_profile_service.update_personal_information(
            user=request.user,
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
        )
        request.user.refresh_from_db()
        if not _is_htmx(request):
            return _profile_redirect(request, saved=True)
        response = render(
            request,
            self.display_template,
            {**self._display_context(request), "rail_oob": True},
        )
        return with_toast(response, "Vos informations ont été enregistrées.")

    def _display_context(self, request) -> dict[str, object]:
        return {"nav_mode": _nav_mode(request)}

    def _form_context(self, form: ProfileInformationForm) -> dict[str, object]:
        return {
            "form": form,
            "nav_mode": _nav_mode(self.request),
        }


class ClientCompanyProfileView(ScopedCustomerMixin, View):
    display_template = "portal/client/partials/company_profile_display.html"
    form_template = "portal/client/partials/company_profile_form.html"

    def get(self, request, customer_public_id):
        if not _is_htmx(request):
            return HttpResponseRedirect(f"{reverse('portal:profile')}?space=client")
        if request.GET.get("edit") == "1":
            self._require_manager()
            return render(
                request,
                self.form_template,
                self._form_context(ClientCompanyProfileForm(instance=self.customer)),
            )
        return render(request, self.display_template, self._display_context())

    def post(self, request, customer_public_id):
        self._require_manager()
        form = ClientCompanyProfileForm(request.POST, instance=self.customer)
        if not form.is_valid():
            response = render(
                request,
                self.form_template,
                self._form_context(form),
                status=400,
            )
            if _is_htmx(request):
                return with_toast(response, "Vérifiez les champs indiqués.", "error")
            return response

        company_profile_service.update(
            customer=self.customer,
            cleaned_data=form.cleaned_data,
            actor=request.user,
        )
        self.customer.refresh_from_db()
        if not _is_htmx(request):
            return HttpResponseRedirect(f"{reverse('portal:profile')}?space=client&saved=1")
        response = render(request, self.display_template, self._display_context())
        return with_toast(response, "Les informations de la société ont été enregistrées.")

    def _require_manager(self) -> None:
        if not self.customer_membership.can_manage_team:
            raise PermissionDenied

    def _display_context(self) -> dict[str, object]:
        return {
            "customer": self.customer,
            "can_edit_company": self.customer_membership.can_manage_team,
            "company_profile": company_profile_service.present(self.customer),
        }

    def _form_context(self, form: ClientCompanyProfileForm) -> dict[str, object]:
        return {
            "customer": self.customer,
            "can_edit_company": True,
            "company_form": form,
        }
