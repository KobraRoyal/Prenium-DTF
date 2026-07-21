from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel

MIN_MM = Decimal("0.01")
ZERO = Decimal("0.00")


def gang_sheet_preview_path(instance, _filename: str) -> str:
    return (
        f"gang-sheets/{instance.customer.public_id}/{instance.public_id}/"
        f"preview-r{instance.revision}.png"
    )


def gang_sheet_final_path(instance, _filename: str) -> str:
    return (
        f"gang-sheets/{instance.customer.public_id}/{instance.public_id}/"
        f"production-r{instance.revision}.pdf"
    )


class GangSheetSiteSettings(BaseModel):
    """Configuration globale pilotée par l'atelier.

    Chaque planche en conserve un instantané pour empêcher qu'un changement de
    machine modifie silencieusement un brouillon existant.
    """

    singleton = models.BooleanField(default=True, unique=True, editable=False)
    roll_width_mm = models.DecimalField(
        "Laize utile (mm)",
        max_digits=8,
        decimal_places=2,
        default=Decimal("550.00"),
        validators=[MinValueValidator(Decimal("100.00")), MaxValueValidator(Decimal("2000.00"))],
    )
    margin_mm = models.DecimalField(
        "Marge de sécurité (mm)",
        max_digits=6,
        decimal_places=2,
        default=Decimal("5.00"),
        validators=[MinValueValidator(ZERO), MaxValueValidator(Decimal("100.00"))],
    )
    item_spacing_mm = models.DecimalField(
        "Espacement entre visuels (mm)",
        max_digits=6,
        decimal_places=2,
        default=Decimal("3.00"),
        validators=[MinValueValidator(ZERO), MaxValueValidator(Decimal("100.00"))],
    )
    minimum_height_mm = models.DecimalField(
        "Hauteur minimale (mm)",
        max_digits=9,
        decimal_places=2,
        default=Decimal("100.00"),
        validators=[MinValueValidator(Decimal("10.00"))],
    )
    maximum_height_mm = models.DecimalField(
        "Hauteur maximale (mm)",
        max_digits=9,
        decimal_places=2,
        default=Decimal("2000.00"),
        validators=[MinValueValidator(Decimal("10.00"))],
    )
    height_step_mm = models.DecimalField(
        "Pas d'arrondi de hauteur (mm)",
        max_digits=6,
        decimal_places=2,
        default=Decimal("10.00"),
        validators=[MinValueValidator(Decimal("1.00"))],
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_gang_sheet_settings",
    )

    class Meta:
        verbose_name = "Réglages Gang Sheet"
        verbose_name_plural = "Réglages Gang Sheet"

    def clean(self):
        super().clean()
        if self.maximum_height_mm <= self.minimum_height_mm:
            raise ValidationError(
                {"maximum_height_mm": "La hauteur maximale doit dépasser la hauteur minimale."}
            )
        if self.margin_mm * 2 >= self.roll_width_mm:
            raise ValidationError({"margin_mm": "Les marges doivent laisser une largeur utile."})

    @classmethod
    def current(cls):
        obj, _created = cls.objects.get_or_create(singleton=True)
        return obj

    def __str__(self) -> str:
        return f"Laize {self.roll_width_mm} mm"


class GangSheetQuerySet(models.QuerySet):
    def for_customer(self, customer):
        return self.filter(customer=customer)

    def for_project(self, project):
        return self.filter(customer=project.customer, project=project)

    def for_order(self, order):
        return self.filter(customer=order.customer, order=order)

    def for_user(self, user):
        if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
            return self.none()
        return self.filter(
            customer__memberships__user=user,
            customer__memberships__is_active=True,
            customer__is_active=True,
        ).distinct()


class GangSheet(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Brouillon"
        RENDERING = "rendering", "Rendu en cours"
        READY = "ready", "Rendu prêt"
        VALIDATED = "validated", "Validée"
        RENDER_FAILED = "render_failed", "Échec du rendu"

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="gang_sheets"
    )
    project = models.ForeignKey(
        "b2b_order_projects.B2BOrderProject",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gang_sheets",
    )
    production_asset = models.OneToOneField(
        "uploads.Asset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_gang_sheet",
        help_text="PDF final injecté dans le projet de commande après validation.",
    )
    order = models.ForeignKey(
        "orders.Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gang_sheets",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_gang_sheets",
    )
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="validated_gang_sheets",
    )
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    width_mm = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(MIN_MM)]
    )
    height_mm = models.DecimalField(
        max_digits=9, decimal_places=2, validators=[MinValueValidator(MIN_MM)]
    )
    minimum_height_mm = models.DecimalField(
        max_digits=9,
        decimal_places=2,
        default=Decimal("100.00"),
        validators=[MinValueValidator(MIN_MM)],
    )
    maximum_height_mm = models.DecimalField(
        max_digits=9, decimal_places=2, validators=[MinValueValidator(MIN_MM)]
    )
    height_step_mm = models.DecimalField(
        max_digits=6, decimal_places=2, validators=[MinValueValidator(MIN_MM)]
    )
    margin_mm = models.DecimalField(
        max_digits=6, decimal_places=2, default=ZERO, validators=[MinValueValidator(ZERO)]
    )
    item_spacing_mm = models.DecimalField(
        max_digits=6, decimal_places=2, default=ZERO, validators=[MinValueValidator(ZERO)]
    )
    surface_sqm = models.DecimalField(
        max_digits=12, decimal_places=4, default=ZERO, validators=[MinValueValidator(ZERO)]
    )
    unit_price_eur = models.DecimalField(
        max_digits=10, decimal_places=2, default=ZERO, validators=[MinValueValidator(ZERO)]
    )
    estimated_price_eur = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO, validators=[MinValueValidator(ZERO)]
    )
    preview_file = models.FileField(upload_to=gang_sheet_preview_path, max_length=500, blank=True)
    final_file = models.FileField(upload_to=gang_sheet_final_path, max_length=500, blank=True)
    render_error = models.CharField(max_length=255, blank=True)
    render_requested_at = models.DateTimeField(null=True, blank=True)
    rendered_at = models.DateTimeField(null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    objects = GangSheetQuerySet.as_manager()

    class Meta:
        ordering = ("-updated_at", "-created_at")
        permissions = [
            ("download_final_gangsheet", "Can download final production gang sheet"),
            ("configure_gangsheet", "Can configure gang sheet generator"),
        ]
        indexes = [
            models.Index(fields=("customer", "status", "updated_at")),
            models.Index(fields=("customer", "project", "created_at")),
            models.Index(fields=("order", "status")),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(width_mm__gt=0), name="gangsheet_width_gt_0"),
            models.CheckConstraint(
                condition=models.Q(height_mm__gt=0), name="gangsheet_height_gt_0"
            ),
        ]

    def clean(self):
        super().clean()
        if self.customer_id and self.project_id and self.customer_id != self.project.customer_id:
            raise ValidationError(
                {"project": "La planche et le projet doivent avoir le même client."}
            )
        if self.customer_id and self.order_id and self.customer_id != self.order.customer_id:
            raise ValidationError(
                {"order": "La planche et la commande doivent avoir le même client."}
            )

    def __str__(self) -> str:
        return f"{self.name} — {self.width_mm} × {self.height_mm} mm"


class GangSheetDriveSyncQuerySet(models.QuerySet):
    def for_customer(self, customer):
        return self.filter(customer=customer)

    def for_sheet(self, sheet):
        return self.filter(customer=sheet.customer, gang_sheet=sheet)


class GangSheetDriveSync(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        SYNCED = "synced", "Synchronisé"
        FAILED = "failed", "Échec"

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="gang_sheet_drive_syncs",
    )
    gang_sheet = models.OneToOneField(
        GangSheet,
        on_delete=models.CASCADE,
        related_name="drive_sync",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    revision = models.PositiveIntegerField(default=0)
    drive_filename = models.CharField(max_length=255, blank=True)
    remote_folder_id = models.CharField(max_length=255, blank=True)
    drive_file_id = models.CharField(max_length=255, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    last_error = models.CharField(max_length=255, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)

    objects = GangSheetDriveSyncQuerySet.as_manager()

    class Meta:
        ordering = ("-updated_at", "-created_at")
        indexes = [
            models.Index(
                fields=("customer", "status", "updated_at"),
                name="gang_drive_customer_status_idx",
            ),
            models.Index(
                fields=("status", "last_attempt_at"),
                name="gang_drive_status_attempt_idx",
            ),
        ]

    def clean(self):
        super().clean()
        if self.customer_id and self.gang_sheet_id:
            if self.customer_id != self.gang_sheet.customer_id:
                raise ValidationError(
                    {"gang_sheet": "La synchronisation Drive doit appartenir au même client."}
                )

    def google_drive_browser_url(self) -> str | None:
        if not self.drive_file_id:
            return None
        return f"https://drive.google.com/file/d/{self.drive_file_id}/view"

    def __str__(self) -> str:
        return f"{self.gang_sheet} — {self.get_status_display()}"


class GangSheetSourceAssetQuerySet(models.QuerySet):
    def for_sheet(self, sheet):
        return self.filter(customer=sheet.customer, sheet=sheet)

    def for_customer(self, customer):
        return self.filter(customer=customer)


class GangSheetSourceAsset(BaseModel):
    """Fichier source importé dans la galerie autonome d'une planche."""

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="gang_sheet_source_assets",
    )
    sheet = models.ForeignKey(
        GangSheet,
        on_delete=models.CASCADE,
        related_name="source_assets",
    )
    asset = models.ForeignKey(
        "uploads.Asset",
        on_delete=models.PROTECT,
        related_name="gang_sheet_sources",
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="added_gang_sheet_source_assets",
    )
    width_mm = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(MIN_MM)],
    )
    height_mm = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(MIN_MM)],
    )
    sort_order = models.PositiveIntegerField(default=1)

    objects = GangSheetSourceAssetQuerySet.as_manager()

    class Meta:
        ordering = ("sort_order", "created_at")
        constraints = [
            models.UniqueConstraint(fields=("sheet", "asset"), name="uniq_gang_source_asset"),
            models.CheckConstraint(
                condition=(
                    models.Q(width_mm__isnull=True, height_mm__isnull=True)
                    | models.Q(width_mm__isnull=False, height_mm__isnull=False)
                ),
                name="gang_source_dimensions_pair",
            ),
        ]
        indexes = [
            models.Index(fields=("customer", "sheet", "sort_order")),
            models.Index(fields=("customer", "asset")),
        ]

    def clean(self):
        super().clean()
        if self.customer_id and self.sheet_id and self.customer_id != self.sheet.customer_id:
            raise ValidationError(
                {"sheet": "La galerie et la planche doivent avoir le même client."}
            )
        if self.customer_id and self.asset_id and self.customer_id != self.asset.customer_id:
            raise ValidationError({"asset": "Le fichier doit appartenir au même client."})

    def __str__(self) -> str:
        return f"{self.sheet.name} — {self.asset.name}"


class GangSheetItemQuerySet(models.QuerySet):
    def for_sheet(self, sheet):
        return self.filter(customer=sheet.customer, sheet=sheet)

    def for_customer(self, customer):
        return self.filter(customer=customer)


class GangSheetItem(BaseModel):
    class Rotation(models.IntegerChoices):
        DEG_0 = 0, "0°"
        DEG_90 = 90, "90°"
        DEG_180 = 180, "180°"
        DEG_270 = 270, "270°"

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="gang_sheet_items"
    )
    sheet = models.ForeignKey(GangSheet, on_delete=models.CASCADE, related_name="items")
    asset_version = models.ForeignKey(
        "uploads.AssetVersion", on_delete=models.PROTECT, related_name="gang_sheet_items"
    )
    x_mm = models.DecimalField(max_digits=9, decimal_places=2, default=ZERO)
    y_mm = models.DecimalField(max_digits=9, decimal_places=2, default=ZERO)
    width_mm = models.DecimalField(
        max_digits=9, decimal_places=2, validators=[MinValueValidator(MIN_MM)]
    )
    height_mm = models.DecimalField(
        max_digits=9, decimal_places=2, validators=[MinValueValidator(MIN_MM)]
    )
    rotation = models.PositiveSmallIntegerField(choices=Rotation.choices, default=Rotation.DEG_0)
    z_index = models.PositiveIntegerField(default=1)

    objects = GangSheetItemQuerySet.as_manager()

    class Meta:
        ordering = ("z_index", "created_at")
        indexes = [
            models.Index(fields=("customer", "sheet", "z_index")),
            models.Index(fields=("customer", "asset_version")),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(width_mm__gt=0), name="gangitem_width_gt_0"),
            models.CheckConstraint(
                condition=models.Q(height_mm__gt=0), name="gangitem_height_gt_0"
            ),
            models.UniqueConstraint(fields=("sheet", "z_index"), name="uniq_gangitem_sheet_z"),
        ]

    @property
    def effective_width_mm(self) -> Decimal:
        return self.height_mm if self.rotation in {90, 270} else self.width_mm

    @property
    def effective_height_mm(self) -> Decimal:
        return self.width_mm if self.rotation in {90, 270} else self.height_mm

    def clean(self):
        super().clean()
        if self.customer_id and self.sheet_id and self.customer_id != self.sheet.customer_id:
            raise ValidationError(
                {"sheet": "L'occurrence et la planche doivent avoir le même client."}
            )
        if (
            self.customer_id
            and self.asset_version_id
            and self.customer_id != self.asset_version.customer_id
        ):
            raise ValidationError(
                {"asset_version": "Le fichier doit appartenir au même client que la planche."}
            )

    def __str__(self) -> str:
        return f"{self.asset_version.asset.name} sur {self.sheet.name}"
