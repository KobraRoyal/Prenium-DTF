from unittest.mock import patch

import pytest
from apps.customers.models import Customer, CustomerInvitation, CustomerMembership
from apps.customers.services.invitations import CustomerInvitationService, make_invitation_token
from apps.notifications.tasks import send_customer_invitation_email_task
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings
from django.urls import reverse

User = get_user_model()


def customer_scope(email: str, role: str):
    user = User.objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(name=f"Org {email}", billing_email=email)
    membership = CustomerMembership.objects.create(customer=customer, user=user, role=role)
    return user, customer, membership


@pytest.mark.django_db
def test_owner_can_invite_but_member_cannot_access_team(client):
    owner, customer, _ = customer_scope("owner@example.com", CustomerMembership.Role.OWNER)
    member = User.objects.create_user(email="member@example.com", password="pass")
    CustomerMembership.objects.create(
        customer=customer,
        user=member,
        role=CustomerMembership.Role.MEMBER,
    )
    team_url = reverse("portal:client-team", kwargs={"customer_public_id": customer.public_id})

    client.force_login(member)
    assert client.get(team_url).status_code == 403

    client.force_login(owner)
    with patch("apps.notifications.tasks.send_customer_invitation_email_task.delay") as delay:
        with TestCase.captureOnCommitCallbacks(execute=True):
            response = client.post(
                reverse(
                    "portal:client-team-invite",
                    kwargs={"customer_public_id": customer.public_id},
                ),
                {"email": "new@example.com", "role": CustomerMembership.Role.MEMBER},
            )
    assert response.status_code == 302
    invitation = CustomerInvitation.objects.get(customer=customer, email="new@example.com")
    delay.assert_called_once_with(str(invitation.public_id))


@pytest.mark.django_db
def test_owner_invitation_htmx_refreshes_panel_and_preserves_async_feedback(client):
    owner, customer, _ = customer_scope("owner-htmx@example.com", CustomerMembership.Role.OWNER)
    client.force_login(owner)

    with patch("apps.notifications.tasks.send_customer_invitation_email_task.delay") as delay:
        with TestCase.captureOnCommitCallbacks(execute=True):
            response = client.post(
                reverse(
                    "portal:client-team-invite",
                    kwargs={"customer_public_id": customer.public_id},
                ),
                {"email": "collaborateur@example.com", "role": CustomerMembership.Role.MEMBER},
                HTTP_HX_REQUEST="true",
            )

    invitation = CustomerInvitation.objects.get(
        customer=customer,
        email="collaborateur@example.com",
    )
    html = response.content.decode()
    assert response.status_code == 200
    assert response["X-Prenium-Toast"]
    assert 'id="team-invite-panel"' in html
    assert "Invitation enregistrée" in html
    assert "collaborateur@example.com" in html
    assert "Invitations en attente" in html
    assert 'value="collaborateur@example.com"' not in html
    assert '<option value="member" selected>Collaborateur</option>' in html
    delay.assert_called_once_with(str(invitation.public_id))


@pytest.mark.django_db
def test_invalid_htmx_invitation_keeps_field_value_and_shows_inline_error(client):
    owner, customer, _ = customer_scope("owner-errors@example.com", CustomerMembership.Role.OWNER)
    client.force_login(owner)

    response = client.post(
        reverse(
            "portal:client-team-invite",
            kwargs={"customer_public_id": customer.public_id},
        ),
        {"email": "adresse-invalide", "role": CustomerMembership.Role.MEMBER},
        HTTP_HX_REQUEST="true",
    )

    html = response.content.decode()
    assert response.status_code == 200
    assert '"variant": "error"' in response["X-Prenium-Toast"]
    assert 'value="adresse-invalide"' in html
    assert 'aria-invalid="true"' in html
    assert CustomerInvitation.objects.filter(customer=customer).exists() is False


@pytest.mark.django_db
@override_settings(
    TRANSACTIONAL_EMAILS_ENABLED=True,
    PUBLIC_BASE_URL="https://portal.example.test",
)
def test_registered_customer_invitation_task_delivers_the_secure_email():
    owner, customer, _ = customer_scope("owner-mail@example.com", CustomerMembership.Role.OWNER)
    with patch("apps.notifications.tasks.send_customer_invitation_email_task.delay"):
        with TestCase.captureOnCommitCallbacks(execute=True):
            invitation = CustomerInvitationService().invite_collaborator(
                customer=customer,
                actor=owner,
                email="invitee@example.com",
                role=CustomerMembership.Role.READONLY,
            )

    mail.outbox.clear()
    send_customer_invitation_email_task(str(invitation.public_id))

    assert send_customer_invitation_email_task.name == (
        "notifications.send_customer_invitation_email"
    )
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["invitee@example.com"]
    assert "https://portal.example.test/acces/invitation/" in mail.outbox[0].body


@pytest.mark.django_db
def test_owner_cannot_manage_another_organization_team(client):
    owner, _, _ = customer_scope("owner-a@example.com", CustomerMembership.Role.OWNER)
    _, other_customer, _ = customer_scope("owner-b@example.com", CustomerMembership.Role.OWNER)
    client.force_login(owner)
    url = reverse("portal:client-team", kwargs={"customer_public_id": other_customer.public_id})
    assert client.get(url).status_code == 403


@pytest.mark.django_db
def test_invitation_is_single_use_and_existing_user_must_authenticate(client):
    owner, customer, _ = customer_scope("owner@example.com", CustomerMembership.Role.OWNER)
    existing = User.objects.create_user(email="existing@example.com", password="pass")
    with patch("apps.notifications.tasks.send_customer_invitation_email_task.delay"):
        with TestCase.captureOnCommitCallbacks(execute=True):
            invitation = CustomerInvitationService().invite_collaborator(
                customer=customer,
                actor=owner,
                email=existing.email,
                role=CustomerMembership.Role.READONLY,
            )
    token = make_invitation_token(invitation)
    accept_url = reverse("portal:customer-invitation-accept", kwargs={"token": token})
    response = client.post(accept_url)
    assert response.status_code == 302
    assert response.url.startswith(reverse("portal:login"))

    client.force_login(existing)
    with patch("apps.notifications.tasks.send_account_activated_email_task.delay"):
        with TestCase.captureOnCommitCallbacks(execute=True):
            response = client.post(accept_url)
    assert response.status_code == 302
    assert CustomerMembership.objects.filter(
        customer=customer,
        user=existing,
        role=CustomerMembership.Role.READONLY,
    ).exists()
    assert client.get(accept_url).status_code == 400


@pytest.mark.django_db
def test_cross_org_membership_deactivation_is_blocked_by_route_scope(client):
    owner, customer, _ = customer_scope("owner-a@example.com", CustomerMembership.Role.OWNER)
    _, other_customer, other_membership = customer_scope(
        "member-b@example.com", CustomerMembership.Role.MEMBER
    )
    client.force_login(owner)
    url = reverse(
        "portal:client-team-member-deactivate",
        kwargs={
            "customer_public_id": other_customer.public_id,
            "membership_public_id": other_membership.public_id,
        },
    )
    assert client.post(url).status_code == 403
    other_membership.refresh_from_db()
    assert other_membership.is_active is True


@pytest.mark.django_db
def test_organization_admin_cannot_change_or_deactivate_peer_admin():
    admin, customer, _ = customer_scope("admin-a@example.com", CustomerMembership.Role.ADMIN)
    peer = User.objects.create_user(email="admin-b@example.com", password="pass")
    peer_membership = CustomerMembership.objects.create(
        customer=customer,
        user=peer,
        role=CustomerMembership.Role.ADMIN,
    )
    service = CustomerInvitationService()

    with pytest.raises(PermissionDenied):
        service.change_member_role(
            membership_public_id=peer_membership.public_id,
            customer=customer,
            actor=admin,
            role=CustomerMembership.Role.MEMBER,
        )
    with pytest.raises(PermissionDenied):
        service.deactivate_member(
            membership_public_id=peer_membership.public_id,
            customer=customer,
            actor=admin,
        )

    peer_membership.refresh_from_db()
    assert peer_membership.role == CustomerMembership.Role.ADMIN
    assert peer_membership.is_active is True
