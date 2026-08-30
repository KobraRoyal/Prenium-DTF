from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.models import BaseModel

from .managers import UserManager

STAFF_ROLE_OWNER = "owner"
STAFF_ROLE_ADMIN = "admin"
STAFF_ROLE_MEMBER = "member"
STAFF_ROLE_READONLY = "readonly"


class User(BaseModel, AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    staff_mfa_required = models.BooleanField(default=False)
    staff_mfa_enabled = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ("email",)
        permissions = [
            ("access_staff_portal", "Can access the staff portal"),
            ("manage_staff_team", "Can manage the workshop team"),
        ]

    def __str__(self) -> str:
        return self.email


class StaffMembershipQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True, user__is_active=True)


class StaffMembership(BaseModel):
    class Role(models.TextChoices):
        OWNER = STAFF_ROLE_OWNER, "Propriétaire"
        ADMIN = STAFF_ROLE_ADMIN, "Administrateur"
        MEMBER = STAFF_ROLE_MEMBER, "Collaborateur"
        READONLY = STAFF_ROLE_READONLY, "Lecture seule"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_membership",
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)
    is_active = models.BooleanField(default=True)

    objects = StaffMembershipQuerySet.as_manager()

    class Meta:
        ordering = ("user__email",)
        indexes = [
            models.Index(fields=("role", "is_active")),
        ]

    def __str__(self) -> str:
        return f"{self.user} ({self.role})"

    @property
    def is_owner(self) -> bool:
        return self.role == self.Role.OWNER

    @property
    def can_manage_team(self) -> bool:
        return self.role in {self.Role.OWNER, self.Role.ADMIN}


class StaffInvitation(BaseModel):
    """Invitation à rejoindre l'équipe Atelier (organisation unique)."""

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        ACCEPTED = "accepted", "Acceptée"
        REVOKED = "revoked", "Révoquée"
        EXPIRED = "expired", "Expirée"

    email = models.EmailField()
    role = models.CharField(
        max_length=16,
        choices=StaffMembership.Role.choices,
        default=StaffMembership.Role.MEMBER,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_invitations_sent",
    )
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_invitations_accepted",
    )
    token_version = models.PositiveIntegerField(default=1)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("email",),
                condition=models.Q(status="pending"),
                name="uniq_pending_staff_invitation_email",
            ),
        ]
        indexes = [
            models.Index(fields=("status", "created_at")),
            models.Index(fields=("email", "status")),
        ]

    def __str__(self) -> str:
        return f"{self.email} ({self.role})"
