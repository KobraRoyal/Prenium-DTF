from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import StaffInvitation, StaffMembership
from apps.accounts.services.staff_roles import sync_staff_access
from apps.auditlog.services import record_event

User = get_user_model()
INVITATION_TOKEN_SALT = "prenium.staff.invitation.v1"
INVITATION_MAX_AGE_SECONDS = 72 * 60 * 60


class StaffInvitationError(Exception):
    """Erreur métier neutre pour une invitation Atelier."""


class ExistingAccountLoginRequired(StaffInvitationError):
    pass


def make_invitation_token(invitation: StaffInvitation) -> str:
    return signing.dumps(
        {"invitation": str(invitation.public_id), "version": invitation.token_version},
        salt=INVITATION_TOKEN_SALT,
        compress=True,
    )


class StaffInvitationService:
    """Création, acceptation et révocation d'invitations Atelier."""

    def resolve_token(self, token: str, *, for_update: bool = False) -> StaffInvitation:
        try:
            payload = signing.loads(
                token,
                salt=INVITATION_TOKEN_SALT,
                max_age=INVITATION_MAX_AGE_SECONDS,
            )
        except signing.BadSignature as exc:
            raise StaffInvitationError("Cette invitation est invalide ou expirée.") from exc
        if not isinstance(payload, dict):
            raise StaffInvitationError("Cette invitation est invalide ou expirée.")
        queryset = StaffInvitation.objects.select_related("invited_by")
        if for_update:
            queryset = queryset.select_for_update(of=("self",))
        invitation = queryset.filter(public_id=payload.get("invitation")).first()
        if (
            invitation is None
            or invitation.token_version != payload.get("version")
            or invitation.status != StaffInvitation.Status.PENDING
        ):
            raise StaffInvitationError("Cette invitation est invalide ou expirée.")
        if invitation.expires_at <= timezone.now():
            invitation.status = StaffInvitation.Status.EXPIRED
            invitation.save(update_fields=("status", "updated_at"))
            raise StaffInvitationError("Cette invitation est invalide ou expirée.")
        return invitation

    def _actor_membership(self, *, actor) -> StaffMembership:
        membership = StaffMembership.objects.active().filter(user=actor).first()
        if membership is None or not membership.can_manage_team:
            raise PermissionDenied
        return membership

    @transaction.atomic
    def invite_collaborator(
        self,
        *,
        actor,
        email: str,
        role: str,
        ip_address: str | None = None,
    ) -> StaffInvitation:
        actor_membership = self._actor_membership(actor=actor)
        if role == StaffMembership.Role.OWNER or role not in StaffMembership.Role.values:
            raise StaffInvitationError("Ce rôle ne peut pas être attribué par invitation.")
        if (
            actor_membership.role == StaffMembership.Role.ADMIN
            and role == StaffMembership.Role.ADMIN
        ):
            raise PermissionDenied
        normalized_email = email.strip().lower()
        if StaffMembership.objects.filter(
            user__email__iexact=normalized_email,
            is_active=True,
        ).exists():
            raise StaffInvitationError("Cette personne appartient déjà à l'équipe Atelier.")
        if StaffInvitation.objects.filter(
            email__iexact=normalized_email,
            status=StaffInvitation.Status.PENDING,
        ).exists():
            raise StaffInvitationError("Une invitation est déjà en attente pour cette adresse.")

        invitation = StaffInvitation.objects.create(
            email=normalized_email,
            role=role,
            invited_by=actor,
            expires_at=timezone.now() + timedelta(hours=72),
            last_sent_at=timezone.now(),
        )
        record_event(
            action="staff.invitation.created",
            actor=actor,
            target=invitation,
            ip_address=ip_address,
            metadata={"role": role},
        )
        from apps.notifications.services.transactional import schedule_staff_invitation_email

        schedule_staff_invitation_email(invitation_public_id=invitation.public_id)
        return invitation

    @transaction.atomic
    def accept(
        self,
        *,
        token: str,
        authenticated_user=None,
        password: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[object, StaffMembership]:
        invitation = self.resolve_token(token, for_update=True)
        existing_user = User.objects.filter(email__iexact=invitation.email).first()
        if existing_user is not None:
            if (
                authenticated_user is None
                or not getattr(authenticated_user, "is_authenticated", False)
                or authenticated_user.pk != existing_user.pk
            ):
                raise ExistingAccountLoginRequired(
                    "Connectez-vous avec l'adresse invitée pour accepter cette invitation."
                )
            user = existing_user
        else:
            if not password:
                raise StaffInvitationError("Choisissez un mot de passe pour activer le compte.")
            user = User.objects.create_user(email=invitation.email, password=password)

        membership, created = StaffMembership.objects.get_or_create(
            user=user,
            defaults={"role": invitation.role, "is_active": True},
        )
        if not created:
            membership.role = invitation.role
            membership.is_active = True
            membership.save(update_fields=("role", "is_active", "updated_at"))

        sync_staff_access(user=user, role=membership.role, is_active=True)

        invitation.status = StaffInvitation.Status.ACCEPTED
        invitation.accepted_by = user
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=("status", "accepted_by", "accepted_at", "updated_at"))

        record_event(
            action="staff.invitation.accepted",
            actor=user,
            target=invitation,
            ip_address=ip_address,
            metadata={"role": invitation.role},
        )
        from apps.notifications.services.transactional import schedule_staff_account_activated_email

        schedule_staff_account_activated_email(invitation_public_id=invitation.public_id)
        return user, membership

    @transaction.atomic
    def revoke(
        self,
        *,
        invitation_public_id,
        actor,
        ip_address: str | None = None,
    ) -> StaffInvitation:
        self._actor_membership(actor=actor)
        invitation = (
            StaffInvitation.objects.select_for_update()
            .filter(public_id=invitation_public_id)
            .first()
        )
        if invitation is None or invitation.status != StaffInvitation.Status.PENDING:
            raise StaffInvitationError("Cette invitation ne peut plus être révoquée.")
        invitation.status = StaffInvitation.Status.REVOKED
        invitation.revoked_at = timezone.now()
        invitation.token_version += 1
        invitation.save(update_fields=("status", "revoked_at", "token_version", "updated_at"))
        record_event(
            action="staff.invitation.revoked",
            actor=actor,
            target=invitation,
            ip_address=ip_address,
        )
        return invitation

    @transaction.atomic
    def change_member_role(
        self,
        *,
        membership_public_id,
        actor,
        role: str,
        ip_address: str | None = None,
    ) -> StaffMembership:
        actor_membership = self._actor_membership(actor=actor)
        membership = (
            StaffMembership.objects.select_for_update()
            .filter(public_id=membership_public_id)
            .first()
        )
        if membership is None:
            raise StaffInvitationError("Ce membre est introuvable.")
        if (
            membership.role == StaffMembership.Role.OWNER
            or role == StaffMembership.Role.OWNER
            or membership.user_id == actor.pk
        ):
            raise PermissionDenied
        if actor_membership.role == StaffMembership.Role.ADMIN and (
            membership.role == StaffMembership.Role.ADMIN
            or role == StaffMembership.Role.ADMIN
        ):
            raise PermissionDenied
        if role not in StaffMembership.Role.values:
            raise StaffInvitationError("Rôle inconnu.")
        previous_role = membership.role
        membership.role = role
        membership.save(update_fields=("role", "updated_at"))
        sync_staff_access(user=membership.user, role=role, is_active=membership.is_active)
        record_event(
            action="staff.membership.role_changed",
            actor=actor,
            target=membership,
            ip_address=ip_address,
            metadata={"before": previous_role, "after": role},
        )
        return membership

    @transaction.atomic
    def deactivate_member(
        self,
        *,
        membership_public_id,
        actor,
        ip_address: str | None = None,
    ) -> StaffMembership:
        actor_membership = self._actor_membership(actor=actor)
        membership = (
            StaffMembership.objects.select_for_update()
            .filter(public_id=membership_public_id)
            .first()
        )
        if membership is None:
            raise StaffInvitationError("Ce membre est introuvable.")
        if (
            membership.role == StaffMembership.Role.OWNER
            or membership.user_id == actor.pk
            or (
                actor_membership.role == StaffMembership.Role.ADMIN
                and membership.role == StaffMembership.Role.ADMIN
            )
        ):
            raise PermissionDenied
        membership.is_active = False
        membership.save(update_fields=("is_active", "updated_at"))
        sync_staff_access(user=membership.user, role=membership.role, is_active=False)
        record_event(
            action="staff.membership.deactivated",
            actor=actor,
            target=membership,
            ip_address=ip_address,
        )
        return membership
