from decimal import Decimal
from unittest.mock import patch

import pytest
from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerBillingProfile, CustomerMembership
from apps.orders.models import Order
from apps.orders.services.pricing import OrderPricingService, billable_sqm_from_physical_size
from apps.uploads.models import OrderUpload, OrderUploadInspection
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings


def _seed_catalog_dtf_and_file_prep(
    *,
    dtf_price: str = "10.00",
    prep_price: str = "10.00",
    dtf_code: str = "dtf-meter",
    prep_code: str = "file-prep",
) -> None:
    CatalogService.objects.create(
        code=dtf_code,
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price=dtf_price,
        currency="EUR",
        display_order=1,
    )
    CatalogService.objects.create(
        code=prep_code,
        name="Preparation fichier",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price=prep_price,
        currency="EUR",
        display_order=2,
    )


@pytest.mark.django_db
@override_settings(DTF_PRINT_DPI=300, DTF_LAIZE_CM=55, DTF_METERAGE_AREA_MODE="laize_fit")
def test_estimate_meterage_laize_fit_uses_full_laize_strip_when_print_wider_than_laize():
    """Motif plus large que la laize → m² min. = grand côté × laize (pas simple rectangle pixel)."""
    user = get_user_model().objects.create_user(email="laize@example.com", password="pass")
    customer = Customer.objects.create(name="Laize")
    CustomerMembership.objects.create(customer=customer, user=user)
    CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="10.00",
        currency="EUR",
        display_order=1,
    )
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PENDING,
        currency="EUR",
        subtotal_amount=Decimal("0"),
        total_amount=Decimal("0"),
    )
    upload = OrderUpload(
        order=order,
        uploaded_by=user,
        original_filename="wide.png",
        mime_type="image/png",
        size_bytes=8,
        quantity=1,
    )
    upload.file.save("wide.png", ContentFile(b"fakebytes"), save=True)
    OrderUploadInspection.objects.create(
        order_upload=upload,
        status=OrderUploadInspection.Status.OK,
        image_width=8000,
        image_height=7000,
    )
    svc = OrderPricingService()
    m2 = svc.estimate_meterage_from_inspection(upload=upload)
    dpi = Decimal(300)
    laize_m = Decimal("0.55")
    wm = Decimal(8000) / dpi * Decimal("0.0254")
    hm = Decimal(7000) / dpi * Decimal("0.0254")
    expected = max(wm, hm) * laize_m
    assert m2 == expected.quantize(Decimal("0.0001"))


@pytest.mark.django_db
@override_settings(DTF_PRINT_DPI=300, DTF_LAIZE_CM=55, DTF_METERAGE_AREA_MODE="pixel_rectangle")
def test_estimate_meterage_pixel_rectangle_ignores_laize():
    user = get_user_model().objects.create_user(email="rect@example.com", password="pass")
    customer = Customer.objects.create(name="Rect")
    CustomerMembership.objects.create(customer=customer, user=user)
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PENDING,
        currency="EUR",
        subtotal_amount=Decimal("0"),
        total_amount=Decimal("0"),
    )
    upload = OrderUpload(
        order=order,
        uploaded_by=user,
        original_filename="wide.png",
        mime_type="image/png",
        size_bytes=8,
        quantity=1,
    )
    upload.file.save("wide.png", ContentFile(b"fakebytes"), save=True)
    OrderUploadInspection.objects.create(
        order_upload=upload,
        status=OrderUploadInspection.Status.OK,
        image_width=8000,
        image_height=7000,
    )
    svc = OrderPricingService()
    m2 = svc.estimate_meterage_from_inspection(upload=upload)
    dpi = Decimal(300)
    wm = Decimal(8000) / dpi * Decimal("0.0254")
    hm = Decimal(7000) / dpi * Decimal("0.0254")
    expected = (wm * hm).quantize(Decimal("0.0001"))
    assert m2 == expected


def test_billable_sqm_from_physical_size_laize_fit():
    laize = Decimal("0.55")
    a = billable_sqm_from_physical_size(
        width_m=Decimal("0.30"),
        height_m=Decimal("0.80"),
        laize_m=laize,
        mode="laize_fit",
    )
    assert a == (Decimal("0.30") * Decimal("0.80")).quantize(Decimal("0.0001"))
    b = billable_sqm_from_physical_size(
        width_m=Decimal("0.60"),
        height_m=Decimal("0.70"),
        laize_m=laize,
        mode="laize_fit",
    )
    assert b == (Decimal("0.70") * laize).quantize(Decimal("0.0001"))


@pytest.mark.django_db
def test_resolve_unit_price_uses_catalog_when_no_profile():
    customer = Customer.objects.create(name="Sans profil")
    CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="11.00",
        currency="EUR",
        display_order=1,
    )
    price = OrderPricingService().resolve_unit_price_per_sqm(customer=customer)
    assert price == Decimal("11.00")


@pytest.mark.django_db
def test_resolve_unit_price_uses_billing_profile_override():
    """Grille client au m² prioritaire sur le catalogue DTF."""
    customer = Customer.objects.create(name="Avec profil")
    CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="99.00",
        currency="EUR",
        display_order=1,
    )
    CustomerBillingProfile.objects.create(
        customer=customer,
        price_per_sqm_eur=Decimal("7.50"),
    )
    price = OrderPricingService().resolve_unit_price_per_sqm(customer=customer)
    assert price == Decimal("7.50")


@pytest.mark.django_db
def test_resolve_file_preparation_fee_uses_catalog_when_not_negotiated():
    customer = Customer.objects.create(name="Catalog prep")
    CatalogService.objects.create(
        code="file-prep",
        name="Preparation fichier",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price="10.00",
        currency="EUR",
        display_order=1,
    )
    fee = OrderPricingService().resolve_file_preparation_fee_per_file(customer=customer)
    assert fee == Decimal("10.00")


@pytest.mark.django_db
def test_resolve_file_preparation_fee_uses_negotiated_customer_value():
    customer = Customer.objects.create(
        name="Nego prep",
        negotiated_file_preparation_fee_eur=Decimal("8.50"),
    )
    fee = OrderPricingService().resolve_file_preparation_fee_per_file(customer=customer)
    assert fee == Decimal("8.50")


@pytest.mark.django_db
def test_open_balance_excludes_draft_and_includes_priced_deferred():
    user = get_user_model().objects.create_user(email="u@example.com", password="pass")
    customer = Customer.objects.create(name="B2B")
    svc = OrderPricingService()
    CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="10.00",
        currency="EUR",
        display_order=1,
    )
    Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.DRAFT,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PRICED,
        currency="EUR",
        subtotal_amount=Decimal("50.00"),
        total_amount=Decimal("50.00"),
    )
    Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PRICED,
        currency="EUR",
        subtotal_amount=Decimal("40.00"),
        total_amount=Decimal("40.00"),
    )
    balance = svc.open_balance_for_customer_excluding_order(customer=customer, exclude_order=None)
    assert balance == Decimal("40.00")


@pytest.mark.django_db
def test_credit_hold_blocked_when_projected_exceeds_limit():
    user = get_user_model().objects.create_user(email="b@example.com", password="pass")
    customer = Customer.objects.create(name="Encours")
    CustomerBillingProfile.objects.create(
        customer=customer,
        credit_limit_eur=Decimal("100.00"),
        enforce_credit_block=True,
    )
    CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="10.00",
        currency="EUR",
        display_order=1,
    )
    Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PRICED,
        currency="EUR",
        subtotal_amount=Decimal("80.00"),
        total_amount=Decimal("80.00"),
    )
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PENDING,
        currency="EUR",
        subtotal_amount=Decimal("0"),
        total_amount=Decimal("0"),
    )
    svc = OrderPricingService()
    hold = svc.evaluate_credit_hold(order=order, priced_total=Decimal("30.00"))
    assert hold == Order.CreditHoldStatus.BLOCKED


@pytest.mark.django_db
def test_credit_hold_warning_when_not_enforced():
    user = get_user_model().objects.create_user(email="w@example.com", password="pass")
    customer = Customer.objects.create(name="Warn")
    CustomerBillingProfile.objects.create(
        customer=customer,
        credit_limit_eur=Decimal("100.00"),
        enforce_credit_block=False,
    )
    CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="10.00",
        currency="EUR",
        display_order=1,
    )
    Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PRICED,
        currency="EUR",
        subtotal_amount=Decimal("80.00"),
        total_amount=Decimal("80.00"),
    )
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PENDING,
        currency="EUR",
        subtotal_amount=Decimal("0"),
        total_amount=Decimal("0"),
    )
    svc = OrderPricingService()
    hold = svc.evaluate_credit_hold(order=order, priced_total=Decimal("30.00"))
    assert hold == Order.CreditHoldStatus.WARNING


@pytest.mark.django_db
def test_compute_and_persist_sets_lines_and_sends_priced_email():
    user = get_user_model().objects.create_user(email="client@example.com", password="pass")
    customer = Customer.objects.create(name="Tarif", billing_email="client@example.com")
    CustomerMembership.objects.create(customer=customer, user=user)
    _seed_catalog_dtf_and_file_prep(dtf_price="10.00", prep_price="10.00")
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PENDING,
        currency="EUR",
        subtotal_amount=Decimal("0"),
        total_amount=Decimal("0"),
    )
    upload = OrderUpload(
        order=order,
        uploaded_by=user,
        original_filename="f.png",
        mime_type="image/png",
        size_bytes=8,
        quantity=1,
    )
    upload.file.save("f.png", ContentFile(b"fakebytes"), save=True)
    OrderUploadInspection.objects.create(
        order_upload=upload,
        status=OrderUploadInspection.Status.OK,
        image_width=3000,
        image_height=1500,
    )

    from django.core import mail

    mail.outbox.clear()
    with patch("apps.notifications.tasks.send_order_priced_email_task.delay") as task_delay:
        with TestCase.captureOnCommitCallbacks(execute=True):
            OrderPricingService().compute_and_persist_order_pricing(
                order=order,
                actor=user,
                source="test",
            )

    order.refresh_from_db()
    assert order.pricing_status == Order.PricingStatus.PRICED
    lines = list(order.items.order_by("position"))
    assert len(lines) == 2
    assert lines[0].service_type == CatalogService.ServiceType.DTF_TRANSFER
    assert lines[1].service_type == CatalogService.ServiceType.FILE_PREPARATION
    assert lines[1].line_total == Decimal("10.00")
    assert order.total_amount == lines[0].line_total + lines[1].line_total
    assert order.total_amount > Decimal("0")
    task_delay.assert_called_once_with(str(order.public_id))

    from apps.notifications.tasks import send_order_priced_email_task

    send_order_priced_email_task.run(str(order.public_id))
    assert len(mail.outbox) == 1
    assert "tarif" in mail.outbox[0].subject.lower() or "Tarif" in mail.outbox[0].subject


@pytest.mark.django_db
@override_settings(DTF_LAIZE_CM=100)
def test_compute_uses_staff_meterage_override_when_set():
    """Saisie linéaire opérateur × laize × qté prioritaire sur le calcul inspection."""
    user = get_user_model().objects.create_user(email="op@example.com", password="pass")
    customer = Customer.objects.create(name="Override")
    CustomerMembership.objects.create(customer=customer, user=user)
    _seed_catalog_dtf_and_file_prep(dtf_price="10.00", prep_price="10.00")
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PENDING,
        currency="EUR",
        subtotal_amount=Decimal("0"),
        total_amount=Decimal("0"),
        meterage_override_linear_m=Decimal("2.5000"),
    )
    upload = OrderUpload(
        order=order,
        uploaded_by=user,
        original_filename="f.png",
        mime_type="image/png",
        size_bytes=8,
        quantity=1,
    )
    upload.file.save("f.png", ContentFile(b"fakebytes"), save=True)
    OrderUploadInspection.objects.create(
        order_upload=upload,
        status=OrderUploadInspection.Status.OK,
        image_width=3000,
        image_height=1500,
    )

    OrderPricingService().compute_and_persist_order_pricing(
        order=order,
        actor=user,
        source="test",
    )

    upload.refresh_from_db()
    order.refresh_from_db()
    assert upload.meterage_sqm == Decimal("2.5000")
    lines = list(order.items.order_by("position"))
    assert len(lines) == 2
    assert lines[0].quantity == Decimal("2.5000")
    assert lines[0].line_total == Decimal("25.00")
    assert lines[1].service_type == CatalogService.ServiceType.FILE_PREPARATION
    assert lines[1].line_total == Decimal("10.00")
    assert order.total_amount == Decimal("35.00")


@pytest.mark.django_db
def test_compute_rejects_non_deferred_order():
    user = get_user_model().objects.create_user(email="inj@example.com", password="pass")
    customer = Customer.objects.create(name="Immediate")
    _seed_catalog_dtf_and_file_prep(dtf_price="10.00", prep_price="10.00")
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.IMMEDIATE,
        pricing_status=Order.PricingStatus.PRICED,
        currency="EUR",
        subtotal_amount=Decimal("1.00"),
        total_amount=Decimal("1.00"),
    )
    with pytest.raises(ValidationError, match="facturation différée"):
        OrderPricingService().compute_and_persist_order_pricing(
            order=order,
            actor=user,
            source="test",
        )
