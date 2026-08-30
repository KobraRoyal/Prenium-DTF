from __future__ import annotations

from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.portal.htmx import with_toast
from apps.portal.views_common import StaffDomainPermissionMixin
from apps.processing_time.forms_staff import StaffProcessingTimeSettingsForm
from apps.processing_time.services.settings import ProcessingTimeSettingsService

processing_time_settings_service = ProcessingTimeSettingsService()


class StaffProcessingTimeSettingsView(StaffDomainPermissionMixin, View):
    required_permission = "customers.manage_customer_pricing"
    template_name = "portal/staff/settings/processing_time.html"

    def get(self, request):
        options = processing_time_settings_service.list_options()
        return render(
            request,
            self.template_name,
            self._context(form=self._build_form(options=options), options=options),
        )

    def post(self, request):
        options = processing_time_settings_service.list_options()
        form = self._build_form(options=options, data=request.POST)
        if form.is_valid():
            processing_time_settings_service.update(
                payloads=form.cleaned_option_payloads(),
                actor=request.user,
                source="staff_portal",
            )
            response = HttpResponseRedirect(reverse("portal:staff-processing-time-settings"))
            return with_toast(response, "Délais de traitement enregistrés.", "success")
        return render(
            request,
            self.template_name,
            self._context(form=form, options=options),
            status=400,
        )

    def _build_form(self, *, options, data=None):
        if data is None:
            return StaffProcessingTimeSettingsForm(options=tuple(options))
        return StaffProcessingTimeSettingsForm(data, options=tuple(options))

    def _context(self, *, form, options):
        option_forms = []
        for option in options:
            prefix = option.code.replace("-", "_")
            option_forms.append(
                {
                    "option": option,
                    "fields": [
                        form[f"{prefix}__name"],
                        form[f"{prefix}__eta_label"],
                        form[f"{prefix}__disclaimer"],
                        form[f"{prefix}__business_days"],
                        form[f"{prefix}__markup_percent"],
                        form[f"{prefix}__flat_fee_eur"],
                        form[f"{prefix}__is_default"],
                        form[f"{prefix}__is_active"],
                        form[f"{prefix}__display_order"],
                    ],
                }
            )
        return {
            "form": form,
            "option_forms": option_forms,
            "nav_mode": "staff",
            "nav_key": "staff-processing-time-settings",
        }
