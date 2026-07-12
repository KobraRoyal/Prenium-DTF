import uuid

import pytest
from apps.b2b_order_projects.models import B2BOrderProject
from apps.customers.models import Customer
from apps.orders.models import Order
from apps.orders.references import order_client_reference, project_client_reference
from django.contrib.auth import get_user_model


@pytest.mark.django_db
def test_order_client_reference_from_linked_project():
    user = get_user_model().objects.create_user(email="ref@example.com", password="pass")
    customer = Customer.objects.create(name="Ref")
    order = Order.objects.create(customer=customer, created_by=user)
    B2BOrderProject.objects.create(
        customer=customer,
        created_by=user,
        project_number="DTF-B2B-2026-100001",
        name="Collection été",
        converted_order=order,
        status=B2BOrderProject.Status.CONVERTED,
    )
    assert order_client_reference(order) == "Collection été"


@pytest.mark.django_db
def test_order_client_reference_falls_back_to_customer_note():
    user = get_user_model().objects.create_user(email="note@example.com", password="pass")
    customer = Customer.objects.create(name="Ref")
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        customer_note="Réassort boutique\nDate souhaitée : 2026-08-01",
    )
    assert order_client_reference(order) == "Réassort boutique"


def test_project_client_reference_prefers_name():
    project = B2BOrderProject(name="Ma commande", customer_reference="REF-42")
    assert project_client_reference(project) == "Ma commande"
