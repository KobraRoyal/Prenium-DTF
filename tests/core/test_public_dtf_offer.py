from decimal import Decimal

import pytest
from apps.catalog.models import CatalogService
from apps.core.services.marketing import PublicDtfOfferService
from apps.customers.models import (
    Customer,
    CustomerBillingProfile,
    CustomerVolumeDiscountTier,
    DefaultCustomerVolumeDiscountTier,
)
from django.test import Client, override_settings
from django.urls import reverse


def public_catalog(price="25.00"):
    return CatalogService.objects.create(
        code="seed-dtf-meter",
        name="DTF au m²",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price=price,
    )


@pytest.mark.django_db
@override_settings(DTF_LAIZE_CM=55)
def test_public_offer_uses_default_catalog_and_only_active_global_tiers():
    service = public_catalog()
    CatalogService.objects.create(
        code="other-dtf",
        name="Other",
        base_price="1.00",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        display_order=0,
    )
    DefaultCustomerVolumeDiscountTier.objects.all().delete()
    DefaultCustomerVolumeDiscountTier.objects.create(
        minimum_monthly_linear_m="25",
        discount_percent="5",
    )
    DefaultCustomerVolumeDiscountTier.objects.create(
        minimum_monthly_linear_m="50",
        discount_percent="8",
        is_active=False,
    )
    offer = PublicDtfOfferService().snapshot()
    assert offer["price_per_m"] == Decimal("13.75")
    assert offer["pricing"] == {
        "pricePerSqmCents": 2500,
        "widthCm": 55,
        "tiers": [{"minimum": "25.0000", "percent": "5.00"}],
    }
    service.base_price = Decimal("30.00")
    service.save(update_fields=["base_price"])
    assert PublicDtfOfferService().snapshot()["price_per_m"] == Decimal("16.50")


@pytest.mark.django_db
@override_settings(DTF_LAIZE_CM=60)
def test_public_offer_converts_the_configured_laize_and_never_bootstraps_missing_catalog():
    CatalogService.objects.all().delete()
    assert PublicDtfOfferService().snapshot()["pricing"] is None
    assert not CatalogService.objects.exists()
    public_catalog("27.50")
    assert PublicDtfOfferService().snapshot()["price_per_m"] == Decimal("16.50")


@pytest.mark.django_db
@override_settings(DTF_LAIZE_CM=55)
def test_public_page_never_exposes_negotiated_customer_pricing_or_ids():
    public_catalog()
    customer = Customer.objects.create(name="Private tenant example")
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="7.77")
    CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m="123.4567",
        discount_percent="37.77",
    )
    response = Client().get(reverse("home"))
    body = response.content.decode()
    assert response.status_code == 200
    for private in (customer.name, str(customer.public_id), "7.77", "37.77", "123.4567"):
        assert private not in body
    assert "pricePerSqmCents" in body
    assert "2500" in body
    assert "6 € HT" in body
    assert "sans rétroactivité" in body


@pytest.mark.django_db
def test_public_get_does_not_create_a_catalog_when_it_is_missing():
    CatalogService.objects.all().delete()
    response = Client().get(reverse("home"))
    assert response.status_code == 200
    assert not CatalogService.objects.exists()
    assert "grille est en cours de mise à jour" in response.content.decode()
    assert "dtf-public-pricing" not in response.content.decode()
    assert "data-hero-price" not in response.content.decode()


@pytest.mark.django_db
def test_public_offer_does_not_label_foreign_currency_as_euros():
    service = public_catalog()
    service.currency = "USD"
    service.save(update_fields=["currency"])
    assert PublicDtfOfferService().snapshot()["pricing"] is None
    assert "data-hero-price" not in Client().get(reverse("home")).content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("catalog_price", "width_cm", "display_price"),
    [("25.00", 55, "13,75"), ("30.00", 55, "16,50"), ("25.00", 60, "15,00")],
)
def test_hero_displays_the_current_public_base_price_and_configured_width(
    catalog_price, width_cm, display_price,
):
    CatalogService.objects.all().delete()
    public_catalog(catalog_price)
    with override_settings(DTF_LAIZE_CM=width_cm):
        body = Client().get(reverse("home")).content.decode()
    hero = body.split('class="dtf-hero dtf-shell"', 1)[1].split("</section>", 1)[0]
    assert f'data-hero-price>{display_price}&nbsp;€' in hero
    assert f"largeur {width_cm} cm" in hero
    assert "Tarif de base" in hero
    assert "Hors transport et préparation" in hero
    assert "Dégressif selon votre volume mensuel" in hero
    assert 'href="#tarifs"' in hero
    assert "Simuler mon tarif" in hero
    assert reverse("prospects:step1") in hero
    assert f'data-unit-price aria-live="off">{display_price} €' in body
    assert "à partir" not in hero.lower()
