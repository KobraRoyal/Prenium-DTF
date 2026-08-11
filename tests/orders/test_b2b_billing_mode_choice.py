import pytest
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.orders.services.orders import OrderService
from apps.uploads.models import OrderUpload
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile


def _attach_dummy_upload(order: Order) -> None:
    upload = OrderUpload(
        order=order,
        original_filename="file.pdf",
        mime_type="application/pdf",
        size_bytes=12,
        sort_order=1,
        quantity=1,
    )
    upload.file.save("file.pdf", ContentFile(b"%PDF-1.4 test"), save=False)
    upload.save()


@pytest.mark.django_db
def test_b2b_order_can_be_created_and_submitted_as_card_payment():
    user = get_user_model().objects.create_user(email="cb@example.com", password="pass")
    customer = Customer.objects.create(name="CB Co")
    CustomerMembership.objects.create(customer=customer, user=user)
    service = OrderService()

    order = service.create_b2b_deferred_order(
        customer=customer,
        actor=user,
        customer_note="Commande CB",
        source="client_portal.b2b_checkout",
        billing_mode="immediate",
    )
    assert order.billing_mode == Order.BillingMode.IMMEDIATE
    assert order.pricing_status == Order.PricingStatus.PENDING
    assert order.uses_atelier_pricing() is True

    _attach_dummy_upload(order)

    submitted = service.submit_b2b_deferred_order(
        customer=customer,
        actor=user,
        order_public_id=order.public_id,
        source="client_portal.b2b_checkout",
        billing_mode="immediate",
    )
    assert submitted.status == Order.Status.SUBMITTED
    assert submitted.billing_mode == Order.BillingMode.IMMEDIATE


@pytest.mark.django_db
def test_b2b_submit_can_switch_from_default_deferred_to_card():
    user = get_user_model().objects.create_user(email="switch@example.com", password="pass")
    customer = Customer.objects.create(name="Switch Co")
    CustomerMembership.objects.create(customer=customer, user=user)
    service = OrderService()
    order = service.create_b2b_deferred_order(
        customer=customer,
        actor=user,
        source="client_checkout",
    )
    assert order.billing_mode == Order.BillingMode.DEFERRED
    _attach_dummy_upload(order)
    submitted = service.submit_b2b_deferred_order(
        customer=customer,
        actor=user,
        order_public_id=order.public_id,
        source="client_checkout",
        billing_mode="cb",
    )
    assert submitted.billing_mode == Order.BillingMode.IMMEDIATE


@pytest.mark.django_db
def test_b2b_billing_mode_rejects_unknown_value():
    with pytest.raises(ValidationError):
        OrderService._normalize_b2b_billing_mode("bitcoin")


@pytest.mark.django_db
def test_immediate_account_rejects_deferred_billing_mode():
    user = get_user_model().objects.create_user(email="cash@example.com", password="pass")
    customer = Customer.objects.create(
        name="Cash Only Co",
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    service = OrderService()

    with pytest.raises(ValidationError, match="comptant"):
        service.create_b2b_deferred_order(
            customer=customer,
            actor=user,
            source="client_portal.b2b_checkout",
            billing_mode="deferred",
        )

    order = service.create_b2b_deferred_order(
        customer=customer,
        actor=user,
        source="client_portal.b2b_checkout",
    )
    assert order.billing_mode == Order.BillingMode.IMMEDIATE
    _attach_dummy_upload(order)

    with pytest.raises(ValidationError, match="comptant"):
        service.submit_b2b_deferred_order(
            customer=customer,
            actor=user,
            order_public_id=order.public_id,
            source="client_portal.b2b_checkout",
            billing_mode="deferred",
        )
