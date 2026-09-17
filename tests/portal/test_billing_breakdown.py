from decimal import Decimal
from types import SimpleNamespace

import pytest
from apps.accounts.models import StaffMembership
from apps.accounts.services.staff_roles import sync_staff_access
from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order, OrderLine
from apps.portal.services.billing_breakdown import order_billing_breakdown
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client
from django.urls import reverse

from tests.orders.test_order_pricing_service import _seed_catalog_dtf_and_file_prep


@pytest.fixture
def scope():
    customer = Customer.objects.create(name="Client facturation")
    user = get_user_model().objects.create_user(email="bill-client@example.com", password="pass")
    CustomerMembership.objects.create(customer=customer, user=user, role="owner")
    client = Client()
    client.force_login(user)
    staff = get_user_model().objects.create_user(email="bill-admin@example.com", password="pass")
    StaffMembership.objects.create(user=staff, role="admin")
    sync_staff_access(user=staff, role="admin", is_active=True)
    admin = Client()
    admin.force_login(staff)
    return customer, user, client, staff, admin


pytestmark = pytest.mark.django_db


@pytest.fixture
def priced_order(scope):
    customer, user, *_ = scope
    _seed_catalog_dtf_and_file_prep()
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        billing_mode="deferred",
        pricing_status="priced",
        subtotal_amount="64.38",
        shipping_amount="8",
        tax_rate="0.2",
        tax_amount="14.48",
        total_amount="86.86",
        meterage_override_linear_m="2.5",
    )
    for position, code, quantity, price, total in (
        (1, "dtf-meter", "1.375", "25", "34.38"),
        (2, "file-prep", "3", "10", "30"),
    ):
        service = CatalogService.objects.get(code=code)
        OrderLine.objects.create(
            order=order,
            service=service,
            position=position,
            service_code=code,
            service_name=service.name,
            service_type=service.service_type,
            unit=service.unit,
            quantity=quantity,
            unit_price=price,
            line_total=total,
        )
    order.refresh_from_db()
    return order


def test_snapshot_preserves_file_count_meterage_prices_and_taxes(priced_order):
    CatalogService.objects.update(base_price=999)
    breakdown = order_billing_breakdown(priced_order)
    dtf, prep = breakdown["rows"]
    assert (dtf["quantity"], dtf["linear_m"], dtf["unit_price"]) == (
        Decimal("1.375"),
        Decimal("2.5"),
        Decimal("25"),
    )
    assert (prep["quantity"], prep["unit_price"], prep["amount"]) == (3, 10, 30)
    assert breakdown["vat_percent"] == 20
    assert not breakdown["discount"]
    priced_order.refresh_from_db()
    assert priced_order.total_amount == Decimal("86.86")


def test_discount_is_displayed_once_and_reconciles_to_subtotal(priced_order):
    priced_order.items.filter(service_type="dtf_transfer").update(
        unit_price="22.50", line_total="30.94"
    )
    priced_order.volume_discount_base_unit_price_eur = Decimal("25")
    priced_order.volume_discount_amount = Decimal("3.44")
    priced_order.volume_discount_percent = Decimal("10")
    priced_order.subtotal_amount = Decimal("60.94")
    breakdown = order_billing_breakdown(priced_order)
    assert breakdown["separate_discount"]
    assert breakdown["rows"][0]["amount"] == Decimal("34.38")
    assert (
        sum(row["amount"] for row in breakdown["rows"]) - breakdown["discount"]
        == priced_order.subtotal_amount
    )


def test_legacy_discount_without_base_is_explicitly_already_included(priced_order):
    priced_order.volume_discount_amount = Decimal("3.44")
    breakdown = order_billing_breakdown(priced_order)
    assert not breakdown["separate_discount"]
    assert breakdown["rows"][0]["amount"] == Decimal("34.38")
    html = render_to_string("components/portal/order_billing_breakdown.html", breakdown)
    assert "Déjà incluse" in html
    assert "−3,44" not in html


def test_catalogue_quantities_remain_linear_meters(priced_order):
    priced_order.source = "client_api"
    priced_order.billing_mode = "immediate"
    row = order_billing_breakdown(priced_order)["rows"][0]
    assert row["unit"] == "m linéaires"
    assert "linear_m" not in row


@pytest.mark.parametrize("staff", [False, True])
def test_both_panels_show_one_read_only_breakdown(scope, priced_order, staff):
    customer, _user, client, _staff, admin = scope
    if staff:
        url = reverse("portal:staff-order-panel-billing", args=[priced_order.public_id])
        response = admin.get(url)
    else:
        url = reverse(
            "portal:client-order-panel-billing", args=[customer.public_id, priced_order.public_id]
        )
        response = client.get(url, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    html = response.content.decode()
    assert html.count('aria-label="Détail du montant"') == 1
    for label in (
        "Préparation des fichiers",
        "3 fichier(s) × 10,00 EUR",
        "2,5 m linéaires",
        "Frais de port HT",
        "TVA · 20 %",
        "Total TTC",
        "86,86 EUR",
    ):
        assert label in html


def test_paid_client_still_sees_detail(priced_order):
    html = render_to_string(
        "portal/client/panels/billing.html",
        {
            "order": priced_order,
            "customer": priced_order.customer,
            "order_display_ref": "TEST-PAID",
            "payment": SimpleNamespace(
                status="captured", provider="stripe", amount="86.86", currency="EUR"
            ),
            "invoice": SimpleNamespace(invoice_number="TEST-PAID"),
        },
    )
    assert "Merci, c’est confirmé" in html
    assert "Télécharger le justificatif" in html
    assert html.count('aria-label="Détail du montant"') == 1
    assert "Préparation des fichiers" in html


def test_zero_shipping_and_vat_are_explicit(priced_order):
    priced_order.shipping_amount = Decimal("0")
    priced_order.tax_rate = Decimal("0")
    priced_order.tax_amount = Decimal("0")
    html = render_to_string(
        "components/portal/order_billing_breakdown.html", order_billing_breakdown(priced_order)
    )
    assert "TVA · 0 %" in html
    assert html.count("<dd>0,00 EUR</dd>") == 2


def test_pending_detail_does_not_show_stale_prices(priced_order):
    priced_order.pricing_status = "pending"
    html = render_to_string(
        "components/portal/order_billing_breakdown.html", order_billing_breakdown(priced_order)
    )
    assert "après le calcul du prix" in html
    assert "Total TTC" not in html
    assert "86,86" not in html


def test_other_customer_cannot_read_breakdown(scope, priced_order):
    customer, _user, client, *_ = scope
    other = Customer.objects.create(name="Other")
    priced_order.customer = other
    priced_order.save(update_fields=["customer"])
    url = reverse(
        "portal:client-order-panel-billing", args=[customer.public_id, priced_order.public_id]
    )
    assert client.get(url, HTTP_HX_REQUEST="true").status_code == 404


def test_client_cannot_read_staff_breakdown(scope, priced_order):
    _customer, _user, client, *_ = scope
    url = reverse("portal:staff-order-panel-billing", args=[priced_order.public_id])
    assert client.get(url).status_code == 403
