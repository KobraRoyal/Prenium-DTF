from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.accounts.forms import ProfileInformationForm
from apps.accounts.services.profile import AccountProfileService
from apps.portal.views_common import access_scope_service

account_profile_service = AccountProfileService()


class PortalProfileView(LoginRequiredMixin, View):
    template_name = "portal/profile.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            self._context(
                request,
                form=ProfileInformationForm(instance=request.user),
                saved=request.GET.get("saved") == "1",
            ),
        )

    def post(self, request):
        form = ProfileInformationForm(request.POST, instance=request.user)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                self._context(request, form=form, saved=False),
                status=400,
            )

        account_profile_service.update_personal_information(
            user=request.user,
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
        )
        space = self._nav_mode(request)
        return HttpResponseRedirect(f"{reverse('portal:profile')}?space={space}&saved=1")

    def _nav_mode(self, request) -> str:
        requested_space = request.POST.get("space") or request.GET.get("space")
        if requested_space == "staff" and access_scope_service.can_access_staff_portal(
            request.user
        ):
            return "staff"
        return "client"

    def _context(self, request, *, form, saved: bool) -> dict[str, object]:
        nav_mode = self._nav_mode(request)
        context: dict[str, object] = {
            "form": form,
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
            context.update(
                {
                    "customer": customer,
                    "selected_membership": selected_membership,
                }
            )
        return context
