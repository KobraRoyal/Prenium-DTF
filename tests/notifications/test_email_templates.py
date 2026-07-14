import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer
from apps.notifications.models import EmailTemplate
from apps.notifications.services.email_templates import (
    EMAIL_TEMPLATE_DEFINITIONS,
    EmailTemplateService,
    render_template_text,
    validate_template_pair,
)
from apps.notifications.services.transactional import (
    send_file_correction_requested_email,
    send_order_created_email,
    send_order_processing_email,
    send_order_ready_to_ship_email,
    send_order_shipped_email,
)
from apps.orders.models import Order
from apps.shipping.models import Shipment
from apps.uploads.models import OrderUpload, OrderUploadReview
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse


def create_order(*, email: str = "owner@example.com") -> tuple[object, Order]:
    user = get_user_model().objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(
        name="Atelier Démo",
        billing_email="billing@example.com",
    )
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        total_amount="125.50",
        currency="EUR",
        billing_mode=Order.BillingMode.DEFERRED,
    )
    return user, order


def create_staff(*permissions: str):
    user = get_user_model().objects.create_user(
        email=f"staff-{len(permissions)}-{get_user_model().objects.count()}@example.com",
        password="pass",
        is_staff=True,
    )
    requested = ["access_staff_portal", *permissions]
    user.user_permissions.set(Permission.objects.filter(codename__in=requested))
    return user


@pytest.mark.parametrize(
    "subject,body",
    [
        ("Objet {% include 'secret.txt' %}", "Message"),
        ("Objet", "{{ customer.unknown }}"),
        ("Objet", "{{ customer.name"),
        ("Objet\nBcc: attacker@example.com", "Message"),
    ],
)
def test_template_validation_rejects_unsafe_or_unknown_syntax(subject, body):
    with pytest.raises(ValidationError):
        validate_template_pair(subject_template=subject, body_template=body)


def test_renderer_replaces_only_allowlisted_tags():
    rendered = render_template_text(
        "Bonjour {{ customer.name }}, commande {{ order.reference }}.",
        {"customer.name": "Atelier Démo", "order.reference": "abc123"},
    )

    assert rendered == "Bonjour Atelier Démo, commande abc123."


def test_template_catalog_uses_order_lifecycle_without_redundant_b2b_event():
    events = {definition.event for definition in EMAIL_TEMPLATE_DEFINITIONS}

    assert "b2b_order_submitted" not in events
    assert {
        EmailTemplate.Event.ORDER_CREATED,
        EmailTemplate.Event.ORDER_PROCESSING,
        EmailTemplate.Event.ORDER_READY_TO_SHIP,
        EmailTemplate.Event.ORDER_SHIPPED,
    }.issubset(events)


@pytest.mark.django_db
def test_rendered_subject_removes_newlines_introduced_by_data_tags():
    _, order = create_order()
    order.customer.name = "Atelier\nBcc: attacker@example.com"
    order.customer.save(update_fields=["name"])

    rendered = EmailTemplateService().render_for_order(
        event=EmailTemplate.Event.ORDER_CREATED,
        audience=EmailTemplate.Audience.CLIENT,
        order=order,
    )

    assert rendered is not None
    subject, _ = rendered
    assert "\n" not in subject
    assert "\r" not in subject


@pytest.mark.django_db
def test_save_override_versions_and_audits_without_copying_message_content():
    actor = get_user_model().objects.create_user(email="editor@example.com", password="pass")
    service = EmailTemplateService()

    first = service.save_override(
        event=EmailTemplate.Event.ORDER_CREATED,
        audience=EmailTemplate.Audience.CLIENT,
        subject_template="Commande {{ order.reference }}",
        body_template="Bonjour {{ customer.name }}",
        is_active=True,
        actor=actor,
        ip_address="127.0.0.1",
    )
    second = service.save_override(
        event=EmailTemplate.Event.ORDER_CREATED,
        audience=EmailTemplate.Audience.CLIENT,
        subject_template="Commande reçue {{ order.reference }}",
        body_template="Bonjour {{ customer.name }}",
        is_active=False,
        actor=actor,
    )

    assert first.public_id == second.public_id
    assert second.version == 2
    assert second.is_active is False
    audit = AuditLogEntry.objects.filter(
        action="notifications.email_template.updated"
    ).latest("created_at")
    assert audit.target_public_id == second.public_id
    assert audit.metadata == {
        "event": "order_created",
        "audience": "client",
        "version": 2,
        "is_active": False,
    }
    assert "Bonjour" not in str(audit.metadata)


@pytest.mark.django_db
@override_settings(INTERNAL_NOTIFICATION_EMAILS=["atelier@example.com", "ATELIER@example.com"])
def test_custom_client_and_internal_templates_are_sent_to_separate_audiences():
    actor, order = create_order()
    service = EmailTemplateService()
    service.save_override(
        event=EmailTemplate.Event.ORDER_CREATED,
        audience=EmailTemplate.Audience.CLIENT,
        subject_template="Votre commande {{ order.reference }}",
        body_template="Bonjour {{ customer.name }}",
        is_active=True,
        actor=actor,
    )
    service.save_override(
        event=EmailTemplate.Event.ORDER_CREATED,
        audience=EmailTemplate.Audience.INTERNAL,
        subject_template="Atelier {{ order.reference }}",
        body_template="Nouveau dossier {{ customer.name }}",
        is_active=True,
        actor=actor,
    )

    mail.outbox.clear()
    send_order_created_email(order=order)

    assert len(mail.outbox) == 2
    client_message = next(message for message in mail.outbox if actor.email in message.to)
    internal_message = next(
        message for message in mail.outbox if message.to == ["atelier@example.com"]
    )
    assert client_message.subject == f"Votre commande {order.short_ref}"
    assert internal_message.subject == f"Atelier {order.short_ref}"


@pytest.mark.django_db
def test_order_lifecycle_templates_render_processing_ready_and_shipping_details():
    actor, order = create_order()
    Shipment.objects.create(
        order=order,
        status=Shipment.Status.CREATED,
        shipping_option_code="sendcloud:standard",
        tracking_number="TRK-123456",
        tracking_url="https://tracking.example.test/TRK-123456",
        sendcloud_status_code="PARCEL_EN_ROUTE",
        sendcloud_status_message="Colis en route",
    )

    mail.outbox.clear()
    send_order_processing_email(order=order)
    send_order_ready_to_ship_email(order=order)
    send_order_shipped_email(order=order)

    assert len(mail.outbox) == 3
    assert "en traitement" in mail.outbox[0].subject
    assert "prête à être expédiée" in mail.outbox[1].subject
    assert "a été expédiée" in mail.outbox[2].subject
    assert "TRK-123456" in mail.outbox[2].body
    assert "https://tracking.example.test/TRK-123456" in mail.outbox[2].body


@pytest.mark.django_db
@override_settings(INTERNAL_NOTIFICATION_EMAILS=["atelier@example.com"])
def test_file_correction_email_uses_upload_and_review_tags_for_both_audiences():
    actor, order = create_order()
    upload = OrderUpload.objects.create(
        order=order,
        file=SimpleUploadedFile("logo.png", b"fake", content_type="image/png"),
        original_filename="logo.png",
        mime_type="image/png",
        size_bytes=4,
    )
    review = OrderUploadReview.objects.create(
        order_upload=upload,
        status=OrderUploadReview.Status.CHANGES_REQUESTED,
        reason_code=OrderUploadReview.Reason.LOW_RESOLUTION,
        comment="Merci de fournir une version 300 DPI.",
        reviewed_by=actor,
    )

    mail.outbox.clear()
    client_was_notified = send_file_correction_requested_email(review=review)

    assert client_was_notified is True
    assert len(mail.outbox) == 2
    client_message = next(message for message in mail.outbox if actor.email in message.to)
    internal_message = next(
        message for message in mail.outbox if message.to == ["atelier@example.com"]
    )
    assert client_message.subject == "Action requise — fichier logo.png"
    assert "Résolution insuffisante" in client_message.body
    assert "Merci de fournir une version 300 DPI." in client_message.body
    assert "logo.png" in internal_message.body


@pytest.mark.django_db
def test_client_and_staff_without_notification_permission_cannot_access_editor(client):
    client_user, _ = create_order(email="client@example.com")
    client.force_login(client_user)
    list_url = reverse("portal:staff-email-template-list")
    assert client.get(list_url).status_code == 403

    staff = create_staff("view_order")
    client.force_login(staff)
    assert client.get(list_url).status_code == 403


@pytest.mark.django_db
def test_view_only_staff_can_consult_but_cannot_save_email_template(client):
    staff = create_staff("view_emailtemplate")
    client.force_login(staff)
    edit_url = reverse(
        "portal:staff-email-template-edit",
        kwargs={"event": "order_created", "audience": "client"},
    )

    response = client.get(edit_url)
    assert response.status_code == 200
    assert "Votre rôle permet la consultation" in response.content.decode()

    response = client.post(
        edit_url,
        {
            "subject_template": "Objet",
            "body_template": "Message",
            "is_active": "on",
            "action": "save",
        },
    )
    assert response.status_code == 403
    assert EmailTemplate.objects.count() == 0


@pytest.mark.django_db
def test_authorised_staff_can_preview_and_save_from_frontend(client):
    staff = create_staff("view_emailtemplate", "change_emailtemplate")
    client.force_login(staff)
    list_url = reverse("portal:staff-email-template-list")
    edit_url = reverse(
        "portal:staff-email-template-edit",
        kwargs={"event": "order_created", "audience": "client"},
    )

    list_response = client.get(list_url)
    assert list_response.status_code == 200
    list_html = list_response.content.decode()
    assert "Messages clients" in list_html
    assert "Messages équipe" in list_html
    assert "data-email-template-token" not in list_html

    preview_response = client.post(
        edit_url,
        {
            "subject_template": "Commande {{ order.reference }}",
            "body_template": "Bonjour {{ customer.name }}",
            "is_active": "on",
            "action": "preview",
        },
    )
    assert preview_response.status_code == 200
    preview_html = preview_response.content.decode()
    assert "Commande a1b2c3d4e5f6" in preview_html
    assert "data-email-template-token" in preview_html
    assert EmailTemplate.objects.count() == 0

    save_response = client.post(
        edit_url,
        {
            "subject_template": "Commande {{ order.reference }}",
            "body_template": "Bonjour {{ customer.name }}",
            "is_active": "on",
            "action": "save",
        },
    )
    assert save_response.status_code == 302
    template = EmailTemplate.objects.get()
    assert template.updated_by == staff
    assert template.body_template == "Bonjour {{ customer.name }}"


@pytest.mark.django_db
def test_frontend_rejects_arbitrary_django_template_tags(client):
    staff = create_staff("view_emailtemplate", "change_emailtemplate")
    client.force_login(staff)
    edit_url = reverse(
        "portal:staff-email-template-edit",
        kwargs={"event": "order_created", "audience": "client"},
    )

    response = client.post(
        edit_url,
        {
            "subject_template": "Commande",
            "body_template": "{% include 'secrets.txt' %}",
            "is_active": "on",
            "action": "save",
        },
    )

    assert response.status_code == 200
    assert "instruction interdite" in response.content.decode()
    assert EmailTemplate.objects.count() == 0


@pytest.mark.django_db
def test_unknown_email_template_route_returns_404(client):
    staff = create_staff("view_emailtemplate")
    client.force_login(staff)
    response = client.get(
        reverse(
            "portal:staff-email-template-edit",
            kwargs={"event": "unknown", "audience": "client"},
        )
    )
    assert response.status_code == 404
