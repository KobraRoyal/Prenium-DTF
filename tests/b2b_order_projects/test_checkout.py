import pytest
from apps.b2b_order_projects.models import B2BOrderProject
from apps.b2b_order_projects.services import (
    B2BOrderProjectCheckoutService,
    B2BOrderProjectService,
    ProjectDomainError,
)
from apps.customers.models import Customer, CustomerBillingProfile, CustomerMembership
from apps.gang_sheets.models import GangSheet
from apps.gang_sheets.services import GangSheetService
from apps.orders.models import Order
from apps.uploads.models import AssetAnalysis, AssetVersion
from apps.uploads.services.asset_analysis import AssetAnalysisService
from apps.uploads.services.assets import AssetService
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from .helpers import png_upload


def create_scope(email="checkout@example.com"):
    user = get_user_model().objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(name="Checkout client", b2b_order_projects_enabled=True)
    membership = CustomerMembership.objects.create(customer=customer, user=user)
    return user, customer, membership


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
@pytest.mark.parametrize("support_color", ["#112233", "#multicolor"])
def test_checkout_project_creates_submitted_order_with_uploads(support_color):
    user, customer, membership = create_scope()
    project_service = B2BOrderProjectService()
    project = project_service.create_project(
        customer=customer,
        actor=user,
        data={"name": "Collection été", "customer_comment": "Livraison rapide"},
        source="test",
    )
    item = project_service.add_item(
        project=project,
        actor=user,
        data={"name": "Logo", "width_mm": 120, "height_mm": 80, "quantity": 3},
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
    item.refresh_from_db()
    project_service.confirm_item_analysis(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        data={
            "quantity": item.quantity,
            "support_color_hex": support_color,
        },
        source="test",
    )
    project.refresh_from_db()
    assert project.status == B2BOrderProject.Status.READY_TO_SUBMIT
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    sheet = GangSheetService().create_sheet(
        project=project,
        actor=user,
        name="Planche validée avant checkout",
        source="test",
    )
    sheet.status = GangSheet.Status.VALIDATED
    sheet.save(update_fields=["status", "updated_at"])

    order = B2BOrderProjectCheckoutService().checkout_project(
        project=project,
        actor=user,
        customer_membership=membership,
        source="test",
    )

    project.refresh_from_db()
    assert project.status == B2BOrderProject.Status.CONVERTED
    assert project.converted_order_id == order.id
    assert project.submitted_at is not None
    assert order.status == Order.Status.SUBMITTED
    assert order.billing_mode == Order.BillingMode.DEFERRED
    assert order.uploads.count() == 1
    upload = order.uploads.get()
    assert upload.quantity == 3
    assert upload.width_mm == item.width_mm
    assert upload.height_mm == item.height_mm
    assert upload.support_color_hex == support_color
    assert upload.asset_version_id == version.id
    assert "Collection été" in order.customer_note
    sheet.refresh_from_db()
    assert sheet.order == order


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_checkout_of_validated_gang_sheet_keeps_the_generated_hd_pdf(settings):
    user, customer, membership = create_scope("gang-sheet-hd-checkout@example.com")
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    production_pdf = b"%PDF-1.4\n% server generated HD output\n%%EOF\n"
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Planche HD")
    sheet.status = GangSheet.Status.VALIDATED
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        production_pdf,
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "final_file", "updated_at"])
    project = GangSheetService().create_order_project(sheet=sheet, actor=user, source="test")
    item = project.items.get()
    version = item.asset.current_version
    AssetAnalysis.objects.create(
        customer=customer,
        version=version,
        image_width=638,
        image_height=2126,
        dpi_x="29.00",
        dpi_y="29.00",
        warnings=[],
        metadata={
            "thin_zone": {"detected": False},
            "semi_transparency": {"detected": False},
        },
    )
    version.analysis_status = AssetVersion.AnalysisStatus.READY
    version.save(update_fields=["analysis_status", "updated_at"])
    B2BOrderProjectService().confirm_item_analysis(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        data={
            "support_color_hex": "#multicolor",
            "quantity": "99",
            "width_mm": "10",
            "height_mm": "10",
        },
        source="test",
    )
    item.refresh_from_db()
    project.refresh_from_db()
    assert project.status == B2BOrderProject.Status.READY_TO_SUBMIT
    assert item.quantity == 1
    assert item.width_mm == sheet.width_mm
    assert item.height_mm == sheet.height_mm

    settings.GOOGLE_DRIVE_SYNC_ENABLED = True
    with pytest.raises(ProjectDomainError, match="Google Drive"):
        B2BOrderProjectCheckoutService().checkout_project(
            project=project,
            actor=user,
            customer_membership=membership,
            source="test",
        )
    assert Order.objects.filter(customer=customer).exists() is False
    settings.GOOGLE_DRIVE_SYNC_ENABLED = False

    order = B2BOrderProjectCheckoutService().checkout_project(
        project=project,
        actor=user,
        customer_membership=membership,
        source="test",
    )

    upload = order.uploads.get()
    sheet.refresh_from_db()
    assert upload.asset_version_id == version.id
    assert upload.file.name == version.file.name
    upload.file.open("rb")
    try:
        assert upload.file.read() == production_pdf
    finally:
        upload.file.close()
    assert sheet.order == order


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_checkout_recovers_legacy_submitted_project_without_order():
    user, customer, membership = create_scope("legacy-submit@example.com")
    project_service = B2BOrderProjectService()
    checkout_service = B2BOrderProjectCheckoutService()
    project = project_service.create_project(
        customer=customer,
        actor=user,
        data={"name": "Ancienne transmission"},
        source="test",
    )
    item = project_service.add_item(
        project=project,
        actor=user,
        data={"name": "Logo", "width_mm": 80, "height_mm": 80, "quantity": 2},
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
    project_service.confirm_item_analysis(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        data={"quantity": 2, "support_color_hex": "#112233"},
        source="test",
    )
    project = project_service.submit(project=project, actor=user, source="test")
    assert project.status == B2BOrderProject.Status.SUBMITTED
    assert project.converted_order is None

    order = checkout_service.checkout_project(
        project=project,
        actor=user,
        customer_membership=membership,
        source="test.recovery",
    )
    project.refresh_from_db()
    assert project.status == B2BOrderProject.Status.CONVERTED
    assert project.converted_order_id == order.id
    assert order.uploads.count() == 1


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_checkout_project_is_idempotent_when_already_converted():
    user, customer, membership = create_scope("checkout-idempotent@example.com")
    project_service = B2BOrderProjectService()
    checkout_service = B2BOrderProjectCheckoutService()
    project = project_service.create_project(
        customer=customer,
        actor=user,
        data={"name": "Idempotent"},
        source="test",
    )
    item = project_service.add_item(
        project=project,
        actor=user,
        data={"name": "Logo", "width_mm": 50, "height_mm": 50, "quantity": 1},
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
    project_service.confirm_item_analysis(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        data={"quantity": 1, "support_color_multicolor": "on"},
        source="test",
    )
    first_order = checkout_service.checkout_project(
        project=project,
        actor=user,
        customer_membership=membership,
        source="test",
    )
    second_order = checkout_service.checkout_project(
        project=project,
        actor=user,
        customer_membership=membership,
        source="test",
    )
    assert second_order.public_id == first_order.public_id
    assert Order.objects.filter(customer=customer).count() == 1
