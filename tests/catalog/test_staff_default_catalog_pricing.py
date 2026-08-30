from decimal import Decimal

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.catalog.models import CatalogService
from apps.catalog.services.default_catalog import DefaultCatalogService
from apps.customers.models import Customer
from apps.orders.services.pricing import OrderPricingService
from apps.shipping.models import ShippingMethod
from apps.shipping.services.methods import ShippingMethodService
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse


def _catalog_services():
    DefaultCatalogService().ensure_default_services()
    return (
        CatalogService.objects.get(code="seed-dtf-meter"),
        CatalogService.objects.get(code="seed-file-prep"),
    )


def _staff_user(*, email: str, pricing_permission: bool):
    user = get_user_model().objects.create_user(email=email, password="pass", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    if pricing_permission:
        user.user_permissions.add(Permission.objects.get(codename="manage_customer_pricing"))
    return user


def _pricing_post_payload(**overrides):
    ShippingMethodService().ensure_default_methods()
    payload = {
        "dtf_price_per_sqm_eur": "25.00",
        "file_preparation_fee_eur": "10.00",
        "shipping_price_standard": "8.00",
        "shipping_price_express": "18.00",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_staff_default_catalog_pricing_requires_permission():
    _catalog_services()
    staff = _staff_user(email="viewer@example.com", pricing_permission=False)
    client = Client()
    assert client.login(email=staff.email, password="pass")

    response = client.get(reverse("portal:staff-default-catalog-pricing-settings"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_staff_can_view_and_update_default_catalog_pricing():
    dtf, file_prep = _catalog_services()
    staff = _staff_user(email="pricing@example.com", pricing_permission=True)
    client = Client()
    assert client.login(email=staff.email, password="pass")
    url = reverse("portal:staff-default-catalog-pricing-settings")

    response = client.get(url)
    html = response.content.decode()
    assert response.status_code == 200
    assert "Grille tarifaire par défaut" in html
    assert "Prix DTF au m² (EUR)" in html
    assert "Forfait préparation fichier (EUR / fichier)" in html
    assert "Transport" in html
    assert "Livraison standard" in html
    assert "Livraison express" in html
    assert "Retrait atelier" in html
    assert 'value="25.00"' in html
    assert 'value="10.00"' in html
    assert 'value="8.00"' in html
    assert 'value="18.00"' in html

    response = client.post(
        url,
        _pricing_post_payload(
            dtf_price_per_sqm_eur="27.50",
            file_preparation_fee_eur="12.00",
            shipping_price_standard="9.50",
            shipping_price_express="20.00",
        ),
    )
    assert response.status_code == 302
    assert response.url == url

    dtf.refresh_from_db()
    file_prep.refresh_from_db()
    standard = ShippingMethod.objects.get(code="standard")
    express = ShippingMethod.objects.get(code="express")
    pickup = ShippingMethod.objects.get(code="pickup")
    assert dtf.base_price == Decimal("27.50")
    assert file_prep.base_price == Decimal("12.00")
    assert standard.base_price == Decimal("9.50")
    assert express.base_price == Decimal("20.00")
    assert pickup.base_price == Decimal("0.00")
    assert AuditLogEntry.objects.filter(action="catalog.default_pricing_updated").exists()


@pytest.mark.django_db
def test_default_dtf_service_prefers_seed_catalog_over_test_service():
    CatalogService.objects.filter(code__in=["seed-dtf-meter", "seed-file-prep"]).delete()
    CatalogService.objects.create(
        code="dtf-upload-x",
        name="DTF test",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="9.00",
        display_order=0,
    )
    DefaultCatalogService().ensure_default_services()
    seed_dtf = CatalogService.objects.get(code="seed-dtf-meter")

    pricing = OrderPricingService()
    assert pricing.get_default_dtf_service().code == seed_dtf.code
    assert pricing.get_default_dtf_service().base_price == Decimal("25.00")


@pytest.mark.django_db
def test_order_pricing_uses_updated_default_catalog_prices():
    _catalog_services()
    staff = _staff_user(email="pricing@example.com", pricing_permission=True)
    client = Client()
    assert client.login(email=staff.email, password="pass")
    client.post(
        reverse("portal:staff-default-catalog-pricing-settings"),
        _pricing_post_payload(
            dtf_price_per_sqm_eur="30.00",
            file_preparation_fee_eur="11.00",
        ),
    )

    customer = Customer.objects.create(name="Client test")
    pricing = OrderPricingService()
    assert pricing.resolve_unit_price_per_sqm(customer=customer) == Decimal("30.00")
    assert pricing.resolve_file_preparation_fee_per_file(customer=customer) == Decimal("11.00")


@pytest.mark.django_db
def test_shipping_method_service_uses_updated_standard_price():
    _catalog_services()
    staff = _staff_user(email="pricing@example.com", pricing_permission=True)
    client = Client()
    assert client.login(email=staff.email, password="pass")
    client.post(
        reverse("portal:staff-default-catalog-pricing-settings"),
        _pricing_post_payload(shipping_price_standard="11.00"),
    )

    shipping = ShippingMethodService()
    method = shipping.require_active_by_code("standard")
    assert method.base_price == Decimal("11.00")
    assert method.resolved_price == Decimal("11.00")
