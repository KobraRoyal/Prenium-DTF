from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.billing.models import BillingStatement, Payment
from apps.catalog.models import CatalogService
from apps.customers.models import (
    Customer,
    CustomerVolumeDiscountTier,
    DefaultCustomerVolumeDiscountTier,
)
from apps.customers.services.volume_discounts import CustomerVolumeDiscountTierService
from apps.notifications.models import VolumeDiscountTierNotification
from apps.orders.models import Order
from apps.orders.services.pricing import OrderPricingService
from apps.uploads.models import OrderUpload
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.utils import timezone


def _seed_catalog():
    CatalogService.objects.create(
        code="dtf-volume-test",
        name="DTF volume test",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price=Decimal("10.00"),
        currency="EUR",
        display_order=1,
    )
    CatalogService.objects.create(
        code="prep-volume-test",
        name="Préparation volume test",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price=Decimal("10.00"),
        currency="EUR",
        display_order=2,
    )


def _create_order(*, customer, user, linear_m: str, billing_mode=Order.BillingMode.DEFERRED):
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=billing_mode,
        pricing_status=Order.PricingStatus.PENDING,
        source="client_portal",
        currency="EUR",
        meterage_override_linear_m=Decimal(linear_m),
    )
    OrderUpload.objects.create(
        order=order,
        uploaded_by=user,
        file=f"orders/{order.public_id}/file.png",
        original_filename="file.png",
        mime_type="image/png",
        size_bytes=8,
        quantity=1,
    )
    return order


def _price(order, user):
    return OrderPricingService().compute_and_persist_order_pricing(
        order=order,
        actor=user,
        source="test",
    )


@pytest.mark.django_db
@override_settings(DTF_LAIZE_CM=100)
def test_best_tier_retroactively_discounts_all_unbilled_dtf_in_month():
    user = get_user_model().objects.create_user(email="volume@example.com", password="pass")
    customer = Customer.objects.create(name="Volume", default_billing_mode="deferred")
    _seed_catalog()
    CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m=Decimal("5.0000"),
        discount_percent=Decimal("10.00"),
    )
    CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m=Decimal("10.0000"),
        discount_percent=Decimal("20.00"),
    )

    first = _create_order(customer=customer, user=user, linear_m="4.0000")
    _price(first, user)
    first.refresh_from_db()
    assert first.total_amount == Decimal("50.00")
    assert first.volume_discount_percent == Decimal("0.00")

    second = _create_order(customer=customer, user=user, linear_m="2.0000")
    _price(second, user)
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.monthly_volume_linear_m == Decimal("6.0000")
    assert first.volume_discount_percent == Decimal("10.00")
    assert first.volume_discount_amount == Decimal("4.00")
    assert first.total_amount == Decimal("46.00")
    assert second.total_amount == Decimal("28.00")

    third = _create_order(customer=customer, user=user, linear_m="5.0000")
    _price(third, user)
    first.refresh_from_db()
    second.refresh_from_db()
    third.refresh_from_db()
    assert first.monthly_volume_linear_m == Decimal("11.0000")
    assert first.volume_discount_threshold_linear_m == Decimal("10.0000")
    assert first.volume_discount_percent == Decimal("20.00")
    assert first.volume_discount_amount == Decimal("8.00")
    assert first.total_amount == Decimal("42.00")
    assert second.total_amount == Decimal("26.00")
    assert third.total_amount == Decimal("50.00")
    prep_line = first.items.get(service_type=CatalogService.ServiceType.FILE_PREPARATION)
    assert prep_line.line_total == Decimal("10.00")
    summary = CustomerVolumeDiscountTierService().get_current_month_summary(customer=customer)
    assert summary["eligible_order_count"] == 3
    assert summary["monthly_volume_linear_m"] == Decimal("11.0000")
    assert (
        summary["current_tier"].pk
        == CustomerVolumeDiscountTier.objects.get(minimum_monthly_linear_m=Decimal("10.0000")).pk
    )
    assert summary["next_tier"] is None
    assert summary["discount_amount"] == Decimal("22.00")
    assert AuditLogEntry.objects.filter(
        action="order.monthly_volume_discount_repriced",
        target_public_id=first.public_id,
    ).exists()
    notifications = list(
        VolumeDiscountTierNotification.objects.filter(customer=customer).order_by(
            "threshold_linear_m"
        )
    )
    assert [row.threshold_linear_m for row in notifications] == [
        Decimal("5.0000"),
        Decimal("10.0000"),
    ]

    OrderPricingService().reprice_deferred_month(
        customer=customer,
        month=timezone.localdate(),
        actor=user,
        source="test.idempotence",
    )
    assert VolumeDiscountTierNotification.objects.filter(customer=customer).count() == 2


@pytest.mark.django_db
@override_settings(DTF_LAIZE_CM=100)
def test_billed_orders_are_frozen_and_excluded_from_new_monthly_volume():
    user = get_user_model().objects.create_user(email="frozen@example.com", password="pass")
    customer = Customer.objects.create(name="Frozen", default_billing_mode="deferred")
    _seed_catalog()
    CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m=Decimal("5.0000"),
        discount_percent=Decimal("10.00"),
    )
    first = _create_order(customer=customer, user=user, linear_m="6.0000")
    _price(first, user)
    first.refresh_from_db()
    assert first.total_amount == Decimal("64.00")
    statement = BillingStatement.objects.create(
        customer=customer,
        period_start=timezone.localdate().replace(day=1),
        period_end=timezone.localdate(),
        total_amount=first.total_amount,
    )
    first.billing_statement = statement
    first.save(update_fields=["billing_statement", "updated_at"])

    second = _create_order(customer=customer, user=user, linear_m="1.0000")
    _price(second, user)
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.total_amount == Decimal("64.00")
    assert first.volume_discount_percent == Decimal("10.00")
    assert second.monthly_volume_linear_m == Decimal("1.0000")
    assert second.volume_discount_percent == Decimal("0.00")
    assert second.total_amount == Decimal("20.00")


@pytest.mark.django_db
@override_settings(DTF_LAIZE_CM=100)
def test_month_and_customer_scopes_are_isolated_and_immediate_orders_do_not_count():
    user = get_user_model().objects.create_user(email="scope@example.com", password="pass")
    customer = Customer.objects.create(name="Scoped", default_billing_mode="deferred")
    other_customer = Customer.objects.create(name="Other", default_billing_mode="deferred")
    _seed_catalog()
    CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m=Decimal("5.0000"),
        discount_percent=Decimal("10.00"),
    )
    previous = _create_order(customer=customer, user=user, linear_m="5.0000")
    now = timezone.localtime()
    previous_month = (now.replace(day=1) - timedelta(days=1)).replace(day=15)
    Order.objects.filter(pk=previous.pk).update(
        created_at=timezone.make_aware(
            datetime.combine(previous_month.date(), datetime.min.time()),
            timezone.get_current_timezone(),
        )
    )
    previous.refresh_from_db()
    _price(previous, user)

    immediate = _create_order(
        customer=customer,
        user=user,
        linear_m="10.0000",
        billing_mode=Order.BillingMode.IMMEDIATE,
    )
    _price(immediate, user)
    other = _create_order(customer=other_customer, user=user, linear_m="10.0000")
    _price(other, user)
    current = _create_order(customer=customer, user=user, linear_m="1.0000")
    _price(current, user)

    current.refresh_from_db()
    previous.refresh_from_db()
    immediate.refresh_from_db()
    assert current.monthly_volume_linear_m == Decimal("1.0000")
    assert current.volume_discount_percent == Decimal("0.00")
    assert previous.monthly_volume_linear_m == Decimal("5.0000")
    assert previous.volume_discount_percent == Decimal("10.00")
    assert immediate.monthly_volume_linear_m is None
    assert immediate.volume_discount_percent == Decimal("0.00")


@pytest.mark.django_db
@override_settings(DTF_LAIZE_CM=100)
def test_updating_tier_reprices_current_unbilled_orders_and_is_audited():
    user = get_user_model().objects.create_user(email="update@example.com", password="pass")
    customer = Customer.objects.create(name="Updated", default_billing_mode="deferred")
    _seed_catalog()
    tier = CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m=Decimal("5.0000"),
        discount_percent=Decimal("10.00"),
    )
    order = _create_order(customer=customer, user=user, linear_m="6.0000")
    _price(order, user)
    order.refresh_from_db()
    assert order.total_amount == Decimal("64.00")

    _tier, summary = CustomerVolumeDiscountTierService().update_tier(
        customer=customer,
        tier_public_id=tier.public_id,
        cleaned_data={
            "minimum_monthly_linear_m": Decimal("5.0000"),
            "discount_percent": Decimal("20.00"),
            "is_active": True,
        },
        actor=user,
        source="test",
    )
    order.refresh_from_db()
    assert summary["repriced_count"] == 1
    assert order.volume_discount_percent == Decimal("20.00")
    assert order.volume_discount_amount == Decimal("12.00")
    assert order.total_amount == Decimal("58.00")

    CustomerVolumeDiscountTierService().update_tier(
        customer=customer,
        tier_public_id=tier.public_id,
        cleaned_data={
            "minimum_monthly_linear_m": Decimal("5.0000"),
            "discount_percent": Decimal("20.00"),
            "is_active": False,
        },
        actor=user,
        source="test",
    )
    order.refresh_from_db()
    assert order.volume_discount_percent == Decimal("0.00")
    assert order.volume_discount_amount == Decimal("0.00")
    assert order.total_amount == Decimal("70.00")
    assert AuditLogEntry.objects.filter(
        action="customer.volume_discount_tier_updated",
        target_public_id=customer.public_id,
    ).exists()


def _capture_payment(order, user):
    return Payment.objects.create(
        order=order,
        created_by=user,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.CAPTURED,
        amount=order.total_amount,
        currency=order.currency,
        source="test",
    )


@pytest.mark.django_db
@override_settings(DTF_LAIZE_CM=100)
def test_immediate_orders_are_prospective_and_paid_only():
    user = get_user_model().objects.create_user(email="cash-volume@example.com", password="pass")
    customer = Customer.objects.create(
        name="Cash Volume",
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    _seed_catalog()
    CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m=Decimal("5.0000"),
        discount_percent=Decimal("10.00"),
    )
    CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m=Decimal("10.0000"),
        discount_percent=Decimal("20.00"),
    )

    first = _create_order(
        customer=customer,
        user=user,
        linear_m="4.0000",
        billing_mode=Order.BillingMode.IMMEDIATE,
    )
    _price(first, user)
    first.refresh_from_db()
    assert first.volume_discount_percent == Decimal("0.00")
    assert first.total_amount == Decimal("60.00")  # 40 HT + 10 prep + 20% TVA
    _capture_payment(first, user)

    unpaid = _create_order(
        customer=customer,
        user=user,
        linear_m="6.0000",
        billing_mode=Order.BillingMode.IMMEDIATE,
    )
    _price(unpaid, user)
    unpaid.refresh_from_db()
    assert unpaid.volume_discount_percent == Decimal("20.00")
    first.refresh_from_db()
    assert first.volume_discount_percent == Decimal("0.00")
    assert first.total_amount == Decimal("60.00")

    second = _create_order(
        customer=customer,
        user=user,
        linear_m="2.0000",
        billing_mode=Order.BillingMode.IMMEDIATE,
    )
    quote = OrderPricingService().estimate_gang_sheet_quote(
        customer=customer,
        surface_sqm="2.0000",
        quantity=1,
        shipping_method_code="pickup",
        billing_mode=Order.BillingMode.IMMEDIATE,
    )
    assert quote["volume_discount_percent"] == Decimal("10.00")
    _price(second, user)
    first.refresh_from_db()
    unpaid.refresh_from_db()
    second.refresh_from_db()
    assert first.volume_discount_percent == Decimal("0.00")
    assert unpaid.volume_discount_percent == Decimal("20.00")
    assert second.volume_discount_percent == Decimal("10.00")
    assert second.volume_discount_amount == Decimal("2.00")
    _capture_payment(second, user)

    third = _create_order(
        customer=customer,
        user=user,
        linear_m="5.0000",
        billing_mode=Order.BillingMode.IMMEDIATE,
    )
    _price(third, user)
    first.refresh_from_db()
    second.refresh_from_db()
    third.refresh_from_db()
    assert first.volume_discount_percent == Decimal("0.00")
    assert second.volume_discount_percent == Decimal("10.00")
    assert third.volume_discount_percent == Decimal("20.00")
    summary = CustomerVolumeDiscountTierService().get_current_month_summary(customer=customer)
    assert summary["policy"] == "prospective"
    assert summary["eligible_order_count"] == 2
    assert summary["monthly_volume_linear_m"] == Decimal("6.0000")
    assert summary["current_tier"].discount_percent == Decimal("10.00")


@pytest.mark.django_db
@override_settings(DTF_LAIZE_CM=100)
def test_immediate_uses_default_ladder_until_customer_personalizes():
    user = get_user_model().objects.create_user(email="cash-default@example.com", password="pass")
    customer = Customer.objects.create(
        name="Cash Default",
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    _seed_catalog()
    DefaultCustomerVolumeDiscountTier.objects.create(
        minimum_monthly_linear_m=Decimal("5.0000"),
        discount_percent=Decimal("10.00"),
    )
    quote = OrderPricingService().estimate_gang_sheet_quote(
        customer=customer,
        surface_sqm="6.0000",
        quantity=1,
        shipping_method_code="pickup",
        billing_mode=Order.BillingMode.IMMEDIATE,
    )
    assert quote["volume_discount_percent"] == Decimal("10.00")
    order = _create_order(
        customer=customer,
        user=user,
        linear_m="6.0000",
        billing_mode=Order.BillingMode.IMMEDIATE,
    )
    _price(order, user)
    order.refresh_from_db()
    assert order.volume_discount_percent == Decimal("10.00")

    CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m=Decimal("5.0000"),
        discount_percent=Decimal("15.00"),
    )
    DefaultCustomerVolumeDiscountTier.objects.update(discount_percent=Decimal("40.00"))
    next_order = _create_order(
        customer=customer,
        user=user,
        linear_m="6.0000",
        billing_mode=Order.BillingMode.IMMEDIATE,
    )
    _price(next_order, user)
    next_order.refresh_from_db()
    assert next_order.volume_discount_percent == Decimal("15.00")


@pytest.mark.django_db
@override_settings(DTF_LAIZE_CM=100)
def test_deferred_uses_default_ladder_when_customer_has_no_personalized_tiers():
    user = get_user_model().objects.create_user(
        email="deferred-default@example.com",
        password="pass",
    )
    customer = Customer.objects.create(name="Deferred Empty", default_billing_mode="deferred")
    _seed_catalog()
    DefaultCustomerVolumeDiscountTier.objects.create(
        minimum_monthly_linear_m=Decimal("5.0000"),
        discount_percent=Decimal("10.00"),
    )
    order = _create_order(customer=customer, user=user, linear_m="6.0000")
    _price(order, user)
    order.refresh_from_db()
    assert order.volume_discount_percent == Decimal("10.00")
    assert order.volume_discount_amount == Decimal("6.00")
    assert order.total_amount == Decimal("64.00")
    summary = CustomerVolumeDiscountTierService().get_current_month_summary(customer=customer)
    assert summary["uses_default_ladder"] is True
    assert summary["current_tier"].discount_percent == Decimal("10.00")


@pytest.mark.django_db
@override_settings(DTF_LAIZE_CM=100)
def test_deferred_personalized_ladder_overrides_default_ladder():
    user = get_user_model().objects.create_user(
        email="deferred-personalized@example.com",
        password="pass",
    )
    customer = Customer.objects.create(
        name="Deferred Personalized",
        default_billing_mode="deferred",
    )
    _seed_catalog()
    DefaultCustomerVolumeDiscountTier.objects.create(
        minimum_monthly_linear_m=Decimal("5.0000"),
        discount_percent=Decimal("40.00"),
    )
    CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m=Decimal("5.0000"),
        discount_percent=Decimal("10.00"),
    )
    order = _create_order(customer=customer, user=user, linear_m="6.0000")
    _price(order, user)
    order.refresh_from_db()
    assert order.volume_discount_percent == Decimal("10.00")
    assert order.total_amount == Decimal("64.00")


@pytest.mark.django_db
@override_settings(DTF_LAIZE_CM=100)
def test_captured_immediate_order_cannot_be_repriced():
    user = get_user_model().objects.create_user(email="frozen-cash@example.com", password="pass")
    customer = Customer.objects.create(
        name="Frozen Cash",
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    _seed_catalog()
    order = _create_order(
        customer=customer,
        user=user,
        linear_m="2.0000",
        billing_mode=Order.BillingMode.IMMEDIATE,
    )
    _price(order, user)
    _capture_payment(order, user)
    with pytest.raises(ValidationError, match="figé après paiement"):
        _price(order, user)
