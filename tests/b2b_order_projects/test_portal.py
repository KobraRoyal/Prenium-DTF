import pytest
from apps.b2b_order_projects.models import B2BOrderProject
from apps.customers.models import Customer, CustomerMembership
from apps.uploads.services.asset_analysis import AssetAnalysisService
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, override_settings
from django.urls import reverse

from .helpers import pdf_upload, png_upload


def portal_scope(*, owner=True):
    user = get_user_model().objects.create_user(email="portal@example.com", password="pass")
    customer = Customer.objects.create(name="Portail", b2b_order_projects_enabled=True)
    CustomerMembership.objects.create(
        customer=customer,
        user=user,
        role=CustomerMembership.Role.OWNER if owner else CustomerMembership.Role.MEMBER,
    )
    client = Client()
    client.login(email=user.email, password="pass")
    return user, customer, client


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_client_portal_project_flow_is_functional():
    user, customer, client = portal_scope()
    create_url = reverse(
        "portal:client-order-project-create",
        kwargs={"customer_public_id": customer.public_id},
    )
    assert client.get(create_url).status_code == 200

    response = client.post(
        create_url,
        {"name": "Projet portail", "order_mode": "individual_designs"},
    )
    assert response.status_code == 302
    project = B2BOrderProject.objects.get(customer=customer)

    detail_url = reverse(
        "portal:client-order-project-detail",
        kwargs={"customer_public_id": customer.public_id, "project_public_id": project.public_id},
    )
    detail = client.get(detail_url)
    assert detail.status_code == 200
    assert "Finaliser la commande" in detail.content.decode()

    item_response = client.post(
        reverse(
            "portal:client-order-project-item-create",
            kwargs={
                "customer_public_id": customer.public_id,
                "project_public_id": project.public_id,
            },
        ),
        {
            "width_mm": "10.16",
            "height_mm": "6.77",
            "quantity": "3",
            "file": png_upload(),
        },
        HTTP_HX_REQUEST="true",
    )
    assert item_response.status_code == 200
    assert "HX-Refresh" not in item_response
    assert 'hx-trigger="load delay:1400ms"' in item_response.content.decode()
    assert 'hx-swap-oob="outerHTML"' in item_response.content.decode()

    items_refresh = client.get(
        reverse(
            "portal:client-order-project-item-create",
            kwargs={
                "customer_public_id": customer.public_id,
                "project_public_id": project.public_id,
            },
        ),
        HTTP_HX_REQUEST="true",
    )
    assert items_refresh.status_code == 200
    assert 'id="order-project-items"' in items_refresh.content.decode()

    project.refresh_from_db()
    assert project.status == B2BOrderProject.Status.INCOMPLETE
    item = project.items.get()
    assert item.name == "logo"
    assert item.asset is not None
    AssetAnalysisService().analyze(
        version_public_id=item.asset.current_version.public_id, source="test"
    )
    item.refresh_from_db()
    assert str(item.width_mm) == "10.16"
    assert str(item.height_mm) == "6.77"
    preview = client.get(
        reverse(
            "portal:client-order-project-item-asset-preview",
            kwargs={
                "customer_public_id": customer.public_id,
                "project_public_id": project.public_id,
                "item_public_id": item.public_id,
            },
        )
    )
    assert preview.status_code == 200
    assert preview["Content-Type"] == "image/webp"

    pdf_response = client.post(
        reverse(
            "portal:client-order-project-item-create",
            kwargs={
                "customer_public_id": customer.public_id,
                "project_public_id": project.public_id,
            },
        ),
        {"quantity": "1", "file": pdf_upload()},
        HTTP_HX_REQUEST="true",
    )
    assert pdf_response.status_code == 200
    pdf_item = project.items.get(name="document")
    assert str(pdf_item.width_mm) == "1.00"
    AssetAnalysisService().analyze(
        version_public_id=pdf_item.asset.current_version.public_id,
        source="test",
    )
    pdf_item.refresh_from_db()
    assert pdf_item.width_mm > 1
    assert pdf_item.height_mm > 1
    assert pdf_item.asset.current_version.analysis.thumbnail

    for project_item in project.items.all():
        confirm = client.post(
            reverse(
                "portal:client-order-project-item-action",
                kwargs={
                    "customer_public_id": customer.public_id,
                    "project_public_id": project.public_id,
                    "item_public_id": project_item.public_id,
                    "action": "confirm-analysis",
                },
            ),
            {
                "confirm_analysis": "on",
                "name": project_item.name,
                "width_mm": str(project_item.width_mm),
                "height_mm": str(project_item.height_mm),
                "quantity": str(project_item.quantity),
                "support_color_hex": "#AABBCC",
            },
            HTTP_HX_REQUEST="true",
        )
        assert confirm.status_code == 200
        assert "Validé" in confirm.content.decode()
        project_item.refresh_from_db()
        assert project_item.support_color_hex == "#aabbcc"

    other = Customer.objects.create(name="Autre portail", b2b_order_projects_enabled=True)
    CustomerMembership.objects.create(customer=other, user=user)
    hidden_preview = client.get(
        reverse(
            "portal:client-order-project-item-asset-preview",
            kwargs={
                "customer_public_id": other.public_id,
                "project_public_id": project.public_id,
                "item_public_id": item.public_id,
            },
        )
    )
    assert hidden_preview.status_code == 404
    project.refresh_from_db()
    assert project.status == B2BOrderProject.Status.READY_TO_SUBMIT
    submit = client.post(
        reverse(
            "portal:client-order-project-submit",
            kwargs={
                "customer_public_id": customer.public_id,
                "project_public_id": project.public_id,
            },
        )
    )
    assert submit.status_code == 302
    project.refresh_from_db()
    assert project.status == B2BOrderProject.Status.CONVERTED
    assert project.converted_order is not None
    order = project.converted_order
    assert order.status == "submitted"
    assert order.uploads.count() == project.items.count()
    assert str(order.public_id) in submit.url

    orders_list = client.get(
        reverse(
            "portal:client-order-list",
            kwargs={"customer_public_id": customer.public_id},
        )
    )
    assert orders_list.status_code == 200
    assert str(order.public_id) in orders_list.content.decode()


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_submit_before_validation_shows_action_required_message():
    from apps.b2b_order_projects.services import B2BOrderProjectService
    from apps.uploads.services.asset_analysis import AssetAnalysisService
    from apps.uploads.services.assets import AssetService

    user, customer, client = portal_scope()
    project = B2BOrderProjectService().create_project(
        customer=customer,
        actor=user,
        data={"name": "Soumission anticipée"},
        source="test",
    )
    item = B2BOrderProjectService().add_item(
        project=project,
        actor=user,
        data={"name": "Logo", "width_mm": 100, "height_mm": 50, "quantity": 1},
        source="test",
    )
    version = AssetService().attach_project_item_file(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        uploaded_file=png_upload(),
        source="test",
    )
    AssetAnalysisService().analyze(version_public_id=version.public_id, source="test")
    project.refresh_from_db()
    assert project.status == B2BOrderProject.Status.ACTION_REQUIRED

    submit_url = reverse(
        "portal:client-order-project-submit",
        kwargs={"customer_public_id": customer.public_id, "project_public_id": project.public_id},
    )

    response = client.post(submit_url)
    assert response.status_code == 302
    assert response.url.endswith("submit_error=action_required")

    detail = client.get(response.url)
    assert detail.status_code == 200
    assert "Validez les dimensions et le contrôle technique" in detail.content.decode()


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_new_order_uses_asynchronous_visual_flow_when_enabled():
    _user, customer, client = portal_scope()
    checkout_url = reverse(
        "portal:client-checkout",
        kwargs={"customer_public_id": customer.public_id},
    )
    create_url = reverse(
        "portal:client-order-project-create",
        kwargs={"customer_public_id": customer.public_id},
    )

    response = client.get(checkout_url)

    assert response.status_code == 302
    assert response.url == create_url
    create_page = client.get(response.url)
    assert create_page.status_code == 200
    assert "Nouvelle commande" in create_page.content.decode()

    replaced_endpoints = [
        ("portal:client-checkout-upload", "post"),
        ("portal:client-checkout-summary", "get"),
        ("portal:client-checkout-submit", "post"),
    ]
    for route_name, method in replaced_endpoints:
        legacy_url = reverse(
            route_name,
            kwargs={"customer_public_id": customer.public_id},
        )
        legacy_response = getattr(client, method)(legacy_url)
        assert legacy_response.status_code == 404


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_new_order_redirect_does_not_cross_customer_scope():
    _user, customer, client = portal_scope()
    other = Customer.objects.create(name="Sans accès", b2b_order_projects_enabled=True)

    response = client.get(
        reverse(
            "portal:client-checkout",
            kwargs={"customer_public_id": other.public_id},
        )
    )

    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_portal_cross_tenant_project_is_not_found():
    user, customer, client = portal_scope()
    other = Customer.objects.create(name="Secret", b2b_order_projects_enabled=True)
    project = B2BOrderProject.objects.create(
        customer=other,
        created_by=user,
        project_number="DTF-B2B-2026-999993",
        name="Secret",
    )
    response = client.get(
        reverse(
            "portal:client-order-project-detail",
            kwargs={
                "customer_public_id": customer.public_id,
                "project_public_id": project.public_id,
            },
        )
    )
    assert response.status_code == 404


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_staff_portal_project_queue_requires_permission():
    staff = get_user_model().objects.create_user(
        email="ops-projects@example.com", password="pass", is_staff=True
    )
    staff.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    client = Client()
    client.login(email=staff.email, password="pass")
    url = reverse("portal:staff-order-project-list")
    assert client.get(url).status_code == 403

    staff.user_permissions.add(Permission.objects.get(codename="view_b2borderproject"))
    response = client.get(url)
    assert response.status_code == 200
    assert b"Projets B2B transmis" in response.content


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_delete_confirmation_modal_is_rendered_on_project_list():
    _user, customer, client = portal_scope()
    project = B2BOrderProject.objects.create(
        customer=customer,
        project_number="DTF-B2B-2026-999986",
        name="Commande test",
    )
    response = client.get(
        reverse(
            "portal:client-order-project-list",
            kwargs={"customer_public_id": customer.public_id},
        )
    )
    content = response.content.decode()
    assert response.status_code == 200
    assert "Supprimer cette commande ?" in content
    assert "Supprimer définitivement" in content
    assert f'data-dialog-open="delete-project-dialog-{project.public_id}"' in content
    assert f'id="delete-project-dialog-{project.public_id}"' in content
    assert "onsubmit=" not in content
