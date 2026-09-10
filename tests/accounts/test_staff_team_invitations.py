import base64
from unittest.mock import patch

import pytest
from apps.accounts.models import StaffInvitation, StaffMembership
from apps.accounts.services.staff_invitations import StaffInvitationService, make_invitation_token
from apps.accounts.services.staff_roles import sync_staff_access
from apps.notifications.tasks import send_staff_invitation_email_task
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

User = get_user_model()
WEB_PUSH_TEST_KEY = Fernet.generate_key().decode("ascii")
WEB_PUSH_TEST_P256DH = base64.urlsafe_b64encode(b"\x04" + (b"p" * 64)).rstrip(b"=").decode("ascii")
WEB_PUSH_TEST_AUTH = base64.urlsafe_b64encode(b"a" * 16).rstrip(b"=").decode("ascii")


def _grant_portal_access(user) -> None:
    permission = Permission.objects.get(
        codename="access_staff_portal",
        content_type__app_label="accounts",
    )
    user.user_permissions.add(permission)
    user.is_staff = True
    user.save(update_fields=("is_staff", "updated_at"))


def staff_scope(email: str, role: str, *, superuser: bool = False):
    user = User.objects.create_user(email=email, password="pass")
    if superuser:
        user.is_superuser = True
    _grant_portal_access(user)
    membership = StaffMembership.objects.create(user=user, role=role, is_active=True)
    sync_staff_access(user=user, role=role, is_active=True)
    return user, membership


@pytest.mark.django_db
def test_owner_can_invite_but_member_cannot_access_staff_team(client):
    owner, _ = staff_scope("owner@example.com", StaffMembership.Role.OWNER, superuser=True)
    member, _ = staff_scope("member@example.com", StaffMembership.Role.MEMBER)
    team_url = reverse("portal:staff-team")

    client.force_login(member)
    assert client.get(team_url).status_code == 403

    client.force_login(owner)
    team_page = client.get(team_url)
    assert team_page.status_code == 200
    team_html = team_page.content.decode()
    assert "Équipe Atelier" in team_html
    assert "Inviter un collaborateur" in team_html
    assert "Désactiver cet accès ?" in team_html

    with patch("apps.notifications.tasks.send_staff_invitation_email_task.delay") as delay:
        with TestCase.captureOnCommitCallbacks(execute=True):
            response = client.post(
                reverse("portal:staff-team-invite"),
                {"email": "new@example.com", "role": StaffMembership.Role.MEMBER},
            )
    assert response.status_code == 302
    invitation = StaffInvitation.objects.get(email="new@example.com")
    delay.assert_called_once_with(str(invitation.public_id))


@pytest.mark.django_db
def test_owner_invitation_htmx_refreshes_panel(client):
    owner, _ = staff_scope("owner-htmx@example.com", StaffMembership.Role.OWNER, superuser=True)
    client.force_login(owner)

    with patch("apps.notifications.tasks.send_staff_invitation_email_task.delay"):
        with TestCase.captureOnCommitCallbacks(execute=True):
            response = client.post(
                reverse("portal:staff-team-invite"),
                {"email": "collaborateur@example.com", "role": StaffMembership.Role.MEMBER},
                HTTP_HX_REQUEST="true",
            )

    html = response.content.decode()
    assert response.status_code == 200
    assert response["X-Prenium-Toast"]
    assert 'id="team-invite-panel"' in html
    assert "Invitation enregistrée" in html


@pytest.mark.django_db
@override_settings(
    TRANSACTIONAL_EMAILS_ENABLED=True,
    PUBLIC_BASE_URL="https://portal.example.test",
)
def test_registered_staff_invitation_task_delivers_the_secure_email():
    owner, _ = staff_scope("owner-mail@example.com", StaffMembership.Role.OWNER, superuser=True)
    with patch("apps.notifications.tasks.send_staff_invitation_email_task.delay"):
        with TestCase.captureOnCommitCallbacks(execute=True):
            invitation = StaffInvitationService().invite_collaborator(
                actor=owner,
                email="invitee@example.com",
                role=StaffMembership.Role.READONLY,
            )

    mail.outbox.clear()
    send_staff_invitation_email_task(str(invitation.public_id))

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["invitee@example.com"]
    assert "https://portal.example.test/acces/invitation-atelier/" in mail.outbox[0].body


@pytest.mark.django_db
def test_staff_invitation_requires_authentication_for_existing_user(client):
    owner, _ = staff_scope("owner@example.com", StaffMembership.Role.OWNER, superuser=True)
    existing = User.objects.create_user(email="existing@example.com", password="pass")
    with patch("apps.notifications.tasks.send_staff_invitation_email_task.delay"):
        with TestCase.captureOnCommitCallbacks(execute=True):
            invitation = StaffInvitationService().invite_collaborator(
                actor=owner,
                email=existing.email,
                role=StaffMembership.Role.READONLY,
            )
    token = make_invitation_token(invitation)
    accept_url = reverse("portal:staff-invitation-accept", kwargs={"token": token})
    response = client.post(accept_url)
    assert response.status_code == 302
    assert response.url.startswith(reverse("portal:login"))

    client.force_login(existing)
    with patch("apps.notifications.tasks.send_staff_account_activated_email_task.delay"):
        with TestCase.captureOnCommitCallbacks(execute=True):
            response = client.post(accept_url)
    assert response.status_code == 302
    membership = StaffMembership.objects.get(user=existing)
    assert membership.role == StaffMembership.Role.READONLY
    assert membership.is_active is True
    existing.refresh_from_db()
    assert existing.is_staff is True


@pytest.mark.django_db
def test_admin_cannot_change_or_deactivate_peer_admin():
    admin, _ = staff_scope("admin-a@example.com", StaffMembership.Role.ADMIN)
    peer = User.objects.create_user(email="admin-b@example.com", password="pass")
    _grant_portal_access(peer)
    peer_membership = StaffMembership.objects.create(
        user=peer,
        role=StaffMembership.Role.ADMIN,
        is_active=True,
    )
    sync_staff_access(user=peer, role=StaffMembership.Role.ADMIN, is_active=True)
    service = StaffInvitationService()

    with pytest.raises(PermissionDenied):
        service.change_member_role(
            membership_public_id=peer_membership.public_id,
            actor=admin,
            role=StaffMembership.Role.MEMBER,
        )
    with pytest.raises(PermissionDenied):
        service.deactivate_member(
            membership_public_id=peer_membership.public_id,
            actor=admin,
        )

    peer_membership.refresh_from_db()
    assert peer_membership.role == StaffMembership.Role.ADMIN
    assert peer_membership.is_active is True


@pytest.mark.django_db
@override_settings(
    WEB_PUSH_ENABLED=True,
    WEB_PUSH_VAPID_PUBLIC_KEY="public-test-key",
    WEB_PUSH_VAPID_PRIVATE_KEY="private-test-key",
    WEB_PUSH_VAPID_CONTACT="mailto:atelier@example.com",
    WEB_PUSH_ENCRYPTION_KEYS=[f"v1:{WEB_PUSH_TEST_KEY}"],
    WEB_PUSH_ALLOWED_DOMAINS=["fcm.googleapis.com"],
)
def test_staff_offboarding_erases_push_secrets_and_reactivation_requires_resubscribe():
    from apps.notifications.models import StaffPushSubscription
    from apps.notifications.services.push_crypto import PushSubscriptionCrypto
    from apps.notifications.services.workshop_push import WorkshopNotificationService

    owner, _ = staff_scope(
        "owner-offboarding@example.com", StaffMembership.Role.OWNER, superuser=True
    )
    member, membership = staff_scope("member-offboarding@example.com", StaffMembership.Role.MEMBER)
    endpoint = "https://fcm.googleapis.com/fcm/send/offboarding-token"
    crypto = PushSubscriptionCrypto([f"v1:{WEB_PUSH_TEST_KEY}"])
    subscription = StaffPushSubscription.objects.create(
        staff_membership=membership,
        endpoint_ciphertext=crypto.encrypt(endpoint),
        endpoint_digest=crypto.endpoint_digest(endpoint),
        p256dh_ciphertext=crypto.encrypt(WEB_PUSH_TEST_P256DH),
        auth_ciphertext=crypto.encrypt(WEB_PUSH_TEST_AUTH),
        last_seen_at=timezone.now(),
    )

    StaffInvitationService().deactivate_member(
        membership_public_id=membership.public_id,
        actor=owner,
    )

    subscription.refresh_from_db()
    assert subscription.is_active is False
    assert subscription.endpoint_ciphertext == ""
    assert subscription.p256dh_ciphertext == ""
    assert subscription.auth_ciphertext == ""

    with patch("apps.notifications.tasks.send_staff_invitation_email_task.delay"):
        with TestCase.captureOnCommitCallbacks(execute=True):
            invitation = StaffInvitationService().invite_collaborator(
                actor=owner,
                email=member.email,
                role=StaffMembership.Role.MEMBER,
            )
    token = make_invitation_token(invitation)
    with patch("apps.notifications.tasks.send_staff_account_activated_email_task.delay"):
        StaffInvitationService().accept(token=token, authenticated_user=member)

    subscription.refresh_from_db()
    assert subscription.is_active is False
    client = type(
        "Client", (), {"configuration": type("Config", (), {"validate": lambda self: None})()}
    )()
    service = WorkshopNotificationService(client=client)
    with patch(
        "apps.notifications.services.workshop_push.validate_push_endpoint",
        return_value=endpoint,
    ):
        resubscribed = service.subscribe(
            actor=member,
            endpoint=endpoint,
            p256dh=WEB_PUSH_TEST_P256DH,
            auth=WEB_PUSH_TEST_AUTH,
            source="portal",
        )

    assert resubscribed.public_id == subscription.public_id
    assert resubscribed.is_active is True
    assert resubscribed.endpoint_ciphertext
