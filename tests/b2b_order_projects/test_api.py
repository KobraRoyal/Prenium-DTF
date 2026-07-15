import pytest
from apps.b2b_order_projects.models import B2BOrderProject
from apps.customers.models import CustomerMembership
from apps.uploads.services.asset_analysis import AssetAnalysisService
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .helpers import create_scope, png_upload


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_client_crud_submit_and_server_fields_are_protected():
    _user, customer, client = create_scope("member@example.com")
    list_url = reverse(
        "b2b_order_projects:client-list-create",
        kwargs={"customer_public_id": customer.public_id},
    )
    response = client.post(
        list_url,
        {"name": "Collection", "status": "converted", "confirmed_total": "0.01"},
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["status"] == B2BOrderProject.Status.DRAFT
    assert response.json()["confirmed_total"] is None
    project_id = response.json()["public_id"]

    item_url = reverse(
        "b2b_order_projects:client-item-create",
        kwargs={"customer_public_id": customer.public_id, "project_public_id": project_id},
    )
    item_response = client.post(
        item_url,
        {"name": "Logo", "width_mm": 120, "height_mm": 80, "quantity": 5},
        format="json",
    )
    assert item_response.status_code == 201
    item_id = item_response.json()["public_id"]
    asset_url = reverse(
        "b2b_order_projects:client-item-asset",
        kwargs={
            "customer_public_id": customer.public_id,
            "project_public_id": project_id,
            "item_public_id": item_id,
        },
    )
    asset_response = client.post(asset_url, {"file": png_upload()}, format="multipart")
    assert asset_response.status_code == 201
    assert asset_response.json()["asset"]["replace_allowed"] is True
    version_id = asset_response.json()["asset"]["version_public_id"]
    AssetAnalysisService().analyze(version_public_id=version_id, source="test")

    replace_response = client.post(
        reverse(
            "b2b_order_projects:client-item-asset-replace",
            kwargs={
                "customer_public_id": customer.public_id,
                "project_public_id": project_id,
                "item_public_id": item_id,
            },
        ),
        {"file": png_upload("replacement.png")},
        format="multipart",
    )
    assert replace_response.status_code == 400
    assert replace_response.json()["code"] == "ASSET_REPLACEMENT_CLOSED"

    confirm_url = reverse(
        "b2b_order_projects:client-item-confirm-analysis",
        kwargs={
            "customer_public_id": customer.public_id,
            "project_public_id": project_id,
            "item_public_id": item_id,
        },
    )
    confirmation_required = client.post(confirm_url, {"confirmed": False}, format="json")
    assert confirmation_required.status_code == 400
    confirmed = client.post(
        confirm_url,
        {"confirmed": True, "support_color_hex": "#112233"},
        format="json",
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["asset"]["replace_allowed"] is False
    assert confirmed.json()["asset"]["technical_review"]["confirmed"] is True

    submit_url = reverse(
        "b2b_order_projects:client-submit",
        kwargs={"customer_public_id": customer.public_id, "project_public_id": project_id},
    )
    assert client.post(submit_url).json()["status"] == B2BOrderProject.Status.SUBMITTED
    assert B2BOrderProject.objects.get(public_id=project_id).converted_order is None


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_cross_tenant_access_does_not_reveal_project():
    user, owner_customer, _owner_client = create_scope("owner@example.com")
    project = B2BOrderProject.objects.create(
        customer=owner_customer,
        created_by=user,
        project_number="DTF-B2B-2026-999991",
        name="Secret",
    )
    _other_user, other_customer, other_client = create_scope("other@example.com", "Autre")

    response = other_client.get(
        reverse(
            "b2b_order_projects:client-detail",
            kwargs={
                "customer_public_id": other_customer.public_id,
                "project_public_id": project.public_id,
            },
        )
    )
    assert response.status_code == 404

    confirmation = other_client.post(
        reverse(
            "b2b_order_projects:client-item-confirm-analysis",
            kwargs={
                "customer_public_id": other_customer.public_id,
                "project_public_id": project.public_id,
                "item_public_id": project.public_id,
            },
        ),
        {"confirmed": True},
        format="json",
    )
    assert confirmation.status_code == 404


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=False)
def test_global_feature_flag_blocks_access():
    _user, customer, client = create_scope("blocked@example.com")
    response = client.get(
        reverse(
            "b2b_order_projects:client-list-create",
            kwargs={"customer_public_id": customer.public_id},
        )
    )
    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_global_feature_exposes_new_order_to_active_customers():
    _user, customer, client = create_scope("blocked-customer@example.com", enabled=False)
    response = client.get(
        reverse(
            "b2b_order_projects:client-list-create",
            kwargs={"customer_public_id": customer.public_id},
        )
    )
    assert response.status_code == 200


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_staff_needs_domain_permission_for_order_projects():
    staff = get_user_model().objects.create_user(
        email="staff@example.com", password="pass", is_staff=True
    )
    staff.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    staff_client = APIClient()
    staff_client.login(email=staff.email, password="pass")
    staff_url = reverse("b2b_order_projects:staff-list")
    assert staff_client.get(staff_url).status_code == 403

    staff.user_permissions.add(Permission.objects.get(codename="view_b2borderproject"))
    assert staff_client.get(staff_url).status_code == 200


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_item_update_duplicate_reorder_and_delete_are_scoped():
    _user, customer, client = create_scope("items@example.com")
    project = client.post(
        reverse(
            "b2b_order_projects:client-list-create",
            kwargs={"customer_public_id": customer.public_id},
        ),
        {"name": "Projet lignes"},
        format="json",
    ).json()
    create_url = reverse(
        "b2b_order_projects:client-item-create",
        kwargs={
            "customer_public_id": customer.public_id,
            "project_public_id": project["public_id"],
        },
    )
    first = client.post(
        create_url,
        {"name": "A", "width_mm": 10, "height_mm": 20, "quantity": 1},
        format="json",
    ).json()
    second = client.post(
        create_url,
        {"name": "B", "width_mm": 30, "height_mm": 40, "quantity": 2},
        format="json",
    ).json()

    detail_url = reverse(
        "b2b_order_projects:client-item-detail",
        kwargs={
            "customer_public_id": customer.public_id,
            "project_public_id": project["public_id"],
            "item_public_id": first["public_id"],
        },
    )
    updated = client.patch(detail_url, {"quantity": 4}, format="json")
    assert updated.status_code == 200
    assert updated.json()["quantity"] == 4

    duplicate_url = reverse(
        "b2b_order_projects:client-item-duplicate",
        kwargs={
            "customer_public_id": customer.public_id,
            "project_public_id": project["public_id"],
            "item_public_id": first["public_id"],
        },
    )
    duplicate = client.post(duplicate_url).json()
    reorder_url = reverse(
        "b2b_order_projects:client-item-reorder",
        kwargs={
            "customer_public_id": customer.public_id,
            "project_public_id": project["public_id"],
        },
    )
    reordered = client.post(
        reorder_url,
        {
            "item_public_ids": [
                duplicate["public_id"],
                second["public_id"],
                first["public_id"],
            ]
        },
        format="json",
    )
    assert reordered.status_code == 200
    assert [item["public_id"] for item in reordered.json()["items"]] == [
        duplicate["public_id"],
        second["public_id"],
        first["public_id"],
    ]
    assert client.delete(detail_url).status_code == 204


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_anonymous_and_inactive_membership_are_refused():
    user, customer, _client = create_scope("inactive@example.com")
    url = reverse(
        "b2b_order_projects:client-list-create",
        kwargs={"customer_public_id": customer.public_id},
    )
    assert APIClient().get(url).status_code in {401, 403}

    CustomerMembership.objects.filter(customer=customer, user=user).update(is_active=False)
    client = APIClient()
    client.login(email=user.email, password="pass")
    assert client.get(url).status_code == 403


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, B2B_ORDER_PROJECT_LIST_PAGE_SIZE=2)
def test_project_list_is_paginated():
    user, customer, client = create_scope("pagination@example.com")
    for index in range(3):
        B2BOrderProject.objects.create(
            customer=customer,
            created_by=user,
            project_number=f"DTF-B2B-2026-9998{index}",
            name=f"Projet {index}",
        )
    response = client.get(
        reverse(
            "b2b_order_projects:client-list-create",
            kwargs={"customer_public_id": customer.public_id},
        )
    )
    assert response.status_code == 200
    assert len(response.json()["projects"]) == 2
    assert response.json()["pagination"]["total_items"] == 3
