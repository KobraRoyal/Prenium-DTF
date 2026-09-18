import hashlib
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from apps.b2b_order_projects.models import B2BOrderProject
from apps.b2b_order_projects.permissions import customer_requires_gang_sheet_orders
from apps.b2b_order_projects.services import (
    B2BOrderProjectCheckoutService,
    B2BOrderProjectService,
    ProjectDomainError,
)
from apps.billing.models import Payment, PaymentGatewaySettings
from apps.billing.services.production_payment_gate import (
    order_awaits_client_payment,
    requires_captured_payment_before_production,
)
from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerBillingProfile, CustomerMembership
from apps.gang_sheets.models import GangSheet, GangSheetItem, GangSheetSourceAsset
from apps.gang_sheets.services import GangSheetService
from apps.gang_sheets.services import gang_sheets as gang_sheets_module
from apps.orders.models import Order
from apps.shipping.services.methods import ShippingMethodService
from apps.uploads.models import Asset, AssetAnalysis, AssetVersion
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse

from .helpers import png_upload


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


def _add_placed_ready_visual(*, sheet, user, name="logo-planche.png"):
    customer = sheet.customer
    uploaded = png_upload(name)
    content = uploaded.read()
    asset = Asset.objects.create(customer=customer, created_by=user, name=name)
    version = AssetVersion.objects.create(
        customer=customer,
        asset=asset,
        uploaded_by=user,
        version_number=1,
        file=SimpleUploadedFile(name, content, content_type="image/png"),
        original_filename=name,
        mime_type="image/png",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        analysis_status=AssetVersion.AnalysisStatus.READY,
    )
    asset.current_version = version
    asset.save(update_fields=["current_version", "updated_at"])
    AssetAnalysis.objects.create(
        customer=customer,
        version=version,
        image_width=120,
        image_height=80,
        dpi_x="300.00",
        dpi_y="300.00",
        warnings=[],
        metadata={"thin_zone": {"detected": False}, "semi_transparency": {"detected": False}},
    )
    GangSheetSourceAsset.objects.create(
        customer=customer,
        sheet=sheet,
        asset=asset,
        added_by=user,
        width_mm="40.00",
        height_mm="20.00",
    )
    GangSheetItem.objects.create(
        customer=customer,
        sheet=sheet,
        asset_version=version,
        x_mm="5.00",
        y_mm="5.00",
        width_mm="40.00",
        height_mm="20.00",
        rotation=0,
        z_index=1,
    )
    return asset


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_immediate_account_checkout_auto_prices_from_gang_sheet():
    _seed_catalog()
    user = get_user_model().objects.create_user(email="cash@example.com", password="pass")
    customer = Customer.objects.create(
        name="Cash Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
        default_shipping_mode=Customer.DefaultShippingMode.PICKUP,
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
        shipping_method_code="pickup",
    )

    assert order.billing_mode == Order.BillingMode.IMMEDIATE
    assert order.pricing_status == Order.PricingStatus.PRICED
    # 1.1 m² × 3 ex. × 25 € + 5 € préparation = 87.50 HT ; retrait ; TVA 20 % → 105.00 TTC
    assert order.subtotal_amount == Decimal("87.50")
    assert order.shipping_amount == Decimal("0.00")
    assert order.tax_amount == Decimal("17.50")
    assert order.total_amount == Decimal("105.00")
    assert order.shipping_method_code == "pickup"
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
        default_shipping_mode=Customer.DefaultShippingMode.PICKUP,
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
        shipping_method_code="pickup",
        billing_mode="immediate",
    )
    assert quote["billable_sqm"] == Decimal("2.2000")
    assert quote["subtotal_eur"] == Decimal("60.00")  # 2.2×25 + 5
    assert quote["shipping_amount_eur"] == Decimal("0.00")
    assert quote["tax_amount_eur"] == Decimal("12.00")
    assert quote["total_eur"] == Decimal("72.00")

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
    assert page_quote["total_eur"] == Decimal("72.00")
    assert "TTC" in body
    assert "Total TTC" not in body
    assert "TVA" in body
    assert "Confirmer et payer" in body
    assert "Mode de règlement" not in body
    assert "Retrait atelier" in body
    assert "72,00" in body or "72.00" in body


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_validated_sheet_editor_shows_inline_checkout_for_cash_client():
    user = get_user_model().objects.create_user(email="cash-cta@example.com", password="pass")
    customer = Customer.objects.create(
        name="Cash CTA Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Planche CTA")
    _add_placed_ready_visual(sheet=sheet, user=user, name="logo-planche.png")
    sheet.status = GangSheet.Status.VALIDATED
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        b"%PDF-1.4\n% cta\n%%EOF\n",
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "final_file", "updated_at"])

    client = Client()
    assert client.login(email="cash-cta@example.com", password="pass")
    response = client.get(
        reverse(
            "portal:client-gang-sheet-editor",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        )
    )
    assert response.status_code == 200
    content = response.content.decode()
    checkout_url = reverse(
        "portal:client-gang-sheet-checkout",
        kwargs={
            "customer_public_id": customer.public_id,
            "sheet_public_id": sheet.public_id,
        },
    )
    assert "data-studio-checkout" in content
    assert checkout_url in content
    assert "data-studio-checkout-submit" in content
    assert "Je commande" in content
    assert "Couleur du support" in content
    assert "is-checkout" in content
    assert "Nom de la commande" in content
    assert 'name="requested_date"' in content
    assert 'name="customer_comment"' in content
    assert "confirm_sheet_files" not in content
    assert "Je confirme ce visuel" not in content
    assert "Continuer vers la commande" not in content
    assert "data-create-order-project" not in content


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_studio_editor_shows_detailed_pay_quote_and_json_endpoint():
    _seed_catalog()
    user = get_user_model().objects.create_user(email="studio-quote@example.com", password="pass")
    customer = Customer.objects.create(
        name="Studio Quote Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
        default_shipping_mode=Customer.DefaultShippingMode.CARRIER,
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Planche devis")
    _add_placed_ready_visual(sheet=sheet, user=user, name="visuel-devis.png")
    sheet.status = GangSheet.Status.VALIDATED
    sheet.surface_sqm = Decimal("1.1000")
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        b"%PDF-1.4\n% quote\n%%EOF\n",
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "surface_sqm", "final_file", "updated_at"])

    client = Client()
    assert client.login(email="studio-quote@example.com", password="pass")
    kwargs = {
        "customer_public_id": customer.public_id,
        "sheet_public_id": sheet.public_id,
    }
    editor = client.get(reverse("portal:client-gang-sheet-editor", kwargs=kwargs))
    assert editor.status_code == 200
    body = editor.content.decode()
    quote_url = reverse("portal:client-gang-sheet-quote", kwargs=kwargs)
    assert quote_url in body
    assert "data-studio-pay-quote" in body
    assert "Impression DTF" in body
    assert "TVA" in body
    assert "b2b-shipping-choice__input" in body
    page_quote = editor.context["gang_sheet_quote"]
    assert page_quote is not None
    assert page_quote["total_eur"] > 0
    assert page_quote["goods_total_eur"] > 0
    assert "Je commande" in body
    assert "Livraison à choisir" in body
    assert "data-studio-order-recap" in body
    inspector = body.split("data-studio-pay-quote", 1)[1].split("data-studio-pay-dialog", 1)[0]
    assert "Livraison standard" not in inspector
    assert "data-studio-pay-shipping" not in inspector

    pickup = client.get(quote_url, {"quantity": "1", "shipping_method_code": "pickup"})
    standard = client.get(quote_url, {"quantity": "1", "shipping_method_code": "standard"})
    assert pickup.status_code == 200
    assert standard.status_code == 200
    pickup_payload = pickup.json()
    standard_payload = standard.json()
    assert pickup_payload["ok"] is True
    assert standard_payload["ok"] is True
    assert pickup_payload["quote"]["shipping_method_code"] == "pickup"
    assert Decimal(pickup_payload["quote"]["shipping_amount_eur"]) == Decimal("0.00")
    assert Decimal(standard_payload["quote"]["shipping_amount_eur"]) > Decimal("0.00")
    assert Decimal(standard_payload["quote"]["total_eur"]) > Decimal(
        pickup_payload["quote"]["total_eur"]
    )
    assert Decimal(standard_payload["quote"]["goods_total_eur"]) == Decimal(
        pickup_payload["quote"]["goods_total_eur"]
    )
    assert "tax_amount_eur" in standard_payload["quote"]
    assert "goods_total_eur" in standard_payload["quote"]

    other = get_user_model().objects.create_user(
        email="studio-quote-other@example.com",
        password="pass",
    )
    other_customer = Customer.objects.create(
        name="Studio Quote Other",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    CustomerMembership.objects.create(customer=other_customer, user=other)
    other_client = Client()
    assert other_client.login(email="studio-quote-other@example.com", password="pass")
    blocked = other_client.get(quote_url)
    assert blocked.status_code == 403


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_draft_sheet_editor_hides_inline_checkout():
    user = get_user_model().objects.create_user(email="draft-cta@example.com", password="pass")
    customer = Customer.objects.create(
        name="Draft CTA Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Planche draft")

    client = Client()
    assert client.login(email="draft-cta@example.com", password="pass")
    response = client.get(
        reverse(
            "portal:client-gang-sheet-editor",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        )
    )
    assert response.status_code == 200
    content = response.content.decode()
    checkout_chunk = content.split("data-studio-checkout", 1)[1].split("</section>", 1)[0]
    assert "hidden" in checkout_chunk
    assert "data-studio-checkout-submit" in checkout_chunk
    assert "Je commande" in checkout_chunk


def test_studio_checkout_lock_avoids_postgres_nullable_outer_join():
    source = Path(gang_sheets_module.__file__).read_text(encoding="utf-8")
    checkout = source.split("def checkout_studio_sheet", 1)[1].split("    def ", 1)[0]
    assert 'select_related("project", "order")' in checkout
    assert 'select_for_update(of=("self",))' in checkout
    assert "select_for_update().select_related" not in checkout


def test_studio_checkout_payment_source_fits_payment_field():
    source = "client_portal.studio_checkout_pay"
    max_length = Payment._meta.get_field("source").max_length
    assert len(source) <= max_length
    assert max_length >= 64


@pytest.mark.django_db
@override_settings(
    B2B_DTF_ORDER_PROJECT_ENABLED=True,
    GOOGLE_DRIVE_SYNC_ENABLED=False,
    PAYPAL_CLIENT_ID="",
    PAYPAL_CLIENT_SECRET="",
    PAYPAL_WEBHOOK_ID="",
    STRIPE_PUBLISHABLE_KEY="",
    STRIPE_SECRET_KEY="",
    STRIPE_WEBHOOK_SECRET="",
)
def test_studio_checkout_creates_priced_order_without_project_hop():
    PaymentGatewaySettings.objects.all().delete()
    _seed_catalog()
    user = get_user_model().objects.create_user(email="studio-pay@example.com", password="pass")
    customer = Customer.objects.create(
        name="Studio Pay Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
        default_shipping_mode=Customer.DefaultShippingMode.PICKUP,
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Planche studio")
    _add_placed_ready_visual(sheet=sheet, user=user)
    sheet.status = GangSheet.Status.VALIDATED
    sheet.surface_sqm = Decimal("1.1000")
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        b"%PDF-1.4\n% studio pay\n%%EOF\n",
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "surface_sqm", "final_file", "updated_at"])

    client = Client()
    assert client.login(email="studio-pay@example.com", password="pass")
    url = reverse(
        "portal:client-gang-sheet-checkout",
        kwargs={
            "customer_public_id": customer.public_id,
            "sheet_public_id": sheet.public_id,
        },
    )
    response = client.post(
        url,
        {
            "billing_mode": "immediate",
            "quantity": "2",
            "support_color_hex": "#112233",
            "name": "Commande studio été",
            "requested_date": "2026-09-20",
            "customer_comment": "Urgent atelier",
            "shipping_method_code": "pickup",
        },
    )
    assert response.status_code == 302
    location = response["Location"]
    assert "order-projects" not in location
    assert "create-order" not in location
    sheet.refresh_from_db()
    assert sheet.order_id is not None
    order = sheet.order
    assert order.billing_mode == Order.BillingMode.IMMEDIATE
    assert order.pricing_status == Order.PricingStatus.PRICED
    assert location == (
        reverse(
            "portal:client-order-detail",
            kwargs={
                "customer_public_id": customer.public_id,
                "order_public_id": order.public_id,
            },
        )
        + "?panel=billing&checkout=success&pay=1"
    )
    upload = order.uploads.get()
    assert upload.quantity == 2
    assert upload.support_color_hex == "#112233"
    assert sheet.project.name == "Commande studio été"
    assert str(sheet.project.requested_date) == "2026-09-20"
    assert sheet.project.customer_comment == "Urgent atelier"

    retry = client.post(
        url,
        {
            "billing_mode": "immediate",
            "quantity": "2",
            "support_color_hex": "#112233",
            "shipping_method_code": "pickup",
            "provider": "paypal",
        },
    )
    assert retry.status_code == 302
    assert "/checkout/" not in retry["Location"]


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_studio_checkout_does_not_require_file_confirmation():
    _seed_catalog()
    user = get_user_model().objects.create_user(email="studio-confirm@example.com", password="pass")
    customer = Customer.objects.create(
        name="Studio Confirm Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
        default_shipping_mode=Customer.DefaultShippingMode.PICKUP,
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Planche confirm")
    _add_placed_ready_visual(sheet=sheet, user=user)
    sheet.status = GangSheet.Status.VALIDATED
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        b"%PDF-1.4\n% confirm\n%%EOF\n",
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "final_file", "updated_at"])

    client = Client()
    assert client.login(email="studio-confirm@example.com", password="pass")
    response = client.post(
        reverse(
            "portal:client-gang-sheet-checkout",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        ),
        {
            "billing_mode": "immediate",
            "support_color_hex": "#112233",
            "shipping_method_code": "pickup",
        },
    )
    assert response.status_code == 302
    assert "checkout_error=" not in response["Location"]
    sheet.refresh_from_db()
    assert sheet.order_id is not None
    assert sheet.project.name == "Planche confirm"


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_deferred_studio_editor_hides_payment_and_offers_validation():
    _seed_catalog()
    ShippingMethodService().ensure_default_methods()
    user = get_user_model().objects.create_user(email="studio-encours@example.com", password="pass")
    customer = Customer.objects.create(
        name="Studio Encours Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.DEFERRED,
        default_shipping_mode=Customer.DefaultShippingMode.PICKUP,
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Planche encours")
    _add_placed_ready_visual(sheet=sheet, user=user)
    sheet.status = GangSheet.Status.VALIDATED
    sheet.surface_sqm = Decimal("1.1000")
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        b"%PDF-1.4\n% encours editor\n%%EOF\n",
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "surface_sqm", "final_file", "updated_at"])

    client = Client()
    assert client.login(email="studio-encours@example.com", password="pass")
    response = client.get(
        reverse(
            "portal:client-gang-sheet-editor",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        )
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert 'value="deferred"' in content
    assert "data-studio-pay-methods" not in content
    assert 'name="provider"' not in content
    assert "aucun paiement en ligne" in content
    assert "Je commande" in content
    assert "Confirmer la commande" in content
    assert "Payer " not in content


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_deferred_studio_checkout_creates_priced_order_without_payment():
    _seed_catalog()
    ShippingMethodService().ensure_default_methods()
    user = get_user_model().objects.create_user(
        email="studio-encours-pay@example.com",
        password="pass",
    )
    customer = Customer.objects.create(
        name="Studio Encours Pay Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.DEFERRED,
        default_shipping_mode=Customer.DefaultShippingMode.PICKUP,
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    sheet = GangSheetService().create_sheet(
        customer=customer,
        actor=user,
        name="Planche encours pay",
    )
    _add_placed_ready_visual(sheet=sheet, user=user)
    sheet.status = GangSheet.Status.VALIDATED
    sheet.surface_sqm = Decimal("1.1000")
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        b"%PDF-1.4\n% encours pay\n%%EOF\n",
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "surface_sqm", "final_file", "updated_at"])

    client = Client()
    assert client.login(email="studio-encours-pay@example.com", password="pass")
    response = client.post(
        reverse(
            "portal:client-gang-sheet-checkout",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        ),
        {
            "billing_mode": "immediate",
            "quantity": "1",
            "support_color_hex": "#112233",
            "name": "Commande encours studio",
            "shipping_method_code": "pickup",
            "provider": "paypal",
        },
    )
    assert response.status_code == 302
    sheet.refresh_from_db()
    assert sheet.order_id is not None
    order = sheet.order
    assert order.billing_mode == Order.BillingMode.DEFERRED
    assert order.pricing_status == Order.PricingStatus.PRICED
    assert order.tax_amount == Decimal("0.00")
    assert str(order.public_id) in response["Location"]
    assert response["Location"] == (
        reverse(
            "portal:client-order-detail",
            kwargs={
                "customer_public_id": customer.public_id,
                "order_public_id": order.public_id,
            },
        )
        + "?checkout=success"
    )
    assert Payment.objects.filter(order=order).count() == 0
    assert requires_captured_payment_before_production(order) is False


@pytest.mark.django_db
@override_settings(
    B2B_DTF_ORDER_PROJECT_ENABLED=True,
    GOOGLE_DRIVE_SYNC_ENABLED=False,
    PAYPAL_CLIENT_ID="",
    PAYPAL_CLIENT_SECRET="",
    PAYPAL_WEBHOOK_ID="",
    STRIPE_PUBLISHABLE_KEY="",
    STRIPE_SECRET_KEY="",
    STRIPE_WEBHOOK_SECRET="",
)
def test_studio_keeps_checkout_form_after_order_and_creates_a_new_order():
    PaymentGatewaySettings.objects.all().delete()
    _seed_catalog()
    ShippingMethodService().ensure_default_methods()
    user = get_user_model().objects.create_user(
        email="studio-repeat@example.com",
        password="pass",
    )
    customer = Customer.objects.create(
        name="Studio Repeat Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.DEFERRED,
        default_shipping_mode=Customer.DefaultShippingMode.PICKUP,
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    sheet = GangSheetService().create_sheet(
        customer=customer,
        actor=user,
        name="Planche réassort",
    )
    _add_placed_ready_visual(sheet=sheet, user=user)
    sheet.status = GangSheet.Status.VALIDATED
    sheet.surface_sqm = Decimal("1.1000")
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        b"%PDF-1.4\n% repeat studio\n%%EOF\n",
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "surface_sqm", "final_file", "updated_at"])

    client = Client()
    assert client.login(email="studio-repeat@example.com", password="pass")
    editor_kwargs = {
        "customer_public_id": customer.public_id,
        "sheet_public_id": sheet.public_id,
    }
    checkout_url = reverse("portal:client-gang-sheet-checkout", kwargs=editor_kwargs)
    first = client.post(
        checkout_url,
        {
            "billing_mode": "deferred",
            "quantity": "2",
            "support_color_hex": "#112233",
            "name": "Première commande",
            "shipping_method_code": "pickup",
        },
    )
    assert first.status_code == 302
    sheet.refresh_from_db()
    first_order_id = sheet.order_id
    first_asset_id = sheet.production_asset_id
    assert first_order_id is not None
    assert first_asset_id is not None

    editor = client.get(reverse("portal:client-gang-sheet-editor", kwargs=editor_kwargs))
    assert editor.status_code == 200
    body = editor.content.decode()
    assert "Je commande" in body
    assert "Voir ma commande" not in body
    assert "data-studio-checkout-form" in body
    assert checkout_url in body

    second = client.post(
        checkout_url,
        {
            "billing_mode": "deferred",
            "quantity": "7",
            "support_color_hex": "#445566",
            "name": "Réassort studio",
            "shipping_method_code": "pickup",
        },
    )
    assert second.status_code == 302
    sheet.refresh_from_db()
    first_order = Order.objects.get(pk=first_order_id)
    assert sheet.order_id != first_order_id
    assert sheet.production_asset_id == first_asset_id
    repeat_order = sheet.order
    assert str(repeat_order.public_id) in second["Location"]
    assert str(first_order.public_id) not in second["Location"]
    assert Order.objects.filter(customer=customer).count() == 2
    upload = repeat_order.uploads.get()
    assert upload.quantity == 7
    assert upload.support_color_hex == "#445566"
    assert upload.asset_version.asset_id == first_asset_id
    assert sheet.project.name == "Réassort studio"
    assert sheet.project.converted_order_id == repeat_order.id
    assert first_order.uploads.get().quantity == 2


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_studio_checkout_rejects_other_customer_sheet():
    owner = get_user_model().objects.create_user(email="studio-owner@example.com", password="pass")
    customer = Customer.objects.create(
        name="Studio Owner Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    CustomerMembership.objects.create(customer=customer, user=owner)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    sheet = GangSheetService().create_sheet(customer=customer, actor=owner, name="Planche isolée")
    _add_placed_ready_visual(sheet=sheet, user=owner)
    sheet.status = GangSheet.Status.VALIDATED
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        b"%PDF-1.4\n% iso\n%%EOF\n",
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "final_file", "updated_at"])

    other = get_user_model().objects.create_user(email="studio-other@example.com", password="pass")
    other_customer = Customer.objects.create(
        name="Studio Other Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    CustomerMembership.objects.create(customer=other_customer, user=other)

    client = Client()
    assert client.login(email="studio-other@example.com", password="pass")
    response = client.post(
        reverse(
            "portal:client-gang-sheet-checkout",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        ),
        {
            "billing_mode": "immediate",
            "support_color_hex": "#112233",
            "shipping_method_code": "pickup",
        },
    )
    assert response.status_code == 403
    sheet.refresh_from_db()
    assert sheet.order_id is None


@pytest.mark.django_db
@override_settings(
    B2B_DTF_ORDER_PROJECT_ENABLED=True,
    GOOGLE_DRIVE_SYNC_ENABLED=False,
    PAYPAL_CLIENT_ID="paypal-id",
    PAYPAL_CLIENT_SECRET="paypal-secret",
    STRIPE_SECRET_KEY="sk_test_x",
)
def test_studio_editor_exposes_checkout_dialog_and_payment_choice():
    _seed_catalog()
    ShippingMethodService().ensure_default_methods()
    user = get_user_model().objects.create_user(email="studio-modal@example.com", password="pass")
    customer = Customer.objects.create(
        name="Studio Modal Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
        default_shipping_mode=Customer.DefaultShippingMode.CARRIER,
        billing_address_line1="10 rue de la Presse",
        billing_postal_code="75011",
        billing_city="Paris",
        billing_country="FR",
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Planche modal")
    _add_placed_ready_visual(sheet=sheet, user=user)
    sheet.status = GangSheet.Status.VALIDATED
    sheet.surface_sqm = Decimal("1.1000")
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        b"%PDF-1.4\n% modal\n%%EOF\n",
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "surface_sqm", "final_file", "updated_at"])

    client = Client()
    assert client.login(email="studio-modal@example.com", password="pass")
    response = client.get(
        reverse(
            "portal:client-gang-sheet-editor",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        )
    )
    assert response.status_code == 200
    body = response.content.decode()
    assert "data-studio-pay-dialog" in body
    assert 'name="delivery_destination"' in body
    assert 'name="shipping_method_code"' in body
    assert 'name="shipping_house_number"' in body
    assert 'name="shipping_contact_name"' in body
    assert "Mode de livraison" in body
    assert 'name="provider"' in body
    assert "PayPal" in body
    assert "Carte bancaire" in body
    assert "Autre point de livraison" in body


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_studio_checkout_persists_other_delivery_address():
    _seed_catalog()
    ShippingMethodService().ensure_default_methods()
    user = get_user_model().objects.create_user(
        email="studio-delivery@example.com",
        password="pass",
    )
    customer = Customer.objects.create(
        name="Studio Delivery Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
        default_shipping_mode=Customer.DefaultShippingMode.CARRIER,
        billing_address_line1="10 rue de la Presse",
        billing_postal_code="75011",
        billing_city="Paris",
        billing_country="FR",
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Planche livraison")
    _add_placed_ready_visual(sheet=sheet, user=user)
    sheet.status = GangSheet.Status.VALIDATED
    sheet.surface_sqm = Decimal("1.1000")
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        b"%PDF-1.4\n% delivery\n%%EOF\n",
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "surface_sqm", "final_file", "updated_at"])

    client = Client()
    assert client.login(email="studio-delivery@example.com", password="pass")
    response = client.post(
        reverse(
            "portal:client-gang-sheet-checkout",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        ),
        {
            "billing_mode": "immediate",
            "quantity": "1",
            "support_color_hex": "#112233",
            "shipping_method_code": "standard",
            "delivery_destination": "other",
            "shipping_contact_name": "Marie Loire",
            "shipping_email": "marie@example.com",
            "shipping_phone": "0612345678",
            "shipping_company_name": "Studio Delivery Co",
            "shipping_house_number": "12",
            "shipping_address_line1": "quai de Loire",
            "shipping_postal_code": "45000",
            "shipping_city": "Orléans",
            "shipping_country": "FR",
        },
    )
    assert response.status_code == 302
    customer.refresh_from_db()
    sheet.refresh_from_db()
    assert customer.shipping_address_line1 == "quai de Loire"
    assert customer.shipping_city == "Orléans"
    assert customer.billing_address_line1 == "10 rue de la Presse"
    assert sheet.project_id is not None
    assert sheet.project.shipping_address.get("line1") == "quai de Loire"
    assert sheet.project.shipping_address.get("house_number") == "12"
    assert sheet.project.shipping_address.get("name") == "Marie Loire"
    assert sheet.project.shipping_address.get("email") == "marie@example.com"
    assert sheet.project.shipping_address.get("city") == "Orléans"


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_studio_checkout_rejects_empty_other_delivery_address():
    _seed_catalog()
    ShippingMethodService().ensure_default_methods()
    user = get_user_model().objects.create_user(
        email="studio-delivery-empty@example.com",
        password="pass",
    )
    customer = Customer.objects.create(
        name="Studio Delivery Empty Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
        default_shipping_mode=Customer.DefaultShippingMode.CARRIER,
        billing_address_line1="10 rue de la Presse",
        billing_postal_code="75011",
        billing_city="Paris",
        billing_country="FR",
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Planche vide")
    _add_placed_ready_visual(sheet=sheet, user=user)
    sheet.status = GangSheet.Status.VALIDATED
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        b"%PDF-1.4\n% empty-delivery\n%%EOF\n",
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "final_file", "updated_at"])

    client = Client()
    assert client.login(email="studio-delivery-empty@example.com", password="pass")
    response = client.post(
        reverse(
            "portal:client-gang-sheet-checkout",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        ),
        {
            "billing_mode": "immediate",
            "support_color_hex": "#112233",
            "shipping_method_code": "standard",
            "delivery_destination": "other",
        },
    )
    assert response.status_code == 302
    assert "checkout_error=delivery_address_required" in response["Location"]
    sheet.refresh_from_db()
    assert sheet.order_id is None


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_studio_checkout_rejects_missing_sendcloud_recipient():
    _seed_catalog()
    ShippingMethodService().ensure_default_methods()
    user = get_user_model().objects.create_user(
        email="studio-recipient-empty@example.com",
        password="pass",
    )
    customer = Customer.objects.create(
        name="Studio Recipient Empty Co",
        billing_email="studio-recipient-empty@example.com",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
        default_shipping_mode=Customer.DefaultShippingMode.CARRIER,
        billing_address_line1="10 rue de la Presse",
        billing_postal_code="75011",
        billing_city="Paris",
        billing_country="FR",
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    sheet = GangSheetService().create_sheet(
        customer=customer, actor=user, name="Planche destinataire"
    )
    _add_placed_ready_visual(sheet=sheet, user=user)
    sheet.status = GangSheet.Status.VALIDATED
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        b"%PDF-1.4\n% recipient\n%%EOF\n",
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "final_file", "updated_at"])

    client = Client()
    assert client.login(email="studio-recipient-empty@example.com", password="pass")
    response = client.post(
        reverse(
            "portal:client-gang-sheet-checkout",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        ),
        {
            "billing_mode": "immediate",
            "support_color_hex": "#112233",
            "shipping_method_code": "standard",
            "delivery_destination": "billing",
        },
    )
    assert response.status_code == 302
    assert "checkout_error=delivery_recipient_required" in response["Location"]
    sheet.refresh_from_db()
    assert sheet.order_id is None


@pytest.mark.django_db
@override_settings(
    B2B_DTF_ORDER_PROJECT_ENABLED=True,
    GOOGLE_DRIVE_SYNC_ENABLED=False,
    PAYPAL_CLIENT_ID="paypal-id",
    PAYPAL_CLIENT_SECRET="paypal-secret",
    STRIPE_SECRET_KEY="sk_test_x",
)
def test_studio_checkout_uses_requested_payment_provider():
    _seed_catalog()
    user = get_user_model().objects.create_user(
        email="studio-provider@example.com",
        password="pass",
    )
    customer = Customer.objects.create(
        name="Studio Provider Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
        default_shipping_mode=Customer.DefaultShippingMode.PICKUP,
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Planche provider")
    _add_placed_ready_visual(sheet=sheet, user=user)
    sheet.status = GangSheet.Status.VALIDATED
    sheet.surface_sqm = Decimal("1.1000")
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        b"%PDF-1.4\n% provider\n%%EOF\n",
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "surface_sqm", "final_file", "updated_at"])

    client = Client()
    assert client.login(email="studio-provider@example.com", password="pass")

    payment = MagicMock()
    payment.approval_url = "https://paypal.example/approve"

    with patch(
        "apps.portal.views_common.billing_service.initiate_payment_for_customer_order",
        return_value=(MagicMock(), payment),
    ) as initiate:
        response = client.post(
            reverse(
                "portal:client-gang-sheet-checkout",
                kwargs={
                    "customer_public_id": customer.public_id,
                    "sheet_public_id": sheet.public_id,
                },
            ),
            {
                "billing_mode": "immediate",
                "quantity": "1",
                "support_color_hex": "#112233",
                "shipping_method_code": "pickup",
                "provider": "paypal",
            },
        )

    assert response.status_code == 302
    assert response["Location"] == "https://paypal.example/approve"
    initiate.assert_called_once()
    assert initiate.call_args.kwargs["provider"] == "paypal"


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
        name="Commande planche qty",
        requested_date="2026-08-15",
        customer_comment="Livraison prioritaire",
    )
    assert project.items.get().quantity == 4
    assert project.name == "Commande planche qty"
    assert str(project.requested_date) == "2026-08-15"
    assert project.customer_comment == "Livraison prioritaire"


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_create_order_project_form_collects_name_date_and_comment():
    _seed_catalog()
    user = get_user_model().objects.create_user(email="form-gs@example.com", password="pass")
    customer = Customer.objects.create(
        name="Form GS Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Planche form")
    sheet.status = GangSheet.Status.VALIDATED
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        b"%PDF-1.4\n% form\n%%EOF\n",
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "final_file", "updated_at"])
    client = Client()
    assert client.login(email="form-gs@example.com", password="pass")
    form_url = reverse(
        "portal:client-gang-sheet-create-order-project",
        kwargs={
            "customer_public_id": customer.public_id,
            "sheet_public_id": sheet.public_id,
        },
    )
    get_response = client.get(form_url, {"quantity": "3"})
    assert get_response.status_code == 200
    content = get_response.content.decode()
    assert "Nom de la commande" in content
    assert 'name="requested_date"' in content
    assert 'name="customer_comment"' in content
    assert 'name="quantity"' in content
    assert 'value="3"' in content

    post_response = client.post(
        form_url,
        {
            "name": "Commande depuis planche",
            "requested_date": "2026-09-01",
            "customer_comment": "Commentaire atelier",
            "quantity": "3",
        },
    )
    assert post_response.status_code == 302
    sheet.refresh_from_db()
    project = sheet.project
    assert project is not None
    assert project.name == "Commande depuis planche"
    assert str(project.requested_date) == "2026-09-01"
    assert project.customer_comment == "Commentaire atelier"
    assert project.items.get().quantity == 3
    assert str(project.public_id) in post_response["Location"]


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
    assert (
        reverse(
            "portal:client-gang-sheet-list-create",
            kwargs={"customer_public_id": customer.public_id},
        )
        in response["Location"]
    )


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_deferred_gang_sheet_checkout_auto_prices_without_vat():
    _seed_catalog()
    ShippingMethodService().ensure_default_methods()
    user = get_user_model().objects.create_user(email="deferred@example.com", password="pass")
    customer = Customer.objects.create(
        name="Deferred Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.DEFERRED,
        default_shipping_mode=Customer.DefaultShippingMode.PICKUP,
    )
    membership = CustomerMembership.objects.create(customer=customer, user=user)
    project, _sheet = _prepare_gang_sheet_project(customer=customer, user=user)

    order = B2BOrderProjectCheckoutService().checkout_project(
        project=project,
        actor=user,
        customer_membership=membership,
        source="test",
        billing_mode="deferred",
        shipping_method_code="pickup",
    )

    assert order.billing_mode == Order.BillingMode.DEFERRED
    assert order.pricing_status == Order.PricingStatus.PRICED
    assert order.subtotal_amount == Decimal("32.50")
    assert order.tax_amount == Decimal("0.00")
    assert order.total_amount == Decimal("32.50")
    assert requires_captured_payment_before_production(order) is False
    assert order_awaits_client_payment(order) is False


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_immediate_account_reorder_checkout_auto_prices_and_awaits_payment():
    from apps.b2b_order_projects.services import B2BOrderReorderService
    from apps.shipping.services.methods import ShippingMethodService

    _seed_catalog()
    ShippingMethodService().ensure_default_methods()
    user = get_user_model().objects.create_user(email="cash-reorder@example.com", password="pass")
    customer = Customer.objects.create(
        name="Cash Reorder Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
        default_shipping_mode=Customer.DefaultShippingMode.PICKUP,
    )
    membership = CustomerMembership.objects.create(customer=customer, user=user)

    source_project, _sheet = _prepare_gang_sheet_project(customer=customer, user=user)
    source_order = B2BOrderProjectCheckoutService().checkout_project(
        project=source_project,
        actor=user,
        customer_membership=membership,
        source="test",
        billing_mode="immediate",
        shipping_method_code="pickup",
    )
    assert source_order.pricing_status == Order.PricingStatus.PRICED

    reorder_project = B2BOrderReorderService().create_reorder_from_order(
        customer=customer,
        order=source_order,
        actor=user,
        source="test",
    )
    assert reorder_project.order_mode == B2BOrderProject.OrderMode.REORDER
    assert reorder_project.status == B2BOrderProject.Status.READY_TO_SUBMIT
    reorder_item = reorder_project.items.get()
    assert reorder_item.width_mm > 0
    assert reorder_item.height_mm > 0

    reorder_order = B2BOrderProjectCheckoutService().checkout_project(
        project=reorder_project,
        actor=user,
        customer_membership=membership,
        source="test",
        billing_mode="immediate",
        shipping_method_code="pickup",
    )

    assert reorder_order.billing_mode == Order.BillingMode.IMMEDIATE
    assert reorder_order.pricing_status == Order.PricingStatus.PRICED
    assert reorder_order.total_amount > Decimal("0.00")
    assert reorder_order.tax_amount > Decimal("0.00")
    assert requires_captured_payment_before_production(reorder_order) is True
    assert order_awaits_client_payment(reorder_order) is True
    upload = reorder_order.uploads.get()
    assert upload.width_mm == reorder_item.width_mm
    assert upload.height_mm == reorder_item.height_mm
    assert upload.meterage_override_sqm is not None


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True, GOOGLE_DRIVE_SYNC_ENABLED=False)
def test_gang_sheet_reorder_project_allows_quantity_change():
    from apps.b2b_order_projects.services import B2BOrderReorderService
    from apps.shipping.services.methods import ShippingMethodService

    _seed_catalog()
    ShippingMethodService().ensure_default_methods()
    user = get_user_model().objects.create_user(
        email="cash-reorder-qty@example.com",
        password="pass",
    )
    customer = Customer.objects.create(
        name="Cash Reorder Qty Co",
        b2b_order_projects_enabled=True,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
        default_shipping_mode=Customer.DefaultShippingMode.PICKUP,
    )
    membership = CustomerMembership.objects.create(customer=customer, user=user)
    source_project, _sheet = _prepare_gang_sheet_project(customer=customer, user=user)
    source_item = source_project.items.get()
    source_item.quantity = 3
    source_item.save(update_fields=["quantity", "updated_at"])
    source_order = B2BOrderProjectCheckoutService().checkout_project(
        project=source_project,
        actor=user,
        customer_membership=membership,
        source="test",
        billing_mode="immediate",
        shipping_method_code="pickup",
    )
    reorder_project = B2BOrderReorderService().create_reorder_from_order(
        customer=customer,
        order=source_order,
        actor=user,
        source="test",
    )
    reorder_item = reorder_project.items.get()
    assert reorder_item.quantity == 3

    client = Client()
    assert client.login(email=user.email, password="pass")
    detail = client.get(
        reverse(
            "portal:client-order-project-detail",
            kwargs={
                "customer_public_id": customer.public_id,
                "project_public_id": reorder_project.public_id,
            },
        )
    )
    assert detail.status_code == 200
    html = detail.content.decode()
    assert "b2b-inline-quantity-form" in html
    assert 'name="quantity"' in html
    assert 'value="3"' in html

    updated = client.post(
        reverse(
            "portal:client-order-project-item-action",
            kwargs={
                "customer_public_id": customer.public_id,
                "project_public_id": reorder_project.public_id,
                "item_public_id": reorder_item.public_id,
                "action": "update",
            },
        ),
        {"quantity": "8"},
        HTTP_HX_REQUEST="true",
    )
    assert updated.status_code == 200
    reorder_item.refresh_from_db()
    assert reorder_item.quantity == 8
    assert 'value="8"' in updated.content.decode()
