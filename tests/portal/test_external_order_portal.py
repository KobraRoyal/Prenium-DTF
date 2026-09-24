from decimal import Decimal
from unittest.mock import patch

import pytest
from apps.accounts.models import StaffMembership
from apps.accounts.services.staff_roles import sync_staff_access
from apps.auditlog.models import AuditLogEntry
from apps.billing.services.production_payment_gate import production_start_blocked_reason
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.orders.services.external_orders import ExternalOrderService
from apps.orders.services.pricing import OrderPricingService
from apps.production.services.manufacturing_order_pdf import render_manufacturing_order_pdf_bytes
from apps.production.services.workflow import ProductionWorkflowService
from apps.uploads.models import OrderUploadDriveSync, OrderUploadInspection, OrderUploadReview
from apps.uploads.services.uploads import OrderUploadService
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from tests.orders.test_order_pricing_service import _seed_catalog_dtf_and_file_prep

pytestmark = pytest.mark.django_db


@pytest.fixture
def scope():
    customer = Customer.objects.create(name="Client lien")
    user = get_user_model().objects.create_user(email="link-client@example.com", password="pass")
    CustomerMembership.objects.create(customer=customer, user=user, role="owner")
    client = Client()
    client.force_login(user)
    staff = get_user_model().objects.create_user(email="link-admin@example.com", password="pass")
    StaffMembership.objects.create(user=staff, role="admin")
    sync_staff_access(user=staff, role="admin", is_active=True)
    admin = Client()
    admin.force_login(staff)
    return customer, user, client, staff, admin


def client_url(customer):
    return reverse("portal:client-external-order-create", args=[customer.public_id])


def payload(**extra):
    return {
        "name": "Affiche grand format",
        "external_url": "https://example.com/design?token=private",
        **({"external_visual_count": "1"} if "customer" in extra else {}),
        **extra,
    }


@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_project_form_has_one_shared_information_card(scope):
    customer, _user, client, _staff, _admin = scope
    page = client.get(reverse("portal:client-order-project-create", args=[customer.public_id]))
    html = page.content.decode()
    assert html.count('name="name"') == 1
    assert html.count('name="customer_comment"') == 1
    assert 'name="customer_note"' not in html
    card = html.split('<section class="portal-page-surface b2b-order-start-surface">')[1]
    card = card.split("</section>")[0]
    form = card.split("<form")[1].split("</form>")[0]
    assert 'name="name"' in form
    assert 'name="external_url"' in form


@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_project_form_link_reuses_name_date_and_comment_without_project(scope):
    from apps.b2b_order_projects.models import B2BOrderProject

    customer, user, client, _staff, _admin = scope
    response = client.post(
        reverse("portal:client-order-project-create", args=[customer.public_id]),
        payload(
            source="external_link",
            customer_comment="Consignes uniques",
            requested_date="2026-10-15",
        ),
    )
    assert response.status_code == 302
    order = Order.objects.get(customer=customer)
    assert order.created_by == user
    assert order.uploads.get().original_filename == "Affiche grand format"
    assert order.customer_note == (
        "Affiche grand format\nDate souhaitée : 15/10/2026\nConsignes uniques"
    )
    detail = client.get(response.url)
    assert detail.status_code == 200
    from apps.portal.client_order_presentation import client_order_identity

    identity = client_order_identity(order)
    assert identity.label == "Affiche grand format"
    assert identity.note == "Date souhaitée : 15/10/2026\nConsignes uniques"
    assert order.uploads.get().is_external
    assert not B2BOrderProject.objects.exists()


@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
@pytest.mark.parametrize("external_url", ["", "http://127.0.0.1/file", "javascript:alert(1)"])
def test_integrated_link_errors_keep_shared_information(scope, external_url):
    customer, _user, client, _staff, _admin = scope
    response = client.post(
        reverse("portal:client-order-project-create", args=[customer.public_id]),
        payload(
            source="external_link",
            external_url=external_url,
            customer_comment="Consignes uniques",
            requested_date="2026-10-15",
        ),
    )
    assert response.status_code == 400
    html = response.content.decode()
    assert "Informations de commande" in html
    assert "Consignes uniques" in html
    assert "2026-10-15" in html
    assert 'id="external-url-error"' in html
    assert not Order.objects.exists()


@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_integrated_link_preserves_customer_scope(scope):
    _customer, _user, client, _staff, _admin = scope
    other = Customer.objects.create(name="Other")
    response = client.post(
        reverse("portal:client-order-project-create", args=[other.public_id]), payload()
    )
    assert response.status_code in {403, 404}
    assert not Order.objects.exists()


@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_client_creates_external_order_without_file_or_meterage(scope):
    customer, user, client, _staff, _admin = scope
    page = client.get(reverse("portal:client-order-project-create", args=[customer.public_id]))
    assert page.status_code == 200
    assert 'name="external_url"' in page.content.decode()
    response = client.post(
        client_url(customer),
        payload(meterage_linear_m="1", external_visual_count="8", customer_note="Urgent"),
    )
    assert response.status_code == 302
    order = Order.objects.get(customer=customer)
    assert order.status == Order.Status.SUBMITTED
    assert order.pricing_status == Order.PricingStatus.PENDING
    assert order.meterage_override_linear_m is None
    assert order.created_by == user
    assert not OrderUploadInspection.objects.exists()
    assert not OrderUploadDriveSync.objects.exists()
    upload = order.uploads.get()
    assert upload.external_visual_count == 1
    assert not upload.file
    details = client.get(response.url)
    assert details.status_code == 200
    panel = client.get(
        reverse("portal:client-order-panel-uploads", args=[customer.public_id, order.public_id])
    )
    html = panel.content.decode()
    assert panel.status_code == 200
    assert "Ouvrir le lien client" in html
    assert "no-referrer" in html
    assert (
        reverse(
            "portal:client-order-upload-preview",
            args=[customer.public_id, order.public_id, upload.public_id],
        )
        not in html
    )
    for route in ("portal:client-order-upload-preview", "portal:client-order-upload-download"):
        assert (
            client.get(
                reverse(route, args=[customer.public_id, order.public_id, upload.public_id])
            ).status_code
            == 404
        )


@pytest.mark.parametrize(
    "invalid",
    ["javascript:alert(1)", "https://127.0.0.1/file", "https://user:password@example.com/file"],
)
def test_invalid_url_preserves_form_and_creates_nothing(scope, invalid):
    customer, _user, client, _staff, _admin = scope
    response = client.post(client_url(customer), payload(external_url=invalid))
    assert response.status_code == 400
    assert "Affiche grand format" in response.content.decode()
    assert not Order.objects.exists()


def test_client_cannot_create_for_another_customer_or_use_staff_form(scope):
    customer, _user, client, _staff, _admin = scope
    other = Customer.objects.create(name="Autre client")
    assert client.post(client_url(other), payload()).status_code in {403, 404}
    staff_url = reverse("portal:staff-external-order-create")
    assert client.get(staff_url).status_code == 403
    assert (
        client.post(
            staff_url, payload(customer=str(customer.public_id), meterage_linear_m="3")
        ).status_code
        == 403
    )
    assert not Order.objects.exists()


def test_staff_creates_priced_order_for_customer_without_impersonation(scope):
    customer, _user, _client, staff, admin = scope
    _seed_catalog_dtf_and_file_prep()
    url = reverse("portal:staff-external-order-create")
    form = admin.get(url)
    assert form.status_code == 200
    assert f'value="{customer.public_id}"' in form.content.decode()
    assert 'name="external_visual_count"' in form.content.decode()
    assert 'name="shipping_method_code"' in form.content.decode()
    assert 'name="support_color_hex"' in form.content.decode()
    assert 'name="support_color_multicolor"' in form.content.decode()
    response = admin.post(
        url,
        payload(
            customer=str(customer.public_id),
            meterage_linear_m="2.5",
            external_visual_count="3",
            shipping_method_code="standard",
            support_color_hex="#112233",
        ),
    )
    assert response.status_code == 302
    order = Order.objects.get(customer=customer)
    assert order.created_by == staff
    assert order.pricing_status == Order.PricingStatus.PRICED
    assert order.meterage_override_linear_m == Decimal("2.5")
    assert order.shipping_method_code == "standard"
    assert order.uploads.get().external_visual_count == 3
    assert order.uploads.get().support_color_hex == "#112233"
    assert order.items.get(service_type="file_preparation").quantity == 3
    from apps.orders.references import order_business_number

    assert order_business_number(order).startswith("CMD-")
    assert not CustomerMembership.objects.filter(user=staff).exists()
    assert admin.get(response.url).status_code == 200
    for panel_name in ("uploads", "inspection", "drive-sync", "production", "billing"):
        panel = admin.get(reverse(f"portal:staff-order-panel-{panel_name}", args=[order.public_id]))
        assert panel.status_code == 200
        if panel_name == "inspection":
            assert "Non applicable" in panel.content.decode()
        if panel_name == "drive-sync":
            assert "Aucun incident Drive" in panel.content.decode()
    with patch(
        "apps.uploads.services.asset_preview.AssetPreviewRenderer.render",
        side_effect=AssertionError("No preview for links"),
    ):
        pdf = render_manufacturing_order_pdf_bytes(order=order, production_job=order.production_job)
    assert pdf.startswith(b"%PDF")


@pytest.mark.parametrize(
    "route", ["portal:staff-order-panel-billing", "portal:staff-atelier-operation-meterage"]
)
def test_atelier_can_price_client_link_with_meterage_and_visual_count(scope, route):
    customer, user, _client, _staff, admin = scope
    _seed_catalog_dtf_and_file_prep()
    order = ExternalOrderService().create_client_order(customer=customer, actor=user, **payload())
    panel = admin.get(reverse("portal:staff-order-panel-production", args=[order.public_id]))
    assert 'name="external_visual_count"' in panel.content.decode()
    job = order.production_job
    early_console = admin.get(
        reverse("portal:staff-atelier-operations"),
        {"q": job.manufacturing_order_number},
    )
    assert not job.of_document_issued_at
    assert early_console.status_code == 200
    assert 'name="external_visual_count"' in early_console.content.decode()
    assert "Nombre de fichiers dans le lien" in early_console.content.decode()
    assert 'name="order_meterage_override_linear_m"' not in early_console.content.decode()
    count_response = admin.post(
        reverse("portal:staff-atelier-operation-external-count", args=[order.public_id]),
        {"external_visual_count": "4", "order_meterage_override_linear_m": "999"},
        HTTP_HX_REQUEST="true",
    )
    assert count_response.status_code == 200
    order.refresh_from_db()
    assert order.uploads.get().external_visual_count == 4
    assert order.meterage_override_linear_m is None
    assert order.pricing_status == Order.PricingStatus.PENDING
    assert not order.items.exists()
    assert 'name="order_meterage_override_linear_m"' not in count_response.content.decode()
    job.of_document_issued_at = timezone.now()
    job.save(update_fields=["of_document_issued_at"])
    OrderUploadReview.objects.create(order_upload=order.uploads.get(), status="approved")
    console = admin.get(
        reverse("portal:staff-atelier-operations"),
        {"q": order.production_job.manufacturing_order_number},
    )
    assert 'name="external_visual_count"' not in console.content.decode()
    assert 'name="order_meterage_override_linear_m"' in console.content.decode()
    response = admin.post(
        reverse(route, args=[order.public_id]),
        {"order_meterage_override_linear_m": "2.5"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    order.refresh_from_db()
    assert order.pricing_status == Order.PricingStatus.PRICED
    assert order.meterage_override_linear_m == Decimal("2.5")
    assert order.uploads.get().external_visual_count == 4
    assert order.items.get(service_type="file_preparation").quantity == 4
    priced_console = admin.get(
        reverse("portal:staff-atelier-operations"),
        {"q": job.manufacturing_order_number},
    )
    assert 'name="external_visual_count"' not in priced_console.content.decode()
    assert 'name="order_meterage_override_linear_m"' not in priced_console.content.decode()


@pytest.mark.parametrize("role", ["member", "readonly"])
def test_staff_without_creation_permission_is_denied(scope, role):
    customer, _user, _client, staff, admin = scope
    sync_staff_access(user=staff, role=role, is_active=True)
    url = reverse("portal:staff-external-order-create")
    assert admin.get(url).status_code == 403
    assert (
        admin.post(
            url, payload(customer=str(customer.public_id), meterage_linear_m="1")
        ).status_code
        == 403
    )
    assert not Order.objects.exists()


@pytest.mark.parametrize("value", ["0", "10001", "abc", ""])
def test_control_step_rejects_invalid_file_count(scope, value):
    customer, user, _client, _staff, admin = scope
    order = ExternalOrderService().create_client_order(customer=customer, actor=user, **payload())
    response = admin.post(
        reverse("portal:staff-atelier-operation-external-count", args=[order.public_id]),
        {"external_visual_count": value},
    )
    assert response.status_code == 200
    assert "alert--danger" in response.content.decode()
    order.refresh_from_db()
    assert order.uploads.get().external_visual_count == 1
    assert order.meterage_override_linear_m is None
    assert order.pricing_status == Order.PricingStatus.PENDING


def test_control_step_count_requires_staff_change_permission(scope):
    customer, user, client, staff, admin = scope
    order = ExternalOrderService().create_client_order(customer=customer, actor=user, **payload())
    url = reverse("portal:staff-atelier-operation-external-count", args=[order.public_id])
    assert client.post(url, {"external_visual_count": "5"}).status_code == 403
    staff.user_permissions.remove(Permission.objects.get(codename="change_order"))
    assert admin.post(url, {"external_visual_count": "5"}).status_code == 403
    assert order.uploads.get().external_visual_count == 1


def test_external_link_remains_customer_scoped(scope):
    customer, user, client, _staff, _admin = scope
    other = Customer.objects.create(name="Autre")
    other_user = get_user_model().objects.create_user(
        email="other-link@example.com", password="pass"
    )
    CustomerMembership.objects.create(customer=other, user=other_user)
    order = ExternalOrderService().create_client_order(
        customer=other, actor=other_user, **payload()
    )
    for route in ("portal:client-order-detail", "portal:client-order-panel-uploads"):
        assert (
            client.get(reverse(route, args=[customer.public_id, order.public_id])).status_code
            == 404
        )
    assert order.created_by != user


@pytest.mark.parametrize("meterage", ["0", "-1", "NaN", "Infinity", "100000000"])
def test_staff_rejects_invalid_meterage_before_mutation(scope, meterage):
    customer, _user, _client, _staff, admin = scope
    response = admin.post(
        reverse("portal:staff-external-order-create"),
        payload(
            customer=str(customer.public_id),
            meterage_linear_m=meterage,
            shipping_method_code="standard",
        ),
    )
    assert response.status_code == 400
    assert not Order.objects.exists()


def test_staff_creates_order_without_meterage_for_later_pricing(scope):
    customer, _user, _client, staff, admin = scope
    response = admin.post(
        reverse("portal:staff-external-order-create"),
        payload(
            customer=str(customer.public_id),
            meterage_linear_m="",
            shipping_method_code="pickup",
        ),
    )
    assert response.status_code == 302
    order = Order.objects.get(customer=customer)
    assert order.created_by == staff
    assert order.meterage_override_linear_m is None
    assert order.pricing_status == Order.PricingStatus.PENDING
    assert order.shipping_method_code == "pickup"
    from apps.orders.references import order_business_number

    assert order_business_number(order).startswith("CMD-")


def test_staff_cannot_select_inactive_customer(scope):
    customer, _user, _client, _staff, admin = scope
    customer.is_active = False
    customer.save(update_fields=["is_active"])
    response = admin.post(
        reverse("portal:staff-external-order-create"),
        payload(
            customer=str(customer.public_id),
            meterage_linear_m="3",
            shipping_method_code="standard",
        ),
    )
    assert response.status_code == 400
    assert not Order.objects.exists()


def test_csrf_required_for_external_order(scope):
    customer, user, _client, staff, _admin = scope
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    assert client.post(client_url(customer), payload()).status_code == 403
    client.force_login(staff)
    assert (
        client.post(
            reverse("portal:staff-external-order-create"),
            payload(customer=str(customer.public_id), meterage_linear_m="3"),
        ).status_code
        == 403
    )


def test_production_and_inspection_permissions_do_not_disclose_file_link(scope):
    customer, user, _client, staff, admin = scope
    order = ExternalOrderService().create_client_order(customer=customer, actor=user, **payload())
    staff.user_permissions.remove(
        Permission.objects.get(content_type__app_label="uploads", codename="view_orderupload")
    )
    response = admin.get(reverse("portal:staff-order-panel-inspection", args=[order.public_id]))
    assert response.status_code == 200
    assert "example.com/design" not in response.content.decode()
    api = admin.get(reverse("production:staff-production-job-detail", args=[order.public_id]))
    assert api.status_code == 200
    assert "external_url" not in api.content.decode()
    assert "token=private" not in api.content.decode()
    console = admin.get(
        reverse("portal:staff-atelier-operations"),
        {
            "q": order.production_job.manufacturing_order_number,
        },
    )
    assert console.status_code == 200
    assert "token=private" not in console.content.decode()
    assert (
        reverse(
            "portal:staff-external-upload-link",
            args=[
                order.public_id,
                order.uploads.get().public_id,
            ],
        )
        not in console.content.decode()
    )
    pdf = render_manufacturing_order_pdf_bytes(order=order, production_job=order.production_job)
    assert pdf.startswith(b"%PDF")
    assert b"/URI" not in pdf
    assert (
        admin.get(reverse("portal:staff-order-panel-uploads", args=[order.public_id])).status_code
        == 403
    )


def test_external_link_opening_is_scoped_and_audited_without_url(scope):
    customer, user, client, staff, admin = scope
    order = ExternalOrderService().create_client_order(customer=customer, actor=user, **payload())
    upload = order.uploads.get()
    client_link = reverse(
        "portal:client-external-upload-link",
        args=[customer.public_id, order.public_id, upload.public_id],
    )
    response = client.get(client_link)
    assert response.status_code == 302
    assert response.url == upload.external_url
    assert response["Referrer-Policy"] == "no-referrer"
    assert "no-store" in response["Cache-Control"]
    audit = AuditLogEntry.objects.get(action="order_upload.external_link_opened")
    assert "token" not in str(audit.metadata)
    staff_link = reverse(
        "portal:staff-external-upload-link", args=[order.public_id, upload.public_id]
    )
    assert admin.get(staff_link).status_code == 302
    staff.user_permissions.remove(
        Permission.objects.get(content_type__app_label="uploads", codename="view_orderupload")
    )
    assert admin.get(staff_link).status_code == 403
    assert client.get(staff_link).status_code == 403
    other = Customer.objects.create(name="Other link tenant")
    CustomerMembership.objects.create(customer=other, user=user)
    assert (
        client.get(
            reverse(
                "portal:client-external-upload-link",
                args=[other.public_id, order.public_id, upload.public_id],
            )
        ).status_code
        == 404
    )


def test_external_order_requires_meterage_price_and_manual_review_before_production(scope):
    customer, user, _client, staff, _admin = scope
    _seed_catalog_dtf_and_file_prep()
    order = ExternalOrderService().create_client_order(customer=customer, actor=user, **payload())
    workflow = ProductionWorkflowService()
    assert "métrage" in production_start_blocked_reason(order)
    with pytest.raises(ValidationError, match="métrage"):
        workflow.transition_existing_job(
            production_job=order.production_job,
            actor=staff,
            source="test",
            to_status="in_progress",
            reason="",
        )
    OrderUploadService().set_staff_order_meterage_linear_override(
        order=order, actor=staff, raw_value="2.5"
    )
    OrderPricingService().compute_and_persist_order_pricing(order=order, actor=staff, source="test")
    order.refresh_from_db()
    assert "contrôle manuel" in production_start_blocked_reason(order)
    OrderUploadReview.objects.create(order_upload=order.uploads.get(), status="approved")
    assert production_start_blocked_reason(order) is None
    job, _transition = workflow.transition_existing_job(
        production_job=order.production_job,
        actor=staff,
        source="test",
        to_status="in_progress",
        reason="",
    )
    assert job.status == "in_progress"
