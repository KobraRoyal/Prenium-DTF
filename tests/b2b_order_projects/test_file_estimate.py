from decimal import Decimal

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.b2b_order_projects.models import B2BOrderProject
from apps.b2b_order_projects.services import B2BOrderProjectService
from apps.b2b_order_projects.services.file_estimate import (
    present_order_notice,
    present_project_estimate,
    request_file_order_quote,
    unit_billable_sqm,
)
from apps.customers.models import (
    Customer,
    CustomerBillingProfile,
    CustomerMembership,
    CustomerVolumeDiscountTier,
    DefaultCustomerVolumeDiscountTier,
)
from apps.orders.models import Order
from apps.orders.services.orders import OrderService
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import Client, override_settings
from django.urls import reverse


def _scope(email, *, billing_mode=Customer.DefaultBillingMode.DEFERRED):
    user = get_user_model().objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(
        name="Encours fichier",
        default_billing_mode=billing_mode,
        negotiated_file_preparation_fee_eur=Decimal("0.00"),
        b2b_order_projects_enabled=True,
    )
    CustomerMembership.objects.create(
        customer=customer,
        user=user,
        role=CustomerMembership.Role.OWNER,
    )
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur=Decimal("25.00"))
    project = B2BOrderProjectService().create_project(
        customer=customer,
        actor=user,
        data={"name": "Logos fichier"},
        source="test",
    )
    B2BOrderProjectService().add_item(
        project=project,
        actor=user,
        data={"name": "Logo", "width_mm": 1000, "height_mm": 200, "quantity": 2},
        source="test",
    )
    return user, customer, project


def test_unit_billable_sqm_uses_the_atelier_laize():
    assert unit_billable_sqm(width_mm=Decimal("1000"), height_mm=Decimal("200")) == Decimal(
        "0.2000"
    )


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_new_order_page_explains_deferred_pricing_before_deposit():
    user, customer, _project = _scope("new-order-estimate@example.com")
    client = Client()
    client.login(email=user.email, password="pass")

    response = client.get(
        reverse(
            "portal:client-order-project-create",
            kwargs={"customer_public_id": customer.public_id},
        )
    )

    assert response.status_code == 200
    body = response.content.decode()
    assert "Déposez vos visuels pour voir une estimation" in body
    assert "demander un devis avant d’envoyer" in body
    assert "retour atelier, sur le métrage réel" in body
    assert "longueur réellement imprimée" not in body
    assert "L’estimation apparaîtra" not in body
    assert "data-file-estimate-live" not in body


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_project_quantity_carries_the_unit_area_for_a_live_estimate():
    user, customer, project = _scope("live-quantity@example.com")
    client = Client()
    client.login(email=user.email, password="pass")

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
    assert "data-estimate-quantity" in body
    assert 'data-sqm-each="0.2000"' in body
    assert "Demander un devis" in body


@pytest.mark.django_db
def test_deferred_file_estimate_uses_declared_size_and_client_rate():
    _user, customer, project = _scope("estimate@example.com")

    notice = present_project_estimate(project=project, customer=customer)

    assert notice["requested"] is False
    assert notice["quote"]["unit_price_eur"] == Decimal("25.00")
    assert notice["quote"]["billable_sqm"] == Decimal("0.4000")
    assert notice["quote"]["dtf_gross_amount_eur"] == Decimal("10.00")
    assert notice["quote"]["dtf_amount_eur"] == Decimal("10.00")
    assert notice["quote"]["volume_discount_percent"] == Decimal("0.00")
    assert notice["quote"]["billing_mode"] == Order.BillingMode.DEFERRED
    assert notice["quote"]["tax_amount_eur"] == Decimal("0.00")
    assert notice["indicative_linear_m"] == Decimal("0.73")
    assert notice["quote"]["shipping_estimate_label"] == "Standard — délai de traitement 2–3 jours"


@pytest.mark.django_db
def test_estimate_applies_the_personalized_tier_on_the_surface_rate():
    _user, customer, project = _scope("estimate-tier@example.com")
    CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m=Decimal("0.5000"),
        discount_percent=Decimal("10.00"),
    )
    DefaultCustomerVolumeDiscountTier.objects.create(
        minimum_monthly_linear_m=Decimal("0.5000"),
        discount_percent=Decimal("40.00"),
    )

    notice = present_project_estimate(project=project, customer=customer)
    quote = notice["quote"]

    assert quote["unit_price_eur"] == Decimal("25.00")
    assert quote["dtf_gross_amount_eur"] == Decimal("10.00")
    assert quote["volume_discount_percent"] == Decimal("10.00")
    assert quote["dtf_amount_eur"] == Decimal("9.00")
    assert quote["volume_discount_amount_eur"] == Decimal("1.00")
    assert quote["prep_amount_eur"] == Decimal("0.00")
    assert quote["total_eur"] == quote["dtf_amount_eur"] + quote["shipping_amount_eur"]


@pytest.mark.django_db
def test_estimate_is_absent_for_cash_and_gang_sheet():
    user, customer, project = _scope("cash@example.com")
    customer.default_billing_mode = Customer.DefaultBillingMode.IMMEDIATE
    customer.save(update_fields=["default_billing_mode", "updated_at"])
    assert present_project_estimate(project=project, customer=customer) is None

    project.order_mode = B2BOrderProject.OrderMode.READY_GANG_SHEET
    project.save(update_fields=["order_mode", "updated_at"])
    customer.default_billing_mode = Customer.DefaultBillingMode.DEFERRED
    customer.save(update_fields=["default_billing_mode", "updated_at"])
    assert present_project_estimate(project=project, customer=customer) is None
    with pytest.raises(ValidationError):
        request_file_order_quote(project=project, customer=customer, actor=user)


@pytest.mark.django_db
def test_quote_request_records_estimate_without_creating_an_order():
    user, customer, project = _scope("quote@example.com")

    project.refresh_from_db()
    status_before = project.status
    request_file_order_quote(project=project, customer=customer, actor=user)
    project.refresh_from_db()

    assert project.price_confirmation_required is True
    assert project.status == status_before
    assert project.estimated_subtotal == Decimal("10.00")
    assert project.estimated_tax == Decimal("0.00")
    assert project.estimated_total >= project.estimated_subtotal
    assert project.estimated_length_mm == 730
    assert Order.objects.filter(customer=customer).count() == 0
    assert AuditLogEntry.objects.filter(
        action="b2b_order_project.quote_requested",
        target_public_id=project.public_id,
    ).exists()


@override_settings(INTERNAL_NOTIFICATION_EMAILS=["atelier@example.com"])
def test_quote_request_emails_the_client_and_the_atelier(django_capture_on_commit_callbacks):
    user, customer, project = _scope("quote-mail@example.com")
    mail.outbox.clear()

    with django_capture_on_commit_callbacks(execute=True):
        request_file_order_quote(project=project, customer=customer, actor=user)

    subjects = {message.subject for message in mail.outbox}
    assert "Votre demande de devis — Encours fichier" in subjects
    assert "[Atelier] Demande de devis — Encours fichier" in subjects
    client_mail = next(message for message in mail.outbox if user.email in message.to)
    atelier_mail = next(message for message in mail.outbox if "atelier@example.com" in message.to)
    assert "validez ou supprimez" in client_mail.body
    assert "indiquer le métrage" in atelier_mail.body
    assert f"/staff/quotes/{project.public_id}/" in atelier_mail.body
    assert str(customer.public_id) in client_mail.body


@pytest.mark.django_db
def test_order_notice_stays_on_unpriced_deferred_file_orders():
    user, customer, project = _scope("order-notice@example.com")
    order = OrderService().create_b2b_deferred_order(
        customer=customer,
        actor=user,
        customer_note="",
        source="test",
    )
    assert present_order_notice(order)["quote"] is None

    project.converted_order = order
    project.save(update_fields=["converted_order", "updated_at"])
    assert present_order_notice(order)["quote"]["dtf_amount_eur"] == Decimal("10.00")

    client = Client()
    client.login(email=user.email, password="pass")
    page = client.get(
        reverse(
            "portal:client-order-detail",
            kwargs={
                "customer_public_id": customer.public_id,
                "order_public_id": order.public_id,
            },
        )
    )
    assert page.status_code == 200
    body = page.content.decode()
    assert "Tarif estimatif" not in body
    assert "Après contrôle atelier" in body

    order.pricing_status = Order.PricingStatus.PRICED
    order.save(update_fields=["pricing_status", "updated_at"])
    assert present_order_notice(order) is None

    order.pricing_status = Order.PricingStatus.PENDING
    order.billing_mode = Order.BillingMode.IMMEDIATE
    order.save(update_fields=["pricing_status", "billing_mode", "updated_at"])
    assert present_order_notice(order) is None


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_client_can_request_a_quote_and_other_customer_cannot():
    user, customer, project = _scope("portal-quote@example.com")
    client = Client()
    client.login(email=user.email, password="pass")
    detail = reverse(
        "portal:client-order-project-detail",
        kwargs={
            "customer_public_id": customer.public_id,
            "project_public_id": project.public_id,
        },
    )
    page = client.get(detail)
    assert page.status_code == 200
    body = page.content.decode()
    assert "Tarif estimatif" in body
    assert "m² ×" not in body
    assert "d’après vos fichiers" not in body
    assert "data-file-estimate-shipping" not in body
    assert "Livraison à choisir à la confirmation" in body
    assert "Pour le tarif réel, demandez un devis" in body
    assert "métrage imprimé" in body
    assert "Demander un devis" in body
    # Délai / transporteur : uniquement dans la modale de confirmation (comme gang sheet).
    assert "Délai de traitement" in body
    assert "Standard — délai de traitement 2–3 jours" in body
    assert "Express — délai de traitement 1–2 jours" in body
    assert "2–3 jours<br>Chronopost 13" in body
    assert "1–2 jours<br>Chronopost 13" in body
    assert ">Standard<" in body
    assert ">Express<" in body
    assert "Confirmer et payer" not in body

    quote_url = reverse(
        "portal:client-order-project-quote",
        kwargs={
            "customer_public_id": customer.public_id,
            "project_public_id": project.public_id,
        },
    )
    response = client.post(quote_url)
    assert response.status_code == 302
    assert response.url == detail
    project.refresh_from_db()
    assert project.price_confirmation_required is True
    assert "Devis demandé" in client.get(detail).content.decode()

    outsider = get_user_model().objects.create_user(email="outsider@example.com", password="pass")
    other = Customer.objects.create(name="Autre", b2b_order_projects_enabled=True)
    CustomerMembership.objects.create(customer=other, user=outsider)
    outsider_client = Client()
    outsider_client.login(email=outsider.email, password="pass")
    denied = outsider_client.post(
        reverse(
            "portal:client-order-project-quote",
            kwargs={
                "customer_public_id": customer.public_id,
                "project_public_id": project.public_id,
            },
        )
    )
    assert denied.status_code == 403


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_staff_project_shows_the_real_meterage_notice():
    _user, _customer, project = _scope("staff-notice@example.com")
    request_file_order_quote(
        project=project,
        customer=project.customer,
        actor=_user,
    )
    staff = get_user_model().objects.create_user(
        email="atelier-notice@example.com",
        password="pass",
        is_staff=True,
    )
    staff.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    staff.user_permissions.add(Permission.objects.get(codename="view_b2borderproject"))
    client = Client()
    client.login(email=staff.email, password="pass")

    response = client.get(
        reverse(
            "portal:staff-order-project-detail",
            kwargs={"project_public_id": project.public_id},
        )
    )

    assert response.status_code == 200
    body = response.content.decode()
    assert "Tarif estimatif" in body
    assert "Le tarif réel suit le métrage imprimé" in body
    assert "Devis demandé" in body
    assert "Demander un devis" not in body
