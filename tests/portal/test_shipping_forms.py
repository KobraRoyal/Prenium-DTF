import pytest
from apps.b2b_order_projects.models import B2BOrderProject
from apps.customers.models import Customer
from apps.orders.models import Order
from apps.portal.shipping_forms import build_shipment_form_data
from django.contrib.auth import get_user_model


@pytest.mark.django_db
def test_shipment_form_prefills_sendcloud_snapshot_from_project():
    user = get_user_model().objects.create_user(email="ship-form@example.com", password="pass")
    customer = Customer.objects.create(
        name="Acme Print",
        billing_email="factu@example.com",
        shipping_address_line1="ancienne voie",
        shipping_postal_code="75000",
        shipping_city="Paris",
        shipping_country="FR",
    )
    order = Order.objects.create(customer=customer, created_by=user)
    B2BOrderProject.objects.create(
        customer=customer,
        created_by=user,
        project_number="CMD-2026-000501",
        name="Planche Sendcloud",
        converted_order=order,
        status=B2BOrderProject.Status.CONVERTED,
        shipping_address={
            "name": "Marie Loire",
            "email": "marie@example.com",
            "phone": "0612345678",
            "company_name": "Atelier Loire",
            "house_number": "12",
            "line1": "quai de Loire",
            "city": "Orléans",
            "postal_code": "45000",
            "country": "FR",
        },
    )
    form = build_shipment_form_data(order=order)
    assert form["recipient_name"] == "Marie Loire"
    assert form["recipient_email"] == "marie@example.com"
    assert form["recipient_phone_number"] == "0612345678"
    assert form["recipient_house_number"] == "12"
    assert form["recipient_address_line_1"] == "quai de Loire"
    assert form["recipient_city"] == "Orléans"
    assert form["recipient_postal_code"] == "45000"
