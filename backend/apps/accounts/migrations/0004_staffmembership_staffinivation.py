import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def bootstrap_staff_team(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    StaffMembership = apps.get_model("accounts", "StaffMembership")
    Permission = apps.get_model("auth", "Permission")

    manage_team_perm = Permission.objects.filter(
        codename="manage_staff_team",
        content_type__app_label="accounts",
    ).first()

    for user in User.objects.filter(is_active=True, is_superuser=True):
        membership, _ = StaffMembership.objects.get_or_create(
            user=user,
            defaults={"role": "owner", "is_active": True},
        )
        if membership.role != "owner":
            membership.role = "owner"
            membership.is_active = True
            membership.save(update_fields=["role", "is_active", "updated_at"])

    for user in User.objects.filter(is_active=True, is_staff=True, is_superuser=False):
        StaffMembership.objects.get_or_create(
            user=user,
            defaults={"role": "member", "is_active": True},
        )

    if manage_team_perm is not None:
        for membership in StaffMembership.objects.filter(
            role__in=("owner", "admin"),
            is_active=True,
        ).select_related("user"):
            user = membership.user
            if user.is_superuser:
                continue
            user.user_permissions.add(manage_team_perm)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_alter_user_options_user_staff_mfa_enabled_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="user",
            options={
                "ordering": ("email",),
                "permissions": [
                    ("access_staff_portal", "Can access the staff portal"),
                    ("manage_staff_team", "Can manage the workshop team"),
                ],
            },
        ),
        migrations.CreateModel(
            name="StaffMembership",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "public_id",
                    models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("owner", "Propriétaire"),
                            ("admin", "Administrateur"),
                            ("member", "Collaborateur"),
                            ("readonly", "Lecture seule"),
                        ],
                        default="member",
                        max_length=16,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_membership",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("user__email",),
            },
        ),
        migrations.CreateModel(
            name="StaffInvitation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "public_id",
                    models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
                ),
                ("email", models.EmailField(max_length=254)),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("owner", "Propriétaire"),
                            ("admin", "Administrateur"),
                            ("member", "Collaborateur"),
                            ("readonly", "Lecture seule"),
                        ],
                        default="member",
                        max_length=16,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "En attente"),
                            ("accepted", "Acceptée"),
                            ("revoked", "Révoquée"),
                            ("expired", "Expirée"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("token_version", models.PositiveIntegerField(default=1)),
                ("expires_at", models.DateTimeField()),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("last_sent_at", models.DateTimeField(blank=True, null=True)),
                (
                    "accepted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="staff_invitations_accepted",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "invited_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="staff_invitations_sent",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="staffmembership",
            index=models.Index(fields=["role", "is_active"], name="accounts_st_role_4b0f0d_idx"),
        ),
        migrations.AddIndex(
            model_name="staffinvitation",
            index=models.Index(fields=["status", "created_at"], name="accounts_st_status_8d2f1a_idx"),
        ),
        migrations.AddIndex(
            model_name="staffinvitation",
            index=models.Index(fields=["email", "status"], name="accounts_st_email_91ac3b_idx"),
        ),
        migrations.AddConstraint(
            model_name="staffinvitation",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "pending")),
                fields=("email",),
                name="uniq_pending_staff_invitation_email",
            ),
        ),
        migrations.RunPython(bootstrap_staff_team, migrations.RunPython.noop),
    ]
