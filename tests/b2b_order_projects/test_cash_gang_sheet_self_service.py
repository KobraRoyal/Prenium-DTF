from decimal import Decimal

import pytest
from apps.b2b_order_projects.models import B2BOrderProject
from apps.b2b_order_projects.permissions import customer_requires_gang_sheet_orders
from apps.b2b_order_projects.services import (
    B2BOrderProjectCheckoutService,
    B2BOrderProjectService,
    ProjectDomainError,
)
from apps.billing.services.production_payment_gate import (
    order_awaits_client_payment,
    requires_captured_payment_before_production,
)
from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerBillingProfile, CustomerMembership
from apps.gang_sheets.models import GangSheet
from apps.gang_sheets.services import GangSheetService
from apps.orders.models import Order
from apps.uploads.models import AssetAnalysis, AssetVersion
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse


def _seed_catalog():
    CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="20.00",
        currency="EUR",
        display_order=1,
    )
    CatalogService.objects.create(
        code="file-prep",
        name="Preparation fichier",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price="5.00",
        currency="EUR",
        display_order=2,
    )


def _prepare_gang_sheet_project(*, customer, user, surface_sqm="1.1000"):
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    production_pdf = b"%PDF-1.4\n% self-service pricing\n%%EOF\n"
    sheet = GangSheetService().create_sheet(
        customer=customer,
        actor=user,
        name="Planche comptant",
    )
    sheet.status = GangSheet.Status.VALIDATED
    sheet.surface_sqm = Decimal(surface_sqm)
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        production_pdf,
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "surface_sqm", "final_file", "updated_at"])
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
        data={"support_color_hex": "#112233"},
        source="test",
    )
    project.refresh_from_db()
    sheet.refresh_from_db()
    return project, sheet


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_immediate_account_checkout_auto_prices_from_gang_sheet():
    _seed_catalog()
    user = get_user_model().objects.create_user(email="cash@example.com", password="pass")
    customer = Customer.objects.create(
        name="Cash Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    membership = CustomerMembership.objects.create(customer=customer, user=user)
    assert customer_requires_gang_sheet_orders(customer) is True

    project, sheet = _prepare_gang_sheet_project(customer=customer, user=user, surface_sqm="1.1000")
    assert project.order_mode == B2BOrderProject.OrderMode.READY_GANG_SHEET
    item = project.items.get()
    item.quantity = 3
    item.save(update_fields=["quantity", "updated_at"])

    order = B2BOrderProjectCheckoutService().checkout_project(
        project=project,
        actor=user,
        customer_membership=membership,
        source="test",
        billing_mode="immediate",
    )

    assert order.billing_mode == Order.BillingMode.IMMEDIATE
    assert order.pricing_status == Order.PricingStatus.PRICED
    # 1.1 m² × 3 ex. × 25 € + 5 € préparation fichier
    assert order.total_amount == Decimal("87.50")
    assert order.uses_atelier_pricing() is True
    assert requires_captured_payment_before_production(order) is True
    assert order_awaits_client_payment(order) is True
    upload = order.uploads.get()
    assert upload.quantity == 3
    assert upload.meterage_override_sqm == Decimal("3.3000")
    sheet.refresh_from_db()
    assert sheet.order_id == order.id


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_gang_sheet_quote_is_available_before_transmit():
    _seed_catalog()
    user = get_user_model().objects.create_user(email="quote@example.com", password="pass")
    customer = Customer.objects.create(
        name="Quote Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    project, _sheet = _prepare_gang_sheet_project(
        customer=customer,
        user=user,
        surface_sqm="1.1000",
    )
    item = project.items.get()
    item.quantity = 2
    item.save(update_fields=["quantity", "updated_at"])

    from apps.orders.services.pricing import OrderPricingService

    quote = OrderPricingService().estimate_gang_sheet_quote(
        customer=customer,
        surface_sqm="1.1000",
        quantity=2,
    )
    assert quote["billable_sqm"] == Decimal("2.2000")
    assert quote["total_eur"] == Decimal("60.00")  # 2.2×25 + 5

    client = Client()
    assert client.login(email="quote@example.com", password="pass")
    response = client.get(
        reverse(
            "portal:client-order-project-detail",
            kwargs={
                "customer_public_id": customer.public_id,
                "project_public_id": project.public_id,
            },
        )
    )
    assert response.status_code == 200
    body = response.content.decode()
    page_quote = response.context["gang_sheet_quote"]
    assert page_quote is not None
    assert page_quote["total_eur"] == Decimal("60.00")
    assert "Total HT" in body
    assert "Confirmer et payer" in body
    assert "Mode de règlement" not in body
    assert "60,00" in body or "60.00" in body


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_create_order_project_accepts_sheet_quantity():
    _seed_catalog()
    user = get_user_model().objects.create_user(email="qty@example.com", password="pass")
    customer = Customer.objects.create(
        name="Qty Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    production_pdf = b"%PDF-1.4\n% qty\n%%EOF\n"
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Planche qty")
    sheet.status = GangSheet.Status.VALIDATED
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        production_pdf,
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "final_file", "updated_at"])

    project = GangSheetService().create_order_project(
        sheet=sheet,
        actor=user,
        source="test",
        quantity=4,
    )
    assert project.items.get().quantity == 4


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_immediate_account_cannot_create_individual_designs_project():
    user = get_user_model().objects.create_user(email="cash2@example.com", password="pass")
    customer = Customer.objects.create(
        name="Cash Co 2",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    with pytest.raises(ProjectDomainError, match="Gang Sheet"):
        B2BOrderProjectService().create_project(
            customer=customer,
            actor=user,
            data={"name": "Fichiers libres"},
            source="test",
        )


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_immediate_account_create_view_redirects_to_gang_sheets():
    user = get_user_model().objects.create_user(email="cash3@example.com", password="pass")
    customer = Customer.objects.create(
        name="Cash Co 3",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    client = Client()
    assert client.login(email="cash3@example.com", password="pass")
    response = client.get(
        reverse(
            "portal:client-order-project-create",
            kwargs={"customer_public_id": customer.public_id},
        )
    )
    assert response.status_code == 302
    assert reverse(
        "portal:client-gang-sheet-list-create",
        kwargs={"customer_public_id": customer.public_id},
    ) in response["Location"]


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_deferred_checkout_still_waits_for_atelier_pricing():
    _seed_catalog()
    user = get_user_model().objects.create_user(email="deferred@example.com", password="pass")
    customer = Customer.objects.create(
        name="Deferred Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.DEFERRED,
    )
    membership = CustomerMembership.objects.create(customer=customer, user=user)
    project, _sheet = _prepare_gang_sheet_project(customer=customer, user=user)

    order = B2BOrderProjectCheckoutService().checkout_project(
        project=project,
        actor=user,
        customer_membership=membership,
        source="test",
        billing_mode="deferred",
    )

    assert order.billing_mode == Order.BillingMode.DEFERRED
    assert order.pricing_status == Order.PricingStatus.PENDING
    assert order.total_amount == Decimal("0.00")
