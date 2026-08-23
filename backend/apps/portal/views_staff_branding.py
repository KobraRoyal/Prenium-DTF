from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.branding.forms import BrandThemeSettingsForm
from apps.branding.models import BrandThemeSettings
from apps.branding.services import brand_theme_service
from apps.portal.htmx import with_toast
from apps.portal.views_common import StaffDomainPermissionMixin


class StaffBrandSettingsView(StaffDomainPermissionMixin, View):
    required_permission = "branding.view_brandthemesettings"
    template_name = "portal/staff/settings/branding.html"

    def _context(self, *, form):
        return {
            "form": form,
            "nav_mode": "staff",
            "nav_key": "staff-brand-settings",
            "can_change_brand_theme": self.request.user.has_perm(
                "branding.change_brandthemesettings"
            ),
        }

    def get(self, request):
        settings_row = brand_theme_service.current_settings()
        form = BrandThemeSettingsForm(
            instance=settings_row,
            initial=(
                None
                if settings_row
                else {
                    "primary_color": "#FF8775",
                    "secondary_color": "#A83BC4",
                }
            ),
        )
        return render(request, self.template_name, self._context(form=form))

    def post(self, request):
        if not request.user.has_perm("branding.change_brandthemesettings"):
            raise PermissionDenied

        settings_row = brand_theme_service.current_settings() or BrandThemeSettings()
        ip_address = request.META.get("REMOTE_ADDR")
        if request.POST.get("intent") == "restore":
            brand_theme_service.restore_defaults(
                actor=request.user,
                source="staff_brand_settings",
                ip_address=ip_address,
            )
            response = HttpResponseRedirect(reverse("portal:staff-brand-settings"))
            return with_toast(response, "Palette claire par défaut restaurée.", "success")

        form = BrandThemeSettingsForm(request.POST, instance=settings_row)
        if form.is_valid():
            brand_theme_service.update(
                primary_color=form.cleaned_data["primary_color"],
                secondary_color=form.cleaned_data["secondary_color"],
                actor=request.user,
                source="staff_brand_settings",
                ip_address=ip_address,
            )
            response = HttpResponseRedirect(reverse("portal:staff-brand-settings"))
            return with_toast(response, "Identité visuelle mise à jour.", "success")
        return render(request, self.template_name, self._context(form=form), status=400)
