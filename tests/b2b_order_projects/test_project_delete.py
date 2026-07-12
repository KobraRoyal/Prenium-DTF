import json

import pytest
from apps.b2b_order_projects.models import B2BOrderProject
from django.test import override_settings
from django.urls import reverse

from .helpers import create_scope


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_member_can_delete_draft_project_via_api():
    member, customer, member_client = create_scope("member-delete@example.com")
    project = B2BOrderProject.objects.create(
        customer=customer,
        created_by=member,
        project_number="DTF-B2B-2026-999991",
        name="Projet à supprimer",
    )
    detail_url = reverse(
        "b2b_order_projects:client-detail",
        kwargs={"customer_public_id": customer.public_id, "project_public_id": project.public_id},
    )
    assert member_client.delete(detail_url).status_code == 204
    assert not B2BOrderProject.objects.filter(pk=project.pk).exists()


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_submitted_project_without_conversion_can_be_deleted():
    _user, customer, client = create_scope("submitted-delete@example.com")
    project = B2BOrderProject.objects.create(
        customer=customer,
        project_number="DTF-B2B-2026-999990",
        name="Transmise",
        status=B2BOrderProject.Status.SUBMITTED,
    )
    detail_url = reverse(
        "b2b_order_projects:client-detail",
        kwargs={"customer_public_id": customer.public_id, "project_public_id": project.public_id},
    )
    assert client.delete(detail_url).status_code == 204
    assert not B2BOrderProject.objects.filter(pk=project.pk).exists()


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_under_review_project_cannot_be_deleted():
    _user, customer, client = create_scope("review-delete@example.com")
    project = B2BOrderProject.objects.create(
        customer=customer,
        project_number="DTF-B2B-2026-999989",
        name="En contrôle",
        status=B2BOrderProject.Status.UNDER_REVIEW,
    )
    detail_url = reverse(
        "b2b_order_projects:client-detail",
        kwargs={"customer_public_id": customer.public_id, "project_public_id": project.public_id},
    )
    response = client.delete(detail_url)
    assert response.status_code == 400
    assert response.json()["code"] == "PROJECT_NOT_DELETABLE"
    assert B2BOrderProject.objects.filter(pk=project.pk).exists()


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_portal_delete_redirects_to_list_with_toast():
    _user, customer, client = create_scope("portal-delete@example.com")
    project = B2BOrderProject.objects.create(
        customer=customer,
        project_number="DTF-B2B-2026-999988",
        name="Portail",
    )
    delete_url = reverse(
        "portal:client-order-project-cancel",
        kwargs={"customer_public_id": customer.public_id, "project_public_id": project.public_id},
    )
    response = client.post(delete_url)
    assert response.status_code == 302
    assert response.url == reverse(
        "portal:client-order-project-list",
        kwargs={"customer_public_id": customer.public_id},
    )
    toast = json.loads(response.headers["X-Prenium-Toast"])
    assert toast["message"] == "Commande supprimée."
    assert toast["variant"] == "success"
    assert not B2BOrderProject.objects.filter(pk=project.pk).exists()


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_delete_is_scoped_to_customer():
    owner_a, customer_a, _client_a = create_scope("owner-a@example.com")
    _owner_b, customer_b, client_b = create_scope("owner-b@example.com")
    project = B2BOrderProject.objects.create(
        customer=customer_a,
        created_by=owner_a,
        project_number="DTF-B2B-2026-999987",
        name="Scope A",
    )
    detail_url = reverse(
        "b2b_order_projects:client-detail",
        kwargs={"customer_public_id": customer_b.public_id, "project_public_id": project.public_id},
    )
    assert client_b.delete(detail_url).status_code == 404
    assert B2BOrderProject.objects.filter(pk=project.pk).exists()
