from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.customers.models import Customer, CustomerInvitation, CustomerMembership

User = get_user_model()
INVITATION_TOKEN_SALT = "prenium.customer.invitation.v1"
INVITATION_MAX_AGE_SECONDS = 72 * 60 * 60


class CustomerInvitationError(Exception):
    """Erreur métier neutre pour une invitation d'organisation."""


class ExistingAccountLoginRequired(CustomerInvitationError):
    pass


def make_invitation_token(invitation: CustomerInvitation) -> str:
    return signing.dumps(
        {"invitation": str(invitation.public_id), "version": invitation.token_version},
        salt=INVITATION_TOKEN_SALT,
        compress=True,
    )


class CustomerInvitationService:
    """Création, acceptation et révocation d'invitations organisationnelles."""

    def resolve_token(self, token: str, *, for_update: bool = False) -> CustomerInvitation:
        try:
            payload = signing.loads(
                token,
                salt=INVITATION_TOKEN_SALT,
                max_age=INVITATION_MAX_AGE_SECONDS,
            )
        except signing.BadSignature as exc:
            raise CustomerInvitationError("Cette invitation est invalide ou expirée.") from exc
        if not isinstance(payload, dict):
            raise CustomerInvitationError("Cette invitation est invalide ou expirée.")
        queryset = CustomerInvitation.objects.select_related("customer", "invited_by")
        if for_update:
            # Verrouiller uniquement l'invitation : invited_by est nullable et son
            # OUTER JOIN ne peut pas être ciblé par un FOR UPDATE PostgreSQL.
            queryset = queryset.select_for_update(of=("self",))
        invitation = queryset.filter(public_id=payload.get("invitation")).first()
        if (
            invitation is None
            or invitation.token_version != payload.get("version")
            or invitation.status != CustomerInvitation.Status.PENDING
        ):
            raise CustomerInvitationError("Cette invitation est invalide ou expirée.")
        if invitation.expires_at <= timezone.now():
            invitation.status = CustomerInvitation.Status.EXPIRED
            invitation.save(update_fields=("status", "updated_at"))
            raise CustomerInvitationError("Cette invitation est invalide ou expirée.")
        return invitation

    @transaction.atomic
    def create_owner_activation(
        self, *, customer: Customer, email: str, actor
    ) -> CustomerInvitation:
        invitation = CustomerInvitation.objects.create(
            customer=customer,
            email=email.strip().lower(),
            role=CustomerMembership.Role.OWNER,
            kind=CustomerInvitation.Kind.OWNER_ACTIVATION,
            invited_by=actor,
            expires_at=timezone.now() + timedelta(hours=72),
            last_sent_at=timezone.now(),
        )
        from apps.notifications.services.transactional import (
            schedule_access_request_approved_email,
        )

        schedule_access_request_approved_email(invitation_public_id=invitation.public_id)
        return invitation

    def _actor_membership(self, *, customer: Customer, actor) -> CustomerMembership:
        membership = (
            CustomerMembership.objects.active().filter(customer=customer, user=actor).first()
        )
        if membership is None or not membership.can_manage_team:
            raise PermissionDenied
        return membership

    @transaction.atomic
    def invite_collaborator(
        self,
        *,
        customer: Customer,
        actor,
        email: str,
        role: str,
        ip_address: str | None = None,
    ) -> CustomerInvitation:
        actor_membership = self._actor_membership(customer=customer, actor=actor)
        if role == CustomerMembership.Role.OWNER or role not in CustomerMembership.Role.values:
            raise CustomerInvitationError("Ce rôle ne peut pas être attribué par invitation.")
        if (
            actor_membership.role == CustomerMembership.Role.ADMIN
            and role == CustomerMembership.Role.ADMIN
        ):
            raise PermissionDenied
        normalized_email = email.strip().lower()
        if CustomerMembership.objects.filter(
            customer=customer,
            user__email__iexact=normalized_email,
            is_active=True,
        ).exists():
            raise CustomerInvitationError("Cette personne appartient déjà à l'organisation.")
        if CustomerInvitation.objects.filter(
            customer=customer,
            email__iexact=normalized_email,
            status=CustomerInvitation.Status.PENDING,
        ).exists():
            raise CustomerInvitationError("Une invitation est déjà en attente pour cette adresse.")

        invitation = CustomerInvitation.objects.create(
            customer=customer,
            email=normalized_email,
            role=role,
            kind=CustomerInvitation.Kind.COLLABORATOR,
            invited_by=actor,
            expires_at=timezone.now() + timedelta(hours=72),
            last_sent_at=timezone.now(),
        )
        record_event(
            action="customer.invitation.created",
            actor=actor,
            target=invitation,
            ip_address=ip_address,
            metadata={"customer_public_id": str(customer.public_id), "role": role},
        )
        from apps.notifications.services.transactional import schedule_customer_invitation_email

        schedule_customer_invitation_email(invitation_public_id=invitation.public_id)
        return invitation

    @transaction.atomic
    def accept(
        self,
        *,
        token: str,
        authenticated_user=None,
        password: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[object, CustomerMembership]:
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
                raise CustomerInvitationError("Choisissez un mot de passe pour activer le compte.")
            profile = None
            if invitation.kind == CustomerInvitation.Kind.OWNER_ACTIVATION:
                from apps.prospects.models import ProspectProfile

                profile = ProspectProfile.objects.filter(customer=invitation.customer).first()
            user = User.objects.create_user(
                email=invitation.email,
                password=password,
                first_name=profile.first_name if profile is not None else "",
                last_name=profile.last_name if profile is not None else "",
            )

        membership, created = CustomerMembership.objects.get_or_create(
            customer=invitation.customer,
            user=user,
            defaults={"role": invitation.role, "is_active": True},
        )
        if not created:
            membership.role = invitation.role
            membership.is_active = True
            membership.save(update_fields=("role", "is_active", "updated_at"))
        invitation.status = CustomerInvitation.Status.ACCEPTED
        invitation.accepted_by = user
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=("status", "accepted_by", "accepted_at", "updated_at"))

        if invitation.kind == CustomerInvitation.Kind.OWNER_ACTIVATION:
            invitation.customer.is_active = True
            invitation.customer.save(update_fields=("is_active", "updated_at"))
            from apps.prospects.models import ProspectProfile

            profile = ProspectProfile.objects.select_for_update().get(customer=invitation.customer)
            profile.user = user
            profile.status = ProspectProfile.Status.ACTIVE
            profile.is_open = False
            profile.activated_at = timezone.now()
            profile.save(update_fields=("user", "status", "is_open", "activated_at", "updated_at"))
        record_event(
            action="customer.invitation.accepted",
            actor=user,
            target=invitation,
            ip_address=ip_address,
            metadata={
                "customer_public_id": str(invitation.customer.public_id),
                "role": invitation.role,
            },
        )
        from apps.notifications.services.transactional import schedule_account_activated_email

        schedule_account_activated_email(invitation_public_id=invitation.public_id)
        return user, membership

    @transaction.atomic
    def revoke(
        self,
        *,
        invitation_public_id,
        customer: Customer,
        actor,
        ip_address: str | None = None,
    ) -> CustomerInvitation:
        self._actor_membership(customer=customer, actor=actor)
        invitation = (
            CustomerInvitation.objects.select_for_update()
            .filter(
                public_id=invitation_public_id,
                customer=customer,
                kind=CustomerInvitation.Kind.COLLABORATOR,
            )
            .first()
        )
        if invitation is None or invitation.status != CustomerInvitation.Status.PENDING:
            raise CustomerInvitationError("Cette invitation ne peut plus être révoquée.")
        invitation.status = CustomerInvitation.Status.REVOKED
        invitation.revoked_at = timezone.now()
        invitation.token_version += 1
        invitation.save(update_fields=("status", "revoked_at", "token_version", "updated_at"))
        record_event(
            action="customer.invitation.revoked",
            actor=actor,
            target=invitation,
            ip_address=ip_address,
            metadata={"customer_public_id": str(customer.public_id)},
        )
        return invitation

    @transaction.atomic
    def change_member_role(
        self,
        *,
        membership_public_id,
        customer: Customer,
        actor,
        role: str,
        ip_address: str | None = None,
    ) -> CustomerMembership:
        actor_membership = self._actor_membership(customer=customer, actor=actor)
        membership = (
            CustomerMembership.objects.select_for_update()
            .filter(
                public_id=membership_public_id,
                customer=customer,
            )
            .first()
        )
        if membership is None:
            raise CustomerInvitationError("Ce membre est introuvable.")
        if (
            membership.role == CustomerMembership.Role.OWNER
            or role == CustomerMembership.Role.OWNER
            or membership.user_id == actor.pk
        ):
            raise PermissionDenied
        if actor_membership.role == CustomerMembership.Role.ADMIN and (
            membership.role == CustomerMembership.Role.ADMIN
            or role == CustomerMembership.Role.ADMIN
        ):
            raise PermissionDenied
        if role not in CustomerMembership.Role.values:
            raise CustomerInvitationError("Rôle inconnu.")
        previous_role = membership.role
        membership.role = role
        membership.save(update_fields=("role", "updated_at"))
        record_event(
            action="customer.membership.role_changed",
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
        customer: Customer,
        actor,
        ip_address: str | None = None,
    ) -> CustomerMembership:
        actor_membership = self._actor_membership(customer=customer, actor=actor)
        membership = (
            CustomerMembership.objects.select_for_update()
            .filter(
                public_id=membership_public_id,
                customer=customer,
            )
            .first()
        )
        if membership is None:
            raise CustomerInvitationError("Ce membre est introuvable.")
        if (
            membership.role == CustomerMembership.Role.OWNER
            or membership.user_id == actor.pk
            or (
                actor_membership.role == CustomerMembership.Role.ADMIN
                and membership.role == CustomerMembership.Role.ADMIN
            )
        ):
            raise PermissionDenied
        membership.is_active = False
        membership.save(update_fields=("is_active", "updated_at"))
        record_event(
            action="customer.membership.deactivated",
            actor=actor,
            target=membership,
            ip_address=ip_address,
            metadata={"customer_public_id": str(customer.public_id)},
        )
        return membership
