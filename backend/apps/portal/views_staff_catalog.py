from __future__ import annotations

from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.catalog.forms_staff import StaffDefaultCatalogPricingForm
from apps.catalog.services.default_pricing import DefaultCatalogPricingService
from apps.portal.htmx import with_toast
from apps.portal.views_common import StaffDomainPermissionMixin

default_catalog_pricing_service = DefaultCatalogPricingService()


class StaffDefaultCatalogPricingSettingsView(StaffDomainPermissionMixin, View):
    required_permission = "customers.manage_customer_pricing"
    template_name = "portal/staff/settings/catalog_pricing.html"

    def get(self, request):
        snapshot = default_catalog_pricing_service.snapshot()
        return render(
            request,
            self.template_name,
            self._context(form=self._build_form(snapshot=snapshot), snapshot=snapshot),
        )

    def post(self, request):
        snapshot = default_catalog_pricing_service.snapshot()
        form = self._build_form(snapshot=snapshot, data=request.POST)
        if form.is_valid():
            default_catalog_pricing_service.update(
                dtf_price_per_sqm_eur=form.cleaned_data["dtf_price_per_sqm_eur"],
                file_preparation_fee_eur=form.cleaned_data["file_preparation_fee_eur"],
                shipping_prices=form.shipping_prices(),
                actor=request.user,
                source="staff_portal",
            )
            response = HttpResponseRedirect(
                reverse("portal:staff-default-catalog-pricing-settings")
            )
            return with_toast(response, "Grille tarifaire par défaut enregistrée.", "success")
        return render(
            request,
            self.template_name,
            self._context(form=form, snapshot=snapshot),
            status=400,
        )

    def _build_form(self, *, snapshot, data=None):
        shipping_methods = tuple(row.method for row in snapshot.shipping_methods)
        initial = {
            "dtf_price_per_sqm_eur": snapshot.dtf_price_per_sqm_eur,
            "file_preparation_fee_eur": snapshot.file_preparation_fee_eur,
        }
        for row in snapshot.shipping_methods:
            field_name = DefaultCatalogPricingService.shipping_field_name(row.method.code)
            initial[field_name] = row.base_price_eur
        if data is None:
            return StaffDefaultCatalogPricingForm(
                initial=initial,
                shipping_methods=shipping_methods,
            )
        return StaffDefaultCatalogPricingForm(
            data,
            shipping_methods=shipping_methods,
        )

    def _context(self, *, form, snapshot):
        production_fields = ("dtf_price_per_sqm_eur", "file_preparation_fee_eur")
        shipping_fields = tuple(
            DefaultCatalogPricingService.shipping_field_name(row.method.code)
            for row in snapshot.shipping_methods
        )
        return {
            "form": form,
            "production_fields": [form[field_name] for field_name in production_fields],
            "shipping_fields": [form[field_name] for field_name in shipping_fields],
            "nav_mode": "staff",
            "nav_key": "staff-default-catalog-pricing",
        }
