from datetime import timedelta

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.b2b_order_projects.models import B2BOrderProject
from apps.customers.models import Customer, CustomerInvitation, CustomerMembership
from apps.gang_sheets.models import GangSheet, GangSheetSourceAsset
from apps.notifications.models import EmailTemplate
from apps.notifications.services.email_templates import (
    EMAIL_TAGS,
    EMAIL_TEMPLATE_DEFINITIONS,
    EmailTemplateService,
    context_for_order,
    render_template_text,
    sample_context,
    validate_template_pair,
)
from apps.notifications.services.transactional import (
    send_access_request_approved_email,
    send_access_request_submitted_internal_email,
    send_access_request_verification_email,
    send_account_activated_email,
    send_customer_invitation_email,
    send_file_correction_requested_email,
    send_order_created_email,
    send_order_processing_email,
    send_order_ready_to_ship_email,
    send_order_shipped_email,
)
from apps.orders.models import Order
from apps.prospects.models import ProspectProfile
from apps.shipping.models import Shipment
from apps.uploads.models import Asset, AssetVersion, OrderUpload, OrderUploadReview
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone


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


def test_order_identity_tags_are_exposed_with_business_examples():
    tags = {tag.key: tag for tag in EMAIL_TAGS}

    assert tags["order.business_number"].label == "N° commande"
    assert tags["order.business_number"].example == "CMD-2026-000104"
    assert tags["order.client_reference"].label == "Réf. client"
    assert tags["order.client_reference"].example == "Collection été"
    assert sample_context()["order.business_number"] == "CMD-2026-000104"
    assert sample_context()["order.client_reference"] == "Collection été"
    assert "- logo.png" in sample_context()["order.files"]


@pytest.mark.django_db
def test_order_identity_tags_render_business_number_and_client_reference():
    user, order = create_order()
    B2BOrderProject.objects.create(
        customer=order.customer,
        created_by=user,
        project_number="CMD-2026-000104",
        name="Collection été",
        customer_reference="REF-CLIENT-42",
        converted_order=order,
        status=B2BOrderProject.Status.CONVERTED,
    )

    context = context_for_order(order)
    rendered = render_template_text(
        "Commande {{ order.business_number }} — {{ order.client_reference }}",
        context,
    )

    assert rendered == "Commande CMD-2026-000104 — Collection été"


@pytest.mark.django_db
def test_order_files_tag_lists_all_order_uploads_in_display_order():
    _, order = create_order()
    for sort_order, filename in ((2, "second.pdf"), (1, "first.png")):
        OrderUpload.objects.create(
            order=order,
            file=SimpleUploadedFile(filename, b"fake", content_type="application/octet-stream"),
            original_filename=filename,
            mime_type="application/octet-stream",
            size_bytes=4,
            sort_order=sort_order,
        )

    context = context_for_order(order)

    assert context["order.files"] == "- first.png\n- second.pdf"
    assert (
        render_template_text("Fichiers :\n{{ order.files }}", context)
        == "Fichiers :\n- first.png\n- second.pdf"
    )


@pytest.mark.django_db
def test_order_files_tag_includes_gang_sheet_sources():
    user, order = create_order(email="gang-files@example.com")
    sheet = GangSheet.objects.create(
        customer=order.customer,
        order=order,
        name="Planche validée",
        status=GangSheet.Status.VALIDATED,
        width_mm="560.00",
        height_mm="100.00",
        minimum_height_mm="100.00",
        maximum_height_mm="1000.00",
        height_step_mm="10.00",
        margin_mm="0.00",
        item_spacing_mm="0.00",
        item_spacing_x_mm="0.00",
        item_spacing_y_mm="0.00",
    )
    source_asset = Asset.objects.create(
        customer=order.customer, created_by=user, name="Logo client"
    )
    source_version = AssetVersion.objects.create(
        customer=order.customer,
        asset=source_asset,
        uploaded_by=user,
        version_number=1,
        file=SimpleUploadedFile("logo-source.png", b"source", content_type="image/png"),
        original_filename="logo-source.png",
        mime_type="image/png",
        size_bytes=6,
        sha256="a" * 64,
        analysis_status=AssetVersion.AnalysisStatus.READY,
    )
    source_asset.current_version = source_version
    source_asset.save(update_fields=["current_version", "updated_at"])
    GangSheetSourceAsset.objects.create(
        customer=order.customer,
        sheet=sheet,
        asset=source_asset,
        added_by=user,
        sort_order=1,
    )
    OrderUpload.objects.create(
        order=order,
        file=SimpleUploadedFile("production.pdf", b"pdf", content_type="application/pdf"),
        original_filename="production.pdf",
        mime_type="application/pdf",
        size_bytes=3,
        sort_order=1,
    )

    assert context_for_order(order)["order.files"] == "- production.pdf\n- logo-source.png"


@pytest.mark.django_db
@override_settings(PUBLIC_BASE_URL="https://portal.example.test")
def test_access_verification_email_contains_signed_public_link_and_no_fake_legal_id():
    profile = ProspectProfile.objects.create(
        first_name="Camille",
        last_name="Martin",
        email="camille@example.com",
        normalized_email="camille@example.com",
        phone="+3212345678",
        company="Atelier Belgique",
        country="BE",
        siren="",
        vat_number="BE0123456789",
        activity_type=ProspectProfile.ActivityType.WORKSHOP,
        service_interest=ProspectProfile.ServiceInterest.DTF_METER,
        project_timing=ProspectProfile.ProjectTiming.ONGOING,
        monthly_volume=ProspectProfile.MonthlyVolume.M10_50,
        order_frequency=ProspectProfile.OrderFrequency.MONTHLY,
        urgency=ProspectProfile.Urgency.MEDIUM,
        status=ProspectProfile.Status.PENDING_EMAIL_VERIFICATION,
        is_open=True,
    )

    mail.outbox.clear()
    send_access_request_verification_email(profile=profile)

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [profile.email]
    assert "https://portal.example.test/demande-acces/verifier/" in mail.outbox[0].body
    assert "123456789" not in mail.outbox[0].body


@pytest.mark.django_db
@override_settings(
    PUBLIC_BASE_URL="https://portal.example.test",
    INTERNAL_NOTIFICATION_EMAILS=["access@example.com"],
)
def test_verified_access_request_is_sent_only_to_internal_recipients():
    profile = ProspectProfile.objects.create(
        first_name="Jean",
        last_name="Martin",
        email="jean@example.com",
        normalized_email="jean@example.com",
        phone="+33612345678",
        company="Atelier Martin",
        country="FR",
        siren="123456789",
        activity_type=ProspectProfile.ActivityType.BRAND,
        service_interest=ProspectProfile.ServiceInterest.DTF_METER,
        project_timing=ProspectProfile.ProjectTiming.IMMEDIATE,
        monthly_volume=ProspectProfile.MonthlyVolume.M10_50,
        order_frequency=ProspectProfile.OrderFrequency.MONTHLY,
        urgency=ProspectProfile.Urgency.MEDIUM,
        status=ProspectProfile.Status.PENDING_REVIEW,
        is_open=True,
    )

    mail.outbox.clear()
    send_access_request_submitted_internal_email(profile=profile)

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["access@example.com"]
    assert profile.email in mail.outbox[0].body
    assert str(profile.public_id) in mail.outbox[0].body


@pytest.mark.django_db
@override_settings(PUBLIC_BASE_URL="https://portal.example.test")
def test_activation_and_collaborator_emails_use_versioned_invitation_link():
    actor = get_user_model().objects.create_user(email="admin@example.com", password="pass")
    customer = Customer.objects.create(name="Atelier Démo")
    profile = ProspectProfile.objects.create(
        first_name="Camille",
        last_name="Martin",
        email="camille@example.com",
        normalized_email="camille@example.com",
        phone="+33612345678",
        company=customer.name,
        country="FR",
        siren="123456789",
        activity_type=ProspectProfile.ActivityType.BRAND,
        service_interest=ProspectProfile.ServiceInterest.DTF_METER,
        project_timing=ProspectProfile.ProjectTiming.IMMEDIATE,
        monthly_volume=ProspectProfile.MonthlyVolume.M10_50,
        order_frequency=ProspectProfile.OrderFrequency.MONTHLY,
        urgency=ProspectProfile.Urgency.MEDIUM,
        customer=customer,
        status=ProspectProfile.Status.APPROVED_PENDING_ACTIVATION,
        is_open=True,
    )
    owner_invitation = CustomerInvitation.objects.create(
        customer=customer,
        email=profile.email,
        role=CustomerMembership.Role.OWNER,
        kind=CustomerInvitation.Kind.OWNER_ACTIVATION,
        invited_by=actor,
        expires_at=timezone.now() + timedelta(hours=72),
    )
    collaborator = CustomerInvitation.objects.create(
        customer=customer,
        email="member@example.com",
        role=CustomerMembership.Role.MEMBER,
        invited_by=actor,
        expires_at=timezone.now() + timedelta(hours=72),
    )

    mail.outbox.clear()
    send_access_request_approved_email(invitation=owner_invitation)
    send_customer_invitation_email(invitation=collaborator)
    send_account_activated_email(invitation=collaborator)

    assert len(mail.outbox) == 3
    for message in mail.outbox:
        assert any(
            token.startswith("https://portal.example.test/")
            for token in message.body.replace("\r", "\n").split()
            if "://" in token
        )
    assert "/acces/invitation/" in mail.outbox[0].body
    assert "/acces/invitation/" in mail.outbox[1].body
    assert "/login/" in mail.outbox[2].body


def test_template_catalog_uses_order_lifecycle_without_redundant_b2b_event():
    events = {definition.event for definition in EMAIL_TEMPLATE_DEFINITIONS}

    assert "b2b_order_submitted" not in events
    assert EmailTemplate.Event.PASSWORD_RESET in events
    assert {
        EmailTemplate.Event.ORDER_CREATED,
        EmailTemplate.Event.ORDER_PROCESSING,
        EmailTemplate.Event.ORDER_READY_TO_SHIP,
        EmailTemplate.Event.ORDER_READY_FOR_PICKUP,
        EmailTemplate.Event.ORDER_SHIPPED,
        EmailTemplate.Event.ORDER_PRICED,
        EmailTemplate.Event.ORDER_AWAITING_PAYMENT,
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
    audit = AuditLogEntry.objects.filter(action="notifications.email_template.updated").latest(
        "created_at"
    )
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
@override_settings(INTERNAL_NOTIFICATION_EMAILS=[])
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
def test_pickup_ready_notification_uses_dedicated_client_and_internal_templates():
    actor, order = create_order()
    B2BOrderProject.objects.create(
        customer=order.customer,
        created_by=actor,
        project_number="CMD-2026-000104",
        name="Collection été",
        converted_order=order,
        status=B2BOrderProject.Status.CONVERTED,
    )
    order.shipping_method_code = "pickup"
    order.shipping_method_name = "Retrait atelier"
    order.save(update_fields=["shipping_method_code", "shipping_method_name", "updated_at"])

    mail.outbox.clear()
    send_order_ready_to_ship_email(order=order)

    assert len(mail.outbox) == 2
    client_message = next(message for message in mail.outbox if actor.email in message.to)
    internal_message = next(
        message for message in mail.outbox if message.to == ["atelier@example.com"]
    )
    assert client_message.subject == "Votre commande est prête au retrait — CMD-2026-000104"
    assert "N° commande : CMD-2026-000104" in client_message.body
    assert "Réf. client : Collection été" in client_message.body
    assert internal_message.subject == "[Atelier] Commande prête au retrait — CMD-2026-000104"


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
    assert "Palier de remise atteint" in list_html
    assert "Commande prête au retrait atelier" in list_html
    assert 'data-testid="email-template-overview"' in list_html
    assert list_html.count('data-testid="email-template-row"') >= 2
    assert "Contenu sécurisé" in list_html
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
    assert "data-email-token-search" in preview_html
    assert "data-email-subject-counter" in preview_html
    assert 'data-testid="email-template-preview"' in preview_html
    assert 'data-email-template-token="{{ order.business_number }}"' in preview_html
    assert 'data-email-template-token="{{ order.client_reference }}"' in preview_html
    assert "N° commande" in preview_html
    assert "Réf. client" in preview_html
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
