from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import Payment
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order


def _client_for(*, customer, role: str, email: str) -> Client:
    user = User.objects.create_user(email=email, password="pass")
    CustomerMembership.objects.create(customer=customer, user=user, role=role)
    client = Client()
    assert client.login(email=email, password="pass")
    return client


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role",
    [CustomerMembership.Role.OWNER, CustomerMembership.Role.ADMIN],
)
def test_financial_dashboard_is_limited_to_customer_managers(role: str) -> None:
    customer = Customer.objects.create(name="Pilotage", b2b_order_projects_enabled=True)
    order = Order.objects.create(
        customer=customer,
        status=Order.Status.SUBMITTED,
        pricing_status=Order.PricingStatus.PRICED,
        billing_mode=Order.BillingMode.IMMEDIATE,
        total_amount=Decimal("125.00"),
    )
    Payment.objects.create(
        order=order,
        status=Payment.Status.CAPTURED,
        amount=Decimal("125.00"),
        currency="EUR",
        captured_at=timezone.now(),
    )

    html = (
        _client_for(
            customer=customer,
            role=role,
            email=f"{role}-dashboard@example.com",
        )
        .get(reverse("portal:client-dashboard"))
        .content.decode()
    )

    assert "Budget des six derniers mois" in html
    assert "Cliquez sur une barre" in html
    assert '"awaiting"' in html
    assert 'id="client-budget-chart-data"' in html
    assert 'id="client-dashboard-orders-title"' in html
    assert "Commandes" in html
    assert "js/client-dashboard-chart.js" in html


@pytest.mark.django_db
def test_financial_dashboard_is_hidden_from_collaborator_and_readonly() -> None:
    customer = Customer.objects.create(name="Pilotage restreint", b2b_order_projects_enabled=True)
    Order.objects.create(
        customer=customer,
        status=Order.Status.SUBMITTED,
        pricing_status=Order.PricingStatus.PRICED,
        total_amount=Decimal("990.00"),
    )

    for role in (CustomerMembership.Role.MEMBER, CustomerMembership.Role.READONLY):
        html = (
            _client_for(
                customer=customer,
                role=role,
                email=f"{role}-no-finance@example.com",
            )
            .get(reverse("portal:client-dashboard"))
            .content.decode()
        )
        assert "Budget des six derniers mois" not in html
        assert '"awaiting"' not in html
        assert 'id="client-budget-chart-data"' not in html
        assert "Où en sont vos commandes" in html


@pytest.mark.django_db
def test_dashboard_exposes_clickable_operational_drilldowns() -> None:
    customer = Customer.objects.create(
        name="Pilotage opérationnel", b2b_order_projects_enabled=True
    )

    html = (
        _client_for(
            customer=customer,
            role=CustomerMembership.Role.OWNER,
            email="owner-drilldown@example.com",
        )
        .get(reverse("portal:client-dashboard"))
        .content.decode()
    )

    assert "Cliquez sur une section" in html
    assert 'id="client-activity-chart-data"' in html
    assert 'id="client-dashboard-orders"' in html


@pytest.mark.django_db
def test_chart_filter_replaces_the_shared_orders_section() -> None:
    customer = Customer.objects.create(name="Pilotage filtré", b2b_order_projects_enabled=True)
    client = _client_for(
        customer=customer,
        role=CustomerMembership.Role.OWNER,
        email="owner-filter@example.com",
    )

    response = client.get(
        reverse(
            "portal:client-dashboard-results",
            kwargs={"customer_public_id": customer.public_id},
        ),
        {"kind": "projects"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    html = response.content.decode()
    assert 'id="client-dashboard-orders"' in html
    assert "Dossiers à reprendre" in html
