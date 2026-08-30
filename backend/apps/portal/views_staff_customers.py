from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from apps.billing.forms import BillingStatementMonthForm
from apps.billing.services.statements import BillingStatementService
from apps.customers.forms_staff import (
    StaffCustomerAccountForm,
    StaffCustomerPricingForm,
    StaffCustomerVolumeDiscountTierForm,
    StaffDefaultCustomerVolumeDiscountTierForm,
    StaffVolumeDiscountDashboardCopyForm,
)
from apps.customers.models import (
    CustomerVolumeDiscountTier,
    DefaultCustomerVolumeDiscountTier,
)
from apps.customers.services.administration import CustomerAdministrationService
from apps.customers.services.volume_discounts import (
    CustomerVolumeDiscountTierService,
    DefaultCustomerVolumeDiscountTierService,
)
from apps.customers.services.volume_nudge_copy import (
    NUDGE_COPY_STAGES,
    VolumeDiscountDashboardCopyService,
)
from apps.processing_time.forms_staff import StaffCustomerProcessingTimeOverridesForm
from apps.processing_time.services.customer_overrides import CustomerProcessingTimeOverrideService
from apps.portal.views_common import StaffDomainPermissionMixin

customer_admin_service = CustomerAdministrationService()
volume_discount_service = CustomerVolumeDiscountTierService()
default_volume_discount_service = DefaultCustomerVolumeDiscountTierService()
volume_nudge_copy_service = VolumeDiscountDashboardCopyService()
billing_statement_service = BillingStatementService()
processing_time_override_service = CustomerProcessingTimeOverrideService()


def _copy_form_audience(form) -> str:
    if any(form.errors.get(f"{stage}_deferred") for stage, _title, _hint in NUDGE_COPY_STAGES):
        return "deferred"
    return "immediate"


class StaffDefaultVolumeDiscountSettingsView(StaffDomainPermissionMixin, View):
    required_permission = "customers.manage_customer_pricing"
    template_name = "portal/staff/customers/default_volume_discounts.html"

    def get(self, request):
        audience = request.GET.get("audience")
        if audience not in {"immediate", "deferred"}:
            audience = "immediate"
        return render(
            request,
            self.template_name,
            self._context(copy_audience=audience),
        )

    def _context(
        self,
        *,
        add_form=None,
        update_form=None,
        update_public_id=None,
        copy_form=None,
        copy_audience="immediate",
    ):
        tiers = list(default_volume_discount_service.list_tiers())
        rows = []
        for position, tier in enumerate(tiers, start=1):
            form = (
                update_form
                if update_form is not None and tier.public_id == update_public_id
                else StaffDefaultCustomerVolumeDiscountTierForm(
                    instance=tier,
                    prefix=f"tier-{tier.public_id}",
                )
            )
            rows.append({"tier": tier, "form": form, "position": position})
        if copy_form is None:
            stored = volume_nudge_copy_service.stored_messages()
            copy_form = StaffVolumeDiscountDashboardCopyForm(initial=stored)
        active_tier_count = sum(tier.is_active for tier in tiers)
        return {
            "tier_rows": rows,
            "active_tier_count": active_tier_count,
            "inactive_tier_count": len(tiers) - active_tier_count,
            "add_form": add_form or StaffDefaultCustomerVolumeDiscountTierForm(prefix="new"),
            "copy_form": copy_form,
            "copy_audience": copy_audience,
            "nav_mode": "staff",
            "nav_key": "staff-default-volume-discounts",
        }


class StaffVolumeDiscountDashboardCopyUpdateView(StaffDomainPermissionMixin, View):
    required_permission = "customers.manage_customer_pricing"

    def post(self, request):
        audience = request.POST.get("audience")
        if audience not in {"immediate", "deferred"}:
            audience = "immediate"
        if request.POST.get("restore_defaults"):
            volume_nudge_copy_service.restore_defaults(
                actor=request.user,
                source="staff_portal",
            )
            return with_toast(
                redirect(
                    f"{reverse('portal:staff-default-volume-discount-settings')}"
                    f"?audience={audience}#volume-nudge-copy"
                ),
                message="Textes Prenium rétablis.",
                variant="success",
            )
        form = StaffVolumeDiscountDashboardCopyForm(request.POST)
        if not form.is_valid():
            response = render(
                request,
                StaffDefaultVolumeDiscountSettingsView.template_name,
                StaffDefaultVolumeDiscountSettingsView()._context(
                    copy_form=form,
                    copy_audience=_copy_form_audience(form),
                ),
            )
            return with_toast(response, message="Corrigez les messages dashboard.", variant="error")
        volume_nudge_copy_service.update(
            cleaned_data=form.cleaned_data,
            actor=request.user,
            source="staff_portal",
        )
        return with_toast(
            redirect(
                f"{reverse('portal:staff-default-volume-discount-settings')}"
                f"?audience={audience}#volume-nudge-copy"
            ),
            message="Messages dashboard enregistrés.",
            variant="success",
        )


class StaffDefaultVolumeDiscountTierCreateView(StaffDomainPermissionMixin, View):
    required_permission = "customers.manage_customer_pricing"

    def post(self, request):
        form = StaffDefaultCustomerVolumeDiscountTierForm(request.POST, prefix="new")
        if form.is_valid():
            try:
                default_volume_discount_service.create_tier(
                    cleaned_data=form.cleaned_data,
                    actor=request.user,
                    source="staff_portal",
                )
            except ValidationError as exc:
                form.add_error(None, exc)
        if not form.is_valid() or form.non_field_errors():
            messages.error(request, "Corrigez les erreurs du palier par défaut.")
            response = render(
                request,
                StaffDefaultVolumeDiscountSettingsView.template_name,
                StaffDefaultVolumeDiscountSettingsView()._context(add_form=form),
            )
            return with_toast(response, message="Palier par défaut invalide.", variant="error")
        messages.success(request, "Palier par défaut ajouté.")
        return with_toast(
            redirect("portal:staff-default-volume-discount-settings"),
            message="Palier par défaut ajouté.",
            variant="success",
        )


class StaffDefaultVolumeDiscountTierUpdateView(StaffDomainPermissionMixin, View):
    required_permission = "customers.manage_customer_pricing"

    def post(self, request, tier_public_id):
        tier = default_volume_discount_service.get_tier(tier_public_id=tier_public_id)
        if tier is None:
            raise Http404
        prefix = f"tier-{tier.public_id}"
        form = StaffDefaultCustomerVolumeDiscountTierForm(
            request.POST,
            instance=tier,
            prefix=prefix,
        )
        if form.is_valid():
            try:
                default_volume_discount_service.update_tier(
                    tier_public_id=tier.public_id,
                    cleaned_data=form.cleaned_data,
                    actor=request.user,
                    source="staff_portal",
                )
            except DefaultCustomerVolumeDiscountTier.DoesNotExist as exc:
                raise Http404 from exc
            except ValidationError as exc:
                form.add_error(None, exc)
        if not form.is_valid() or form.non_field_errors():
            messages.error(request, "Corrigez les erreurs du palier par défaut.")
            response = render(
                request,
                StaffDefaultVolumeDiscountSettingsView.template_name,
                StaffDefaultVolumeDiscountSettingsView()._context(
                    update_form=form,
                    update_public_id=tier.public_id,
                ),
            )
            return with_toast(response, message="Palier par défaut invalide.", variant="error")
        messages.success(request, "Palier par défaut enregistré.")
        return with_toast(
            redirect("portal:staff-default-volume-discount-settings"),
            message="Palier par défaut enregistré.",
            variant="success",
        )


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

    def _context(
        self,
        request,
        customer,
        *,
        account_form=None,
        pricing_form=None,
        processing_time_form=None,
        tier_add_form=None,
        tier_update_form=None,
        tier_update_public_id=None,
        billing_statement_form=None,
    ):
        can_edit_account = request.user.has_perm("customers.change_customer")
        can_edit_pricing = request.user.has_perm("customers.manage_customer_pricing")
        can_view_billing_statements = request.user.has_perm("billing.view_billingstatement")
        can_generate_billing_statements = can_view_billing_statements and request.user.has_perm(
            "billing.add_billingstatement"
        )
        tiers = list(volume_discount_service.list_tiers(customer=customer))
        summary = volume_discount_service.get_current_month_summary(customer=customer)
        tier_rows = []
        for position, tier in enumerate(tiers, start=1):
            if tier_update_form is not None and tier.public_id == tier_update_public_id:
                form = tier_update_form
            else:
                form = StaffCustomerVolumeDiscountTierForm(
                    instance=tier,
                    prefix=f"tier-{tier.public_id}",
                )
            state = "upcoming"
            state_label = "À venir"
            state_badge_class = "is-neutral"
            if not tier.is_active:
                state = "inactive"
                state_label = ""
            elif summary["current_tier"] and tier.pk == summary["current_tier"].pk:
                state = "current"
                state_label = "Palier atteint"
                state_badge_class = "is-success"
            elif tier.minimum_monthly_linear_m <= summary["monthly_volume_linear_m"]:
                state = "reached"
                state_label = "Franchi"
                state_badge_class = "is-success"
            elif summary["next_tier"] and tier.pk == summary["next_tier"].pk:
                state = "next"
                state_label = "Prochain objectif"
                state_badge_class = "is-warning"
            tier_rows.append(
                {
                    "tier": tier,
                    "form": form,
                    "position": position,
                    "state": state,
                    "state_label": state_label,
                    "state_badge_class": state_badge_class,
                }
            )
        resolved_account_form = account_form or (
            StaffCustomerAccountForm(instance=customer) if can_edit_account else None
        )
        resolved_pricing_form = pricing_form or (
            StaffCustomerPricingForm.from_customer(customer) if can_edit_pricing else None
        )
        resolved_processing_time_form = processing_time_form or (
            StaffCustomerProcessingTimeOverridesForm.from_customer(customer)
            if can_edit_pricing
            else None
        )
        processing_time_rows = processing_time_override_service.rows_for_staff_form(customer)
        processing_time_option_forms = []
        if resolved_processing_time_form is not None:
            for row in processing_time_rows:
                code = row["option"].code.replace("-", "_")
                processing_time_option_forms.append(
                    {
                        "row": row,
                        "fields": [
                            resolved_processing_time_form[f"{code}__is_enabled"],
                            resolved_processing_time_form[f"{code}__markup_percent"],
                            resolved_processing_time_form[f"{code}__flat_fee_eur"],
                        ],
                    }
                )
        resolved_tier_add_form = tier_add_form or StaffCustomerVolumeDiscountTierForm(prefix="new")
        resolved_billing_statement_form = (
            billing_statement_form or BillingStatementMonthForm(prefix="statement")
            if can_generate_billing_statements
            else None
        )
        address_fields = {
            "billing_address_line1",
            "billing_address_line2",
            "billing_postal_code",
            "billing_city",
            "billing_country",
            "shipping_address_line1",
            "shipping_address_line2",
            "shipping_postal_code",
            "shipping_city",
            "shipping_country",
        }
        return {
            "customer": customer,
            "memberships": customer_admin_service.list_memberships(customer=customer),
            "billing_profile": getattr(customer, "billing_profile", None),
            "account_form": resolved_account_form,
            "account_address_has_errors": bool(
                resolved_account_form
                and any(field in resolved_account_form.errors for field in address_fields)
            ),
            "account_notes_has_errors": bool(
                resolved_account_form and "notes" in resolved_account_form.errors
            ),
            "pricing_form": resolved_pricing_form,
            "processing_time_form": resolved_processing_time_form,
            "processing_time_rows": processing_time_rows,
            "processing_time_option_forms": processing_time_option_forms,
            "processing_time_has_customizations": processing_time_override_service.customer_has_customizations(
                customer
            ),
            "can_edit_account": can_edit_account,
            "can_edit_pricing": can_edit_pricing,
            "volume_discount_tiers": tiers,
            "volume_discount_tier_rows": tier_rows,
            "volume_discount_tier_add_form": resolved_tier_add_form,
            "volume_discount_has_errors": bool(
                resolved_tier_add_form.errors or any(row["form"].errors for row in tier_rows)
            ),
            "volume_discount_available": customer.default_billing_mode in {"deferred", "immediate"},
            "volume_discount_summary": summary,
            "volume_discount_progress_value": f"{summary['monthly_volume_linear_m']:f}",
            "volume_discount_progress_max": (
                f"{summary['next_tier'].minimum_monthly_linear_m:f}"
                if summary["next_tier"]
                else None
            ),
            "can_view_billing_statements": can_view_billing_statements,
            "can_generate_billing_statements": can_generate_billing_statements,
            "billing_statements": (
                list(billing_statement_service.list_for_customer(customer=customer))
                if can_view_billing_statements
                else []
            ),
            "billing_statement_form": resolved_billing_statement_form,
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


class StaffCustomerProcessingTimeUpdateView(StaffDomainPermissionMixin, View):
    required_permission = "customers.manage_customer_pricing"

    def post(self, request, customer_public_id):
        customer = customer_admin_service.get_customer(customer_public_id=customer_public_id)
        if customer is None:
            raise Http404
        form = StaffCustomerProcessingTimeOverridesForm(request.POST, rows=processing_time_override_service.rows_for_staff_form(customer))
        detail_url = reverse(
            "portal:staff-customer-detail",
            kwargs={"customer_public_id": customer.public_id},
        )
        if not form.is_valid():
            messages.error(request, "Corrigez les erreurs des délais de traitement client.")
            response = render(
                request,
                "portal/staff/customers/detail.html",
                StaffCustomerDetailView()._context(request, customer, processing_time_form=form),
            )
            return with_toast(
                response,
                message="Délais de traitement client invalides.",
                variant="error",
            )
        processing_time_override_service.update_for_customer(
            customer=customer,
            payloads=form.cleaned_option_payloads(),
            actor=request.user,
            source="staff_portal",
        )
        messages.success(request, "Délais de traitement client enregistrés.")
        response = redirect(f"{detail_url}#customer-processing-time")
        return with_toast(
            response,
            message="Délais de traitement client enregistrés.",
            variant="success",
        )


class StaffCustomerVolumeDiscountTierCreateView(StaffDomainPermissionMixin, View):
    required_permission = "customers.manage_customer_pricing"

    def post(self, request, customer_public_id):
        customer = customer_admin_service.get_customer(customer_public_id=customer_public_id)
        if customer is None:
            raise Http404
        form = StaffCustomerVolumeDiscountTierForm(request.POST, prefix="new")
        detail_url = reverse(
            "portal:staff-customer-detail",
            kwargs={"customer_public_id": customer.public_id},
        )
        if form.is_valid():
            try:
                _tier, summary = volume_discount_service.create_tier(
                    customer=customer,
                    cleaned_data=form.cleaned_data,
                    actor=request.user,
                    source="staff_portal",
                )
            except ValidationError as exc:
                form.add_error(None, exc)
        if not form.is_valid() or form.non_field_errors():
            messages.error(request, "Corrigez les erreurs du nouveau palier.")
            response = render(
                request,
                "portal/staff/customers/detail.html",
                StaffCustomerDetailView()._context(
                    request,
                    customer,
                    tier_add_form=form,
                ),
            )
            return with_toast(response, message="Palier invalide.", variant="error")

        count = summary["repriced_count"]
        if customer.default_billing_mode == "immediate":
            message = "Palier ajouté. Les commandes déjà payées conservent leur tarif."
        else:
            message = f"Palier ajouté. {count} commande(s) du mois recalculée(s)."
        messages.success(request, message)
        return with_toast(redirect(detail_url), message=message, variant="success")


class StaffCustomerVolumeDiscountTierUpdateView(StaffDomainPermissionMixin, View):
    required_permission = "customers.manage_customer_pricing"

    def post(self, request, customer_public_id, tier_public_id):
        customer = customer_admin_service.get_customer(customer_public_id=customer_public_id)
        if customer is None:
            raise Http404
        tier = volume_discount_service.get_tier(
            customer=customer,
            tier_public_id=tier_public_id,
        )
        if tier is None:
            raise Http404
        prefix = f"tier-{tier.public_id}"
        form = StaffCustomerVolumeDiscountTierForm(request.POST, instance=tier, prefix=prefix)
        detail_url = reverse(
            "portal:staff-customer-detail",
            kwargs={"customer_public_id": customer.public_id},
        )
        if form.is_valid():
            try:
                _tier, summary = volume_discount_service.update_tier(
                    customer=customer,
                    tier_public_id=tier.public_id,
                    cleaned_data=form.cleaned_data,
                    actor=request.user,
                    source="staff_portal",
                )
            except CustomerVolumeDiscountTier.DoesNotExist as exc:
                raise Http404 from exc
            except ValidationError as exc:
                form.add_error(None, exc)
        if not form.is_valid() or form.non_field_errors():
            messages.error(request, "Corrigez les erreurs du palier.")
            response = render(
                request,
                "portal/staff/customers/detail.html",
                StaffCustomerDetailView()._context(
                    request,
                    customer,
                    tier_update_form=form,
                    tier_update_public_id=tier.public_id,
                ),
            )
            return with_toast(response, message="Palier invalide.", variant="error")

        count = summary["repriced_count"]
        if customer.default_billing_mode == "immediate":
            message = "Palier enregistré. Les commandes déjà payées conservent leur tarif."
        else:
            message = f"Palier enregistré. {count} commande(s) du mois recalculée(s)."
        messages.success(request, message)
        return with_toast(redirect(detail_url), message=message, variant="success")
