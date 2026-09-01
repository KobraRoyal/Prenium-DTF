from decimal import Decimal

import pytest
from apps.catalog.services.default_catalog import DefaultCatalogService
from apps.customers.models import (
    Customer,
    CustomerBillingProfile,
    CustomerMembership,
    CustomerVolumeDiscountTier,
    DefaultCustomerVolumeDiscountTier,
)
from apps.customers.services.client_pricing_overview import CustomerPricingOverviewService
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

User = get_user_model()


def _owner_scope(*, email: str, customer: Customer):
    user = User.objects.create_user(email=email, password="pass")
    CustomerMembership.objects.create(
        customer=customer,
        user=user,
        role=CustomerMembership.Role.OWNER,
    )
    return user


@pytest.mark.django_db
def test_pricing_overview_uses_catalog_and_default_ladder_when_customer_has_no_overrides():
    DefaultCatalogService().ensure_default_services()
    DefaultCustomerVolumeDiscountTier.objects.create(
        minimum_monthly_linear_m="25.0000",
        discount_percent="5.00",
    )
    DefaultCustomerVolumeDiscountTier.objects.create(
        minimum_monthly_linear_m="50.0000",
        discount_percent="10.00",
    )
    customer = Customer.objects.create(name="Catalogue")

    overview = CustomerPricingOverviewService().present(customer=customer)

    assert overview.dtf_rate.amount == Decimal("25.00")
    assert overview.dtf_rate.is_personalized is False
    assert overview.dtf_rate.source_label == "Tarif catalogue par défaut"
    assert overview.file_preparation_rate.amount == Decimal("10.00")
    assert overview.file_preparation_rate.is_personalized is False
    assert overview.uses_personalized_volume_discount is False
    assert overview.volume_discount_source_label == "Grille par défaut"
    assert [tier.minimum_monthly_linear_m for tier in overview.volume_discount_tiers] == [
        Decimal("25.0000"),
        Decimal("50.0000"),
    ]


@pytest.mark.django_db
def test_pricing_overview_uses_customer_rates_and_ladder_when_present():
    customer = Customer.objects.create(
        name="Conditions négociées",
        negotiated_file_preparation_fee_eur=Decimal("6.00"),
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur=Decimal("30.00"))
    CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m="12.5000",
        discount_percent="7.50",
    )

    overview = CustomerPricingOverviewService().present(customer=customer)

    assert overview.dtf_rate.amount == Decimal("30.00")
    assert overview.dtf_rate.is_personalized is True
    assert overview.file_preparation_rate.amount == Decimal("6.00")
    assert overview.file_preparation_rate.is_personalized is True
    assert overview.uses_personalized_volume_discount is True
    assert overview.volume_discount_source_label == "Grille personnalisée"
    assert len(overview.volume_discount_tiers) == 1
    assert overview.volume_discount_tiers[0].minimum_monthly_linear_m == Decimal("12.5000")
    assert overview.volume_discount_tiers[0].discount_percent == Decimal("7.50")
    assert "sans effet rétroactif" in overview.volume_discount_application_scope


@pytest.mark.django_db
def test_owner_sees_resolved_pricing_conditions_in_client_profile():
    customer = Customer.objects.create(
        name="Atelier propriétaire",
        negotiated_file_preparation_fee_eur="6.00",
    )
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="30.00")
    CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m="25.0000",
        discount_percent="5.00",
    )
    user = _owner_scope(email="owner-pricing@example.com", customer=customer)
    client = Client()
    assert client.login(email=user.email, password="pass")

    response = client.get(f"{reverse('portal:profile')}?space=client")
    html = response.content.decode()

    assert response.status_code == 200
    assert "Tarifs et remises" in html
    assert "Impression DTF" in html
    assert "Préparation de fichier" in html
    assert html.count("Tarif personnalisé") == 2
    assert "Grille personnalisée" in html
    assert "À partir de" in html
    assert "account-pricing" in html


@pytest.mark.django_db
def test_non_owner_does_not_receive_pricing_conditions_in_client_profile():
    customer = Customer.objects.create(
        name="Atelier non propriétaire",
        negotiated_file_preparation_fee_eur="88.00",
    )
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="99.00")
    CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m="20.0000",
        discount_percent="30.00",
    )
    member = User.objects.create_user(email="member-pricing@example.com", password="pass")
    CustomerMembership.objects.create(
        customer=customer,
        user=member,
        role=CustomerMembership.Role.ADMIN,
    )
    client = Client()
    assert client.login(email=member.email, password="pass")

    response = client.get(f"{reverse('portal:profile')}?space=client")
    html = response.content.decode()

    assert response.status_code == 200
    assert response.context["customer_pricing_overview"] is None
    assert response.context["can_view_pricing"] is False
    assert "Tarifs et remises" not in html
    assert "Tarif personnalisé" not in html
    assert "99.00" not in html
    assert "88.00" not in html
