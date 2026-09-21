from decimal import Decimal

import pytest
from apps.accounts.models import StaffMembership
from apps.accounts.services.staff_roles import sync_staff_access
from apps.auditlog.models import AuditLogEntry
from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order, OrderLine
from apps.orders.services.pricing import OrderPricingService
from apps.shipping.services.methods import ShippingMethodService
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from tests.orders.test_order_pricing_service import _seed_catalog_dtf_and_file_prep

pytestmark = pytest.mark.django_db


def _staff_admin():
    staff = get_user_model().objects.create_user(
        email="billing-adjust@example.com", password="pass", is_staff=True
    )
    StaffMembership.objects.create(user=staff, role="admin")
    sync_staff_access(user=staff, role="admin", is_active=True)
    client = Client()
    client.force_login(staff)
    return staff, client


def _priced_deferred_order(*, billing_mode=Order.BillingMode.DEFERRED):
    if not CatalogService.objects.filter(code="dtf-meter").exists():
        _seed_catalog_dtf_and_file_prep()
    ShippingMethodService().ensure_default_methods()
    user = get_user_model().objects.create_user(
        email=f"encours-{billing_mode}-{timezone.now().timestamp()}@example.com",
        password="pass",
    )
    customer = Customer.objects.create(
        name=f"Client {billing_mode}",
        default_billing_mode=Customer.DefaultBillingMode.DEFERRED,
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=billing_mode,
        pricing_status=Order.PricingStatus.PRICED,
        currency="EUR",
        shipping_method_code="standard",
        shipping_method_name="Livraison standard",
        shipping_amount=Decimal("8.00"),
        subtotal_amount=Decimal("40.00"),
        tax_rate=Decimal("0"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("48.00"),
    )
    dtf = CatalogService.objects.get(code="dtf-meter")
    prep = CatalogService.objects.get(code="file-prep")
    OrderLine.objects.create(
        order=order,
        service=dtf,
        position=1,
        service_code=dtf.code,
        service_name=dtf.name,
        service_type=dtf.service_type,
        unit=dtf.unit,
        quantity=Decimal("2.0000"),
        unit_price=Decimal("15.00"),
        line_total=Decimal("30.00"),
    )
    OrderLine.objects.create(
        order=order,
        service=prep,
        position=2,
        service_code=prep.code,
        service_name=prep.name,
        service_type=prep.service_type,
        unit=prep.unit,
        quantity=Decimal("1.0000"),
        unit_price=Decimal("10.00"),
        line_total=Decimal("10.00"),
    )
    return order


def test_staff_can_adjust_qty_unit_price_and_shipping_for_deferred():
    staff, _client = _staff_admin()
    order = _priced_deferred_order()
    lines = list(order.items.order_by("position"))
    refreshed = OrderPricingService().apply_staff_billing_adjustments(
        order=order,
        actor=staff,
        source="test",
        shipping_method_code="pickup",
        shipping_amount="3.50",
        line_adjustments=[
            {
                "line_public_id": str(lines[0].public_id),
                "quantity": "1.5",
                "unit_price": "20.00",
            },
            {
                "line_public_id": str(lines[1].public_id),
                "quantity": "2",
                "unit_price": "12.00",
            },
        ],
    )
    assert refreshed.shipping_method_code == "pickup"
    assert refreshed.shipping_amount == Decimal("3.50")
    assert refreshed.subtotal_amount == Decimal("54.00")  # 30 + 24
    assert refreshed.total_amount == Decimal("57.50")
    assert refreshed.manual_billing_adjusted_at is not None
    assert refreshed.volume_discount_amount == Decimal("0.00")
    lines = list(refreshed.items.order_by("position"))
    assert lines[0].quantity == Decimal("1.5000")
    assert lines[0].unit_price == Decimal("20.00")
    assert lines[0].line_total == Decimal("30.00")
    assert lines[1].line_total == Decimal("24.00")
    assert AuditLogEntry.objects.filter(action="order.manual_billing_adjusted").exists()


def test_staff_adjustment_rejects_immediate_orders():
    staff, _client = _staff_admin()
    order = _priced_deferred_order(billing_mode=Order.BillingMode.IMMEDIATE)
    lines = list(order.items.order_by("position"))
    with pytest.raises(ValidationError, match="encours"):
        OrderPricingService().apply_staff_billing_adjustments(
            order=order,
            actor=staff,
            source="test",
            shipping_method_code="standard",
            shipping_amount="8.00",
            line_adjustments=[
                {
                    "line_public_id": str(line.public_id),
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                }
                for line in lines
            ],
        )


def test_reprice_skips_manual_adjusted_order_prices():
    staff, _client = _staff_admin()
    order = _priced_deferred_order()
    lines = list(order.items.order_by("position"))
    OrderPricingService().apply_staff_billing_adjustments(
        order=order,
        actor=staff,
        source="test",
        shipping_method_code="standard",
        shipping_amount="8.00",
        line_adjustments=[
            {
                "line_public_id": str(lines[0].public_id),
                "quantity": "2",
                "unit_price": "99.00",
            },
            {
                "line_public_id": str(lines[1].public_id),
                "quantity": "1",
                "unit_price": "10.00",
            },
        ],
    )
    order.refresh_from_db()
    frozen_price = order.items.order_by("position").first().unit_price
    OrderPricingService().reprice_deferred_month(
        customer=order.customer,
        month=timezone.localdate(),
        actor=staff,
        source="test",
    )
    order.refresh_from_db()
    assert order.items.order_by("position").first().unit_price == frozen_price


def test_billing_panel_shows_adjustment_for_deferred_only():
    staff, client = _staff_admin()
    deferred = _priced_deferred_order()
    url = reverse("portal:staff-order-panel-billing", args=[deferred.public_id])
    page = client.get(url)
    assert page.status_code == 200
    html = page.content.decode()
    assert "Détail du montant" in html
    assert 'name="action" value="adjust_billing"' in html
    assert "Impression DTF" in html
    assert 'name="dtf_group_linear_m"' in html
    assert 'name="dtf_group_unit_price"' in html
    assert 'x-text="displayTotal()"' in html
    assert 'x-text="displaySubtotal()"' in html
    assert "data-billing-adjustment" in html
    assert "laize" in html.lower()
    assert 'placeholder="15.00"' in html
    assert 'placeholder="8.00"' in html
    assert "Valeurs actuelles" in html

    prep = deferred.items.get(service_type=CatalogService.ServiceType.FILE_PREPARATION)
    # 3 m lin. × laize 0,55 m = 1,65 m² → 1,65×11 + 10 = 28,15
    response = client.post(
        url,
        {
            "action": "adjust_billing",
            "shipping_method_code": "express",
            "shipping_amount": "12.00",
            "dtf_group_linear_m": "3",
            "dtf_group_unit_price": "11.00",
            f"line_{prep.public_id}_quantity": "1",
            f"line_{prep.public_id}_unit_price": "10.00",
        },
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    deferred.refresh_from_db()
    assert deferred.shipping_method_code == "express"
    assert deferred.shipping_amount == Decimal("12.00")
    assert deferred.subtotal_amount == Decimal("28.15")
    assert deferred.total_amount == Decimal("40.15")
    assert deferred.meterage_override_linear_m == Decimal("3.0000")
    assert "ajusté manuellement" in response.content.decode()
    assert "Détail du montant" in response.content.decode()

    immediate = _priced_deferred_order(billing_mode=Order.BillingMode.IMMEDIATE)
    immediate_page = client.get(
        reverse("portal:staff-order-panel-billing", args=[immediate.public_id])
    )
    assert "Valeurs actuelles" not in immediate_page.content.decode()
    assert 'name="action" value="adjust_billing"' not in immediate_page.content.decode()


def test_multiple_dtf_visuals_are_edited_as_one_meterage_line():
    staff, client = _staff_admin()
    order = _priced_deferred_order()
    dtf = CatalogService.objects.get(code="dtf-meter")
    OrderLine.objects.create(
        order=order,
        service=dtf,
        position=3,
        service_code=dtf.code,
        service_name=dtf.name,
        service_type=dtf.service_type,
        unit=dtf.unit,
        quantity=Decimal("1.0000"),
        unit_price=Decimal("15.00"),
        line_total=Decimal("15.00"),
    )
    order.subtotal_amount = Decimal("55.00")
    order.total_amount = Decimal("63.00")
    order.save(update_fields=["subtotal_amount", "total_amount", "updated_at"])
    url = reverse("portal:staff-order-panel-billing", args=[order.public_id])
    page = client.get(url)
    html = page.content.decode()
    assert html.count('name="dtf_group_linear_m"') == 1
    assert "2 visuels" in html
    assert "laize" in html.lower()
    prep = order.items.get(service_type=CatalogService.ServiceType.FILE_PREPARATION)
    # 4,5 m lin. × 0,55 = 2,475 m² → 2,475×12 + 10 = 39,70
    response = client.post(
        url,
        {
            "action": "adjust_billing",
            "shipping_method_code": "standard",
            "shipping_amount": "8.00",
            "dtf_group_linear_m": "4.5",
            "dtf_group_unit_price": "12.00",
            f"line_{prep.public_id}_quantity": "1",
            f"line_{prep.public_id}_unit_price": "10.00",
        },
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    order.refresh_from_db()
    dtf_lines = list(
        order.items.filter(service_type=CatalogService.ServiceType.DTF_TRANSFER).order_by(
            "position"
        )
    )
    assert len(dtf_lines) == 2
    assert sum((line.quantity for line in dtf_lines), Decimal("0")) == Decimal("2.4750")
    assert {line.unit_price for line in dtf_lines} == {Decimal("12.00")}
    assert order.subtotal_amount == Decimal("39.70")
    assert order.meterage_override_linear_m == Decimal("4.5000")
