from decimal import Decimal

import pytest
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.uploads.models import OrderUpload
from apps.uploads.services.uploads import OrderUploadService
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile


@pytest.mark.django_db
def test_set_staff_meterage_override_allows_deferred_draft():
    user = get_user_model().objects.create_user(email="s@example.com", password="pass")
    customer = Customer.objects.create(name="C")
    CustomerMembership.objects.create(customer=customer, user=user)
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.DRAFT,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PENDING,
        currency="EUR",
        subtotal_amount="0",
        total_amount="0",
    )
    upload = OrderUpload(
        order=order,
        uploaded_by=user,
        original_filename="a.png",
        mime_type="image/png",
        size_bytes=4,
    )
    upload.file.save("a.png", ContentFile(b"x"), save=True)
    svc = OrderUploadService()
    out = svc.set_staff_meterage_override(
        order=order,
        upload_public_id=upload.public_id,
        actor=user,
        raw_value="1.5",
    )
    assert out.meterage_override_linear_m is not None
    assert str(out.meterage_override_linear_m) == "1.5000"
    assert out.meterage_override_sqm is None


@pytest.mark.django_db
def test_set_staff_order_meterage_linear_override_allows_deferred_draft():
    user = get_user_model().objects.create_user(email="ord@example.com", password="pass")
    customer = Customer.objects.create(name="Co")
    CustomerMembership.objects.create(customer=customer, user=user)
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.DRAFT,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PENDING,
        currency="EUR",
        subtotal_amount="0",
        total_amount="0",
    )
    svc = OrderUploadService()
    out = svc.set_staff_order_meterage_linear_override(
        order=order,
        actor=user,
        raw_value="3,2",
    )
    assert out.meterage_override_linear_m is not None
    assert str(out.meterage_override_linear_m) == "3.2000"


@pytest.mark.django_db
def test_set_staff_order_meterage_linear_override_resets_priced_order():
    from apps.catalog.models import CatalogService

    CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="10.00",
        currency="EUR",
        display_order=1,
    )
    CatalogService.objects.create(
        code="file-prep",
        name="Preparation fichier",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price="10.00",
        currency="EUR",
        display_order=2,
    )
    user = get_user_model().objects.create_user(email="priced@example.com", password="pass")
    customer = Customer.objects.create(name="Cp")
    CustomerMembership.objects.create(customer=customer, user=user)
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PRICED,
        currency="EUR",
        subtotal_amount="10.00",
        total_amount="10.00",
    )
    upload = OrderUpload(
        order=order,
        uploaded_by=user,
        original_filename="c.png",
        mime_type="image/png",
        size_bytes=4,
        meterage_sqm=Decimal("1.0000"),
        unit_price_eur=Decimal("10.00"),
        line_total_eur=Decimal("10.00"),
    )
    upload.file.save("c.png", ContentFile(b"x"), save=True)
    svc = OrderUploadService()
    out = svc.set_staff_order_meterage_linear_override(
        order=order,
        actor=user,
        raw_value="2.5",
    )
    out.refresh_from_db()
    assert out.pricing_status == Order.PricingStatus.PRICED
    assert out.meterage_override_linear_m is not None
    assert str(out.meterage_override_linear_m) == "2.5000"
    assert out.total_amount > Decimal("0.00")
    upload.refresh_from_db()
    assert upload.meterage_sqm is not None
    assert upload.line_total_eur is not None


@pytest.mark.django_db
def test_set_staff_order_meterage_auto_prices_submitted_order():
    from apps.catalog.models import CatalogService

    CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="20.00",
        currency="EUR",
        display_order=1,
    )
    CatalogService.objects.create(
        code="file-prep",
        name="Preparation fichier",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price="5.00",
        currency="EUR",
        display_order=2,
    )
    user = get_user_model().objects.create_user(email="autoprice@example.com", password="pass")
    customer = Customer.objects.create(name="Auto")
    CustomerMembership.objects.create(customer=customer, user=user)
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PENDING,
        currency="EUR",
        subtotal_amount="0",
        total_amount="0",
    )
    upload = OrderUpload(
        order=order,
        uploaded_by=user,
        original_filename="a.png",
        mime_type="image/png",
        size_bytes=4,
    )
    upload.file.save("a.png", ContentFile(b"x"), save=True)
    out = OrderUploadService().set_staff_order_meterage_linear_override(
        order=order,
        actor=user,
        raw_value="2",
    )
    out.refresh_from_db()
    assert out.pricing_status == Order.PricingStatus.PRICED
    assert out.total_amount > Decimal("0.00")


@pytest.mark.django_db
def test_set_staff_meterage_override_rejects_catalog_immediate():
    user = get_user_model().objects.create_user(email="s2@example.com", password="pass")
    customer = Customer.objects.create(name="C2")
    CustomerMembership.objects.create(customer=customer, user=user)
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        source="client_api",
        billing_mode=Order.BillingMode.IMMEDIATE,
        pricing_status=Order.PricingStatus.PRICED,
        currency="EUR",
        subtotal_amount="0",
        total_amount="0",
    )
    upload = OrderUpload(
        order=order,
        uploaded_by=user,
        original_filename="b.png",
        mime_type="image/png",
        size_bytes=4,
    )
    upload.file.save("b.png", ContentFile(b"x"), save=True)
    svc = OrderUploadService()
    with pytest.raises(ValidationError, match="atelier"):
        svc.set_staff_meterage_override(
            order=order,
            upload_public_id=upload.public_id,
            actor=user,
            raw_value="1.5",
        )
