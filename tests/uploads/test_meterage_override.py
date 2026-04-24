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
    assert out.pricing_status == Order.PricingStatus.PENDING
    assert out.subtotal_amount == Decimal("0.00")
    assert out.total_amount == Decimal("0.00")
    assert str(out.meterage_override_linear_m) == "2.5000"
    upload.refresh_from_db()
    assert upload.meterage_sqm is None
    assert upload.line_total_eur is None


@pytest.mark.django_db
def test_set_staff_meterage_override_rejects_immediate_even_when_submitted():
    user = get_user_model().objects.create_user(email="s2@example.com", password="pass")
    customer = Customer.objects.create(name="C2")
    CustomerMembership.objects.create(customer=customer, user=user)
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.IMMEDIATE,
        pricing_status=Order.PricingStatus.PENDING,
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
    with pytest.raises(ValidationError, match="différée"):
        svc.set_staff_meterage_override(
            order=order,
            upload_public_id=upload.public_id,
            actor=user,
            raw_value="1.5",
        )
