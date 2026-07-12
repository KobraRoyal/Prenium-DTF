import pytest
from apps.b2b_order_projects.models import B2BOrderProject
from apps.b2b_order_projects.services import B2BOrderProjectService
from apps.orders.models import Order
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from .test_portal import portal_scope


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_converted_projects_are_excluded_from_in_progress_lists():
    user, customer, client = portal_scope()
    service = B2BOrderProjectService()

    active = B2BOrderProject.objects.create(
        customer=customer,
        created_by=user,
        project_number="DTF-B2B-2026-100001",
        name="En cours",
        status=B2BOrderProject.Status.INCOMPLETE,
    )
    converted = B2BOrderProject.objects.create(
        customer=customer,
        created_by=user,
        project_number="DTF-B2B-2026-100002",
        name="Déjà transmise",
        status=B2BOrderProject.Status.CONVERTED,
        converted_at=timezone.now(),
        converted_order=Order.objects.create(
            customer=customer,
            created_by=user,
            status=Order.Status.SUBMITTED,
            currency="EUR",
            subtotal_amount="10.00",
            total_amount="10.00",
        ),
    )

    in_progress = list(service.list_customer_projects_in_progress(customer))
    assert active in in_progress
    assert converted not in in_progress

    list_url = reverse(
        "portal:client-order-project-list",
        kwargs={"customer_public_id": customer.public_id},
    )
    dashboard_url = reverse("portal:client-dashboard")
    list_html = client.get(list_url).content.decode()
    dashboard_html = client.get(dashboard_url).content.decode()

    assert active.name in list_html
    assert converted.name not in list_html
    assert active.name in dashboard_html
    if "Commandes à finaliser" in dashboard_html:
        prep_section = dashboard_html.split("Commandes transmises", 1)[0]
        assert converted.name not in prep_section
        assert converted.project_number not in prep_section
