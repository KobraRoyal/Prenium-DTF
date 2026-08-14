from __future__ import annotations

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q

from apps.auditlog.services import record_event
from apps.customers.models import Customer, CustomerBillingProfile, CustomerMembership


class CustomerAdministrationService:
    """Administration staff des comptes clients et conditions tarifaires."""

    def list_customers(self, *, search: str = "", active_only: bool | None = None):
        queryset = Customer.objects.all().select_related("billing_profile")
        query = (search or "").strip()
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(billing_email__icontains=query)
                | Q(siren__icontains=query)
                | Q(vat_number__icontains=query)
            )
        if active_only is True:
            queryset = queryset.filter(is_active=True)
        elif active_only is False:
            queryset = queryset.filter(is_active=False)
        return queryset.order_by("name")

    def paginate_customers(self, queryset, *, page_number, page_size: int = 25):
        return Paginator(queryset, page_size).get_page(page_number)

    def get_customer(self, *, customer_public_id):
        return (
            Customer.objects.select_related("billing_profile")
            .prefetch_related("memberships__user", "volume_discount_tiers")
            .filter(public_id=customer_public_id)
            .first()
        )

    def list_memberships(self, *, customer: Customer):
        return (
            CustomerMembership.objects.for_customer(customer)
            .select_related("user")
            .order_by("role", "user__email")
        )

    @transaction.atomic
    def update_account(
        self,
        *,
        customer: Customer,
        cleaned_data: dict,
        actor,
        source: str,
    ) -> Customer:
        tracked_fields = (
            "name",
            "billing_email",
            "siren",
            "vat_number",
            "is_active",
            "default_billing_mode",
            "preferred_settlement_method",
            "default_shipping_mode",
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
            "notes",
        )
        before = {field: getattr(customer, field) for field in tracked_fields}
        for field in tracked_fields:
            setattr(customer, field, cleaned_data[field])
        customer.save(update_fields=[*tracked_fields, "updated_at"])
        if (
            before["default_billing_mode"] != Customer.DefaultBillingMode.DEFERRED
            and customer.default_billing_mode == Customer.DefaultBillingMode.DEFERRED
        ):
            from apps.customers.services.volume_discounts import (
                DefaultCustomerVolumeDiscountTierService,
            )

            DefaultCustomerVolumeDiscountTierService().apply_to_customer(
                customer=customer,
                actor=actor,
                source=f"{source}.billing_mode_changed",
            )
        after = {field: getattr(customer, field) for field in tracked_fields}
        changes = {
            field: {"before": _serialize(before[field]), "after": _serialize(after[field])}
            for field in tracked_fields
            if before[field] != after[field]
        }
        record_event(
            action="customer.account_updated",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=customer,
            metadata={
                "customer_public_id": str(customer.public_id),
                "source": source,
                "changes": changes,
            },
        )
        return customer

    @transaction.atomic
    def update_pricing_conditions(
        self,
        *,
        customer: Customer,
        cleaned_data: dict,
        actor,
        source: str,
    ) -> Customer:
        profile, _created = CustomerBillingProfile.objects.get_or_create(
            customer=customer,
            defaults={
                "billing_cycle": cleaned_data["billing_cycle"],
                "credit_limit_eur": cleaned_data.get("credit_limit_eur"),
                "enforce_credit_block": bool(cleaned_data.get("enforce_credit_block")),
                "price_per_sqm_eur": cleaned_data.get("price_per_sqm_eur"),
            },
        )
        profile = CustomerBillingProfile.objects.select_for_update().get(pk=profile.pk)

        before = {
            "negotiated_file_preparation_fee_eur": customer.negotiated_file_preparation_fee_eur,
            "price_per_sqm_eur": profile.price_per_sqm_eur,
            "billing_cycle": profile.billing_cycle,
            "credit_limit_eur": profile.credit_limit_eur,
            "enforce_credit_block": profile.enforce_credit_block,
        }

        customer.negotiated_file_preparation_fee_eur = cleaned_data.get(
            "negotiated_file_preparation_fee_eur"
        )
        customer.save(update_fields=["negotiated_file_preparation_fee_eur", "updated_at"])

        profile.billing_cycle = cleaned_data["billing_cycle"]
        profile.credit_limit_eur = cleaned_data.get("credit_limit_eur")
        profile.enforce_credit_block = bool(cleaned_data.get("enforce_credit_block"))
        profile.price_per_sqm_eur = cleaned_data.get("price_per_sqm_eur")
        profile.save(
            update_fields=[
                "billing_cycle",
                "credit_limit_eur",
                "enforce_credit_block",
                "price_per_sqm_eur",
                "updated_at",
            ]
        )

        after = {
            "negotiated_file_preparation_fee_eur": customer.negotiated_file_preparation_fee_eur,
            "price_per_sqm_eur": profile.price_per_sqm_eur,
            "billing_cycle": profile.billing_cycle,
            "credit_limit_eur": profile.credit_limit_eur,
            "enforce_credit_block": profile.enforce_credit_block,
        }
        changes = {
            key: {"before": _serialize(before[key]), "after": _serialize(after[key])}
            for key in before
            if before[key] != after[key]
        }
        record_event(
            action="customer.pricing_conditions_updated",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=customer,
            metadata={
                "customer_public_id": str(customer.public_id),
                "billing_profile_public_id": str(profile.public_id),
                "source": source,
                "changes": changes,
            },
        )
        return customer


def _serialize(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
