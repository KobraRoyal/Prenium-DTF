from decimal import Decimal

import pytest
from apps.accounts.models import User
from apps.billing.models import Payment
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from django.test import Client
from django.urls import reverse
from django.utils import timezone


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

    html = _client_for(
        customer=customer,
        role=role,
        email=f"{role}-dashboard@example.com",
    ).get(reverse("portal:client-dashboard")).content.decode()

    assert "Budget des six derniers mois" in html
    assert "Commandé ce mois" in html
    assert "Paiements reçus" in html
    assert 'id="client-budget-chart-data"' in html
    assert 'js/client-dashboard-chart.js' in html


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
        html = _client_for(
            customer=customer,
            role=role,
            email=f"{role}-no-finance@example.com",
        ).get(reverse("portal:client-dashboard")).content.decode()
        assert "Budget des six derniers mois" not in html
        assert "Commandé ce mois" not in html
        assert 'id="client-budget-chart-data"' not in html
        assert "Où en sont vos commandes" in html
