from decimal import Decimal

import pytest
from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerBillingProfile, CustomerMembership
from apps.orders.models import Order
from apps.orders.services.pricing import OrderPricingService
from apps.shipping.services.methods import ShippingMethodService
from apps.uploads.models import OrderUpload, OrderUploadInspection
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import override_settings


def _seed_catalog(*, dtf_price="25.00", prep_price="5.00"):
    CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price=dtf_price,
        currency="EUR",
        display_order=1,
    )
    CatalogService.objects.create(
        code="file-prep",
        name="Preparation fichier",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price=prep_price,
        currency="EUR",
        display_order=2,
    )


def _make_priced_order(*, billing_mode, shipping_method_code, meterage="1.0000"):
    ShippingMethodService().ensure_default_methods()
    user = get_user_model().objects.create_user(email="vat-ship@example.com", password="pass")
    customer = Customer.objects.create(
        name="VAT Ship Co",
        default_billing_mode=Customer.DefaultBillingMode.DEFERRED
        if billing_mode == Order.BillingMode.DEFERRED
        else Customer.DefaultBillingMode.IMMEDIATE,
        default_shipping_mode=Customer.DefaultShippingMode.PICKUP,
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="20.00")
    method = ShippingMethodService().require_active_by_code(shipping_method_code)
    snap = ShippingMethodService().snapshot_dict(method)
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=billing_mode,
        pricing_status=Order.PricingStatus.PENDING,
        currency="EUR",
        shipping_method_code=str(snap["shipping_method_code"]),
        shipping_method_name=str(snap["shipping_method_name"]),
        shipping_amount=snap["shipping_amount"],
    )
    upload = OrderUpload(
        order=order,
        uploaded_by=user,
        original_filename="f.png",
        mime_type="image/png",
        size_bytes=8,
        quantity=1,
        meterage_override_sqm=Decimal(meterage),
    )
    upload.file.save("f.png", ContentFile(b"fakebytes"), save=True)
    OrderUploadInspection.objects.create(
        order_upload=upload,
        status=OrderUploadInspection.Status.OK,
        image_width=1000,
        image_height=1000,
    )
    return order, user


@pytest.mark.django_db
def test_shipping_method_seed_and_pickup_is_free():
    service = ShippingMethodService()
    service.ensure_default_methods()
    methods = {m.code: m for m in service.list_active_methods()}
    assert set(methods) >= {"pickup", "standard", "express"}
    assert methods["pickup"].resolved_price == Decimal("0.00")
    assert methods["standard"].resolved_price == Decimal("8.00")
    assert methods["express"].resolved_price == Decimal("18.00")


@pytest.mark.django_db
@override_settings(DTF_LAIZE_CM=55)
def test_deferred_carrier_includes_shipping_without_vat():
    _seed_catalog()
    order, user = _make_priced_order(
        billing_mode=Order.BillingMode.DEFERRED,
        shipping_method_code="standard",
        meterage="2.0000",
    )
    OrderPricingService().compute_and_persist_order_pricing(
        order=order,
        actor=user,
        source="test",
    )
    order.refresh_from_db()
    # 2 m² × 20 € + 5 € prep = 45 HT + 8 port ; pas de TVA encours
    assert order.subtotal_amount == Decimal("45.00")
    assert order.shipping_amount == Decimal("8.00")
    assert order.tax_amount == Decimal("0.00")
    assert order.total_amount == Decimal("53.00")
    assert order.shipping_method_name == "Livraison standard"


@pytest.mark.django_db
@override_settings(DTF_LAIZE_CM=55)
def test_immediate_express_applies_vat_on_subtotal_and_shipping():
    _seed_catalog()
    order, user = _make_priced_order(
        billing_mode=Order.BillingMode.IMMEDIATE,
        shipping_method_code="express",
        meterage="1.0000",
    )
    OrderPricingService().compute_and_persist_order_pricing(
        order=order,
        actor=user,
        source="test",
    )
    order.refresh_from_db()
    # 1×20 + 5 = 25 HT + 18 port = 43 ; TVA 20 % = 8.60 ; total 51.60
    assert order.subtotal_amount == Decimal("25.00")
    assert order.shipping_amount == Decimal("18.00")
    assert order.tax_rate == Decimal("0.2000")
    assert order.tax_amount == Decimal("8.60")
    assert order.total_amount == Decimal("51.60")


@pytest.mark.django_db
@override_settings(DTF_LAIZE_CM=55)
def test_legacy_order_without_shipping_code_keeps_zero_shipping():
    """Anti-régression : commandes sans option figée restent à 0 € de port."""
    _seed_catalog()
    user = get_user_model().objects.create_user(email="legacy@example.com", password="pass")
    customer = Customer.objects.create(name="Legacy")
    CustomerMembership.objects.create(customer=customer, user=user)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="10.00")
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PENDING,
        currency="EUR",
    )
    upload = OrderUpload(
        order=order,
        uploaded_by=user,
        original_filename="f.png",
        mime_type="image/png",
        size_bytes=8,
        quantity=1,
        meterage_override_sqm=Decimal("1.0000"),
    )
    upload.file.save("f.png", ContentFile(b"fakebytes"), save=True)
    OrderUploadInspection.objects.create(
        order_upload=upload,
        status=OrderUploadInspection.Status.OK,
        image_width=1000,
        image_height=1000,
    )
    OrderPricingService().compute_and_persist_order_pricing(
        order=order,
        actor=user,
        source="test",
    )
    order.refresh_from_db()
    assert order.subtotal_amount == Decimal("15.00")  # 10 + 5
    assert order.shipping_amount == Decimal("0.00")
    assert order.tax_amount == Decimal("0.00")
    assert order.total_amount == Decimal("15.00")


@pytest.mark.django_db
def test_quote_aligns_with_compose_totals_for_standard_cash():
    _seed_catalog()
    ShippingMethodService().ensure_default_methods()
    customer = Customer.objects.create(
        name="Quote Align",
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    quote = OrderPricingService().estimate_gang_sheet_quote(
        customer=customer,
        surface_sqm="1.0000",
        quantity=1,
        shipping_method_code="standard",
        billing_mode="immediate",
    )
    # 25 + 5 + 8 = 38 HT ; TVA 7.60 ; total 45.60
    assert quote["subtotal_eur"] == Decimal("30.00")
    assert quote["shipping_amount_eur"] == Decimal("8.00")
    assert quote["tax_amount_eur"] == Decimal("7.60")
    assert quote["total_eur"] == Decimal("45.60")


@pytest.mark.django_db
def test_pickup_account_ignores_requested_carrier_shipping():
    ShippingMethodService().ensure_default_methods()
    customer = Customer.objects.create(
        name="Pickup Only",
        default_shipping_mode=Customer.DefaultShippingMode.PICKUP,
    )
    service = ShippingMethodService()
    assert service.customer_locks_shipping_to_pickup(customer) is True
    method = service.resolve_method_for_customer(
        customer=customer,
        shipping_method_code="express",
    )
    assert method.code == "pickup"
    assert method.resolved_price == Decimal("0.00")


@pytest.mark.django_db
def test_prefers_seed_file_prep_over_cheaper_test_duplicate():
    CatalogService.objects.create(
        code="file-prep",
        name="Preparation fichier",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price="5.00",
        currency="EUR",
        display_order=1,
        is_active=True,
    )
    CatalogService.objects.create(
        code="seed-file-prep",
        name="Seed Preparation fichier",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price="10.00",
        currency="EUR",
        display_order=2,
        is_active=True,
    )
    CatalogService.objects.create(
        code="dtf-meter",
        name="DTF",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="9.00",
        currency="EUR",
        display_order=1,
        is_active=True,
    )
    customer = Customer.objects.create(name="Client T")
    fee = OrderPricingService().resolve_file_preparation_fee_per_file(customer=customer)
    assert fee == Decimal("10.00")
    Customer.objects.filter(pk=customer.pk).update(
        negotiated_file_preparation_fee_eur=Decimal("3.50")
    )
    customer.refresh_from_db()
    assert OrderPricingService().resolve_file_preparation_fee_per_file(
        customer=customer
    ) == Decimal("3.50")
