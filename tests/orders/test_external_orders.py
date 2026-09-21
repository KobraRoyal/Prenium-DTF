from decimal import Decimal

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.orders.services.external_orders import ExternalOrderService
from apps.uploads.models import OrderUpload, OrderUploadDriveSync, OrderUploadInspection
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError


def client_scope(suffix="a"):
    user = get_user_model().objects.create_user(
        email=f"client-{suffix}@example.com", password="pass"
    )
    customer = Customer.objects.create(name=f"Client {suffix}")
    CustomerMembership.objects.create(customer=customer, user=user)
    return user, customer


def staff_user(*, full_permissions=True):
    user = get_user_model().objects.create_user(
        email="atelier-external@example.com", password="pass", is_staff=True
    )
    perms = [Permission.objects.get(codename="access_staff_portal")]
    if full_permissions:
        perms += [
            Permission.objects.get(codename=name)
            for name in ("add_order", "change_order", "view_order")
        ]
    user.user_permissions.add(*perms)
    return user


@pytest.mark.django_db
def test_client_creates_submitted_external_order_without_file_or_jobs():
    actor, customer = client_scope()
    order = ExternalOrderService().create_client_order(
        customer=customer,
        actor=actor,
        name="Grand visuel",
        external_url="https://files.example.com/download/abc?token=private",
        customer_note="Grand fichier",
    )
    upload = OrderUpload.objects.get(order=order)
    assert order.status == Order.Status.SUBMITTED
    assert order.pricing_status == Order.PricingStatus.PENDING
    assert order.created_by == actor
    assert order.production_job is not None
    assert upload.is_external
    assert upload.file.name == ""
    assert upload.asset_version_id is None
    assert upload.size_bytes == 0
    assert not OrderUploadInspection.objects.filter(order_upload=upload).exists()
    assert not OrderUploadDriveSync.objects.filter(order_upload=upload).exists()
    audit = AuditLogEntry.objects.get(
        action="order.external_created", target_public_id=order.public_id
    )
    assert "token" not in str(audit.metadata)


@pytest.mark.django_db
def test_client_cannot_create_for_other_customer_or_cash_account():
    actor, customer = client_scope("a")
    _, other = client_scope("b")
    service = ExternalOrderService()
    with pytest.raises(ValidationError):
        service.create_client_order(
            customer=other, actor=actor, name="Visuel", external_url="https://files.example.com/a"
        )
    customer.default_billing_mode = Order.BillingMode.IMMEDIATE
    customer.save(update_fields=["default_billing_mode"])
    with pytest.raises(ValidationError):
        service.create_client_order(
            customer=customer,
            actor=actor,
            name="Visuel",
            external_url="https://files.example.com/a",
        )
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_staff_requires_all_permissions_and_valid_meterage_before_mutation():
    _, customer = client_scope()
    actor = staff_user(full_permissions=False)
    service = ExternalOrderService()
    with pytest.raises(ValidationError):
        service.create_staff_order(
            customer=customer,
            actor=actor,
            name="Visuel",
            external_url="https://files.example.com/a",
            meterage_linear_m="2.5",
        )
    actor.user_permissions.add(
        *[
            Permission.objects.get(codename=name)
            for name in ("add_order", "change_order", "view_order")
        ]
    )
    with pytest.raises(ValidationError):
        service.create_staff_order(
            customer=customer,
            actor=actor,
            name="Visuel",
            external_url="https://files.example.com/a",
            meterage_linear_m="NaN",
        )
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_staff_creation_prices_meterage_and_preserves_staff_actor():
    _, customer = client_scope()
    actor = staff_user()
    order = ExternalOrderService().create_staff_order(
        customer=customer,
        actor=actor,
        name="Grand visuel",
        external_url="https://files.example.com/a",
        meterage_linear_m="2.5000",
        shipping_method_code="express",
    )
    assert order.created_by == actor
    assert order.meterage_override_linear_m == Decimal("2.5000")
    assert order.pricing_status == Order.PricingStatus.PRICED
    assert order.items.count() == 2
    assert order.uploads.get().meterage_sqm > 0
    assert order.shipping_method_code == "express"
    from apps.orders.references import order_business_number

    assert order_business_number(order).startswith("CMD-")
    assert order.source_b2b_order_project.project_number == order_business_number(order)


@pytest.mark.django_db
def test_staff_creation_allows_deferred_meterage_with_cmd_number():
    _, customer = client_scope()
    actor = staff_user()
    order = ExternalOrderService().create_staff_order(
        customer=customer,
        actor=actor,
        name="Sans métrage",
        external_url="https://files.example.com/a",
        meterage_linear_m=None,
        shipping_method_code="standard",
    )
    assert order.meterage_override_linear_m is None
    assert order.pricing_status == Order.PricingStatus.PENDING
    assert order.shipping_method_code == "standard"
    from apps.orders.references import order_business_number

    assert order_business_number(order).startswith("CMD-")


@pytest.mark.django_db
def test_staff_creation_respects_immediate_billing_mode():
    _, customer = client_scope()
    customer.default_billing_mode = Order.BillingMode.IMMEDIATE
    customer.save(update_fields=["default_billing_mode"])
    actor = staff_user()
    order = ExternalOrderService().create_staff_order(
        customer=customer,
        actor=actor,
        name="Grand visuel",
        external_url="https://files.example.com/a",
        meterage_linear_m="2.0000",
    )
    assert order.billing_mode == Order.BillingMode.IMMEDIATE
    assert order.pricing_status == Order.PricingStatus.PRICED
    assert order.tax_amount > 0


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "ftp://files.example.com/a",
        "http://localhost/a",
        "http://127.0.0.1/a",
        "http://10.0.0.1/a",
        "http://[::1]/a",
        "https://user:password@files.example.com/a",
        "https://files.local/a",
        "https://example.com:bad/a",
        "https://intranet/a",
    ],
)
def test_external_url_rejects_non_public_or_unsafe_urls(url):
    with pytest.raises(ValidationError):
        ExternalOrderService.validate_external_url(url)


@pytest.mark.django_db
@pytest.mark.parametrize("count_only", [False, True])
def test_visual_count_changes_only_preparation_and_survives_monthly_repricing(count_only):
    from apps.orders.services.pricing import OrderPricingService
    from apps.uploads.services.uploads import OrderUploadService
    from django.utils import timezone

    _, customer = client_scope()
    actor = staff_user()
    order = ExternalOrderService().create_staff_order(
        customer=customer,
        actor=actor,
        name="Lot",
        external_url="https://example.com/lot",
        meterage_linear_m="2.5",
        external_visual_count=3,
    )
    prep = order.items.get(service_type="file_preparation")
    assert prep.quantity == 3
    assert prep.line_total == prep.unit_price * 3
    upload = order.uploads.get()
    area = upload.meterage_sqm
    assert upload.quantity == 1
    assert upload.external_visual_count == 3
    dtf = order.items.exclude(service_type="file_preparation").get()
    dtf_quantity, dtf_total = dtf.quantity, dtf.line_total
    old_subtotal = order.subtotal_amount
    unit_prep = prep.unit_price
    if count_only:
        order = OrderUploadService().set_staff_external_visual_count(
            order=order, actor=actor, value="5"
        )
    else:
        order = OrderUploadService().set_staff_order_meterage_linear_override(
            order=order, actor=actor, raw_value="2.5", external_visual_count="5"
        )
    assert order.subtotal_amount == old_subtotal + unit_prep * 2
    assert order.uploads.get().meterage_sqm == area
    assert order.meterage_override_linear_m == Decimal("2.5")
    dtf = order.items.exclude(service_type="file_preparation").get()
    assert (dtf.quantity, dtf.line_total) == (dtf_quantity, dtf_total)
    OrderPricingService().reprice_deferred_month(
        customer=customer,
        month=timezone.localdate(),
        actor=actor,
        source="test",
    )
    assert order.items.get(service_type="file_preparation").quantity == 5


@pytest.mark.django_db
@pytest.mark.parametrize("count", ["0", "-1", "1.5", "10001", "NaN", "", None, True])
def test_manual_visual_count_rejects_invalid_values_without_order(count):
    _, customer = client_scope()
    with pytest.raises(ValidationError):
        ExternalOrderService().create_staff_order(
            customer=customer,
            actor=staff_user(),
            name="Lot",
            external_url="https://example.com/lot",
            meterage_linear_m="2.5",
            external_visual_count=count,
        )
    assert not Order.objects.exists()


@pytest.mark.django_db
def test_failed_meterage_or_count_edit_preserves_previous_price():
    from apps.uploads.services.uploads import OrderUploadService

    _, customer = client_scope()
    actor = staff_user()
    order = ExternalOrderService().create_staff_order(
        customer=customer,
        actor=actor,
        name="Lot",
        external_url="https://example.com/lot",
        meterage_linear_m="2.5",
        external_visual_count=3,
    )
    old_total = order.total_amount
    for meterage, count in [("oops", "5"), ("2.5", "0")]:
        with pytest.raises(ValidationError):
            OrderUploadService().set_staff_order_meterage_linear_override(
                order=order,
                actor=actor,
                raw_value=meterage,
                external_visual_count=count,
            )
        order.refresh_from_db()
        assert order.total_amount == old_total
        assert order.pricing_status == Order.PricingStatus.PRICED
        assert order.uploads.get().external_visual_count == 3
        assert order.items.get(service_type="file_preparation").quantity == 3


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["pending", "approved", "captured", "cancelled", "failed"])
def test_visual_count_and_meterage_frozen_after_payment_attempt(status):
    from apps.billing.models import Payment
    from apps.uploads.services.uploads import OrderUploadService

    _, customer = client_scope()
    customer.default_billing_mode = Order.BillingMode.IMMEDIATE
    customer.save(update_fields=["default_billing_mode"])
    actor = staff_user()
    order = ExternalOrderService().create_staff_order(
        customer=customer,
        actor=actor,
        name="Lot",
        external_url="https://example.com/lot",
        meterage_linear_m="2.5",
        external_visual_count=3,
    )
    old_total = order.total_amount
    Payment.objects.create(order=order, status=status, amount=old_total, currency=order.currency)
    with pytest.raises(ValidationError, match="paiement"):
        OrderUploadService().set_staff_external_visual_count(order=order, actor=actor, value="5")
    with pytest.raises(ValidationError, match="paiement"):
        OrderUploadService().set_staff_order_meterage_linear_override(
            order=order, actor=actor, raw_value="3", external_visual_count="5"
        )
    order.refresh_from_db()
    assert order.total_amount == old_total
    assert order.pricing_status == Order.PricingStatus.PRICED
    assert order.meterage_override_linear_m == Decimal("2.5")
    assert order.uploads.get().external_visual_count == 3
    assert order.items.get(service_type="file_preparation").quantity == 3


@pytest.mark.django_db
def test_visual_count_update_requires_order_change_permission():
    from apps.uploads.services.uploads import OrderUploadService

    actor, customer = client_scope()
    order = ExternalOrderService().create_client_order(
        customer=customer, actor=actor, name="Lot", external_url="https://example.com/lot"
    )
    with pytest.raises(ValidationError, match="Permission"):
        OrderUploadService().set_staff_order_meterage_linear_override(
            order=order,
            actor=staff_user(full_permissions=False),
            raw_value="2.5",
            external_visual_count="5",
        )
    order.refresh_from_db()
    assert order.meterage_override_linear_m is None
    assert order.uploads.get().external_visual_count == 1
    assert not AuditLogEntry.objects.filter(action="order.external_visual_count_updated").exists()


@pytest.mark.django_db
def test_frozen_meterage_empty_confirm_is_noop_when_already_resolved():
    """Paiement lancé : confirmation vide OK si métrage déjà connu (workflow Atelier)."""
    from apps.billing.models import Payment
    from apps.uploads.services.uploads import OrderUploadService

    _, customer = client_scope("frozen-confirm")
    customer.default_billing_mode = Order.BillingMode.IMMEDIATE
    customer.save(update_fields=["default_billing_mode"])
    actor = staff_user()
    order = ExternalOrderService().create_staff_order(
        customer=customer,
        actor=actor,
        name="Lot figé",
        external_url="https://example.com/lot-fige",
        meterage_linear_m="2.5",
        external_visual_count=2,
    )
    Payment.objects.create(
        order=order, status=Payment.Status.CAPTURED, amount=order.total_amount, currency=order.currency
    )
    out = OrderUploadService().set_staff_order_meterage_linear_override(
        order=order, actor=actor, raw_value="", external_visual_count=None
    )
    assert out.meterage_override_linear_m == Decimal("2.5")
    with pytest.raises(ValidationError, match="paiement"):
        OrderUploadService().set_staff_order_meterage_linear_override(
            order=order, actor=actor, raw_value="4", external_visual_count=None
        )
