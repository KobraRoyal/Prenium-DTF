import os
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.utils import validate_file_name
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.text import get_valid_filename

from apps.core.models import BaseModel
from apps.orders.models import Order

ZERO_AMOUNT = Decimal("0.00")
MIN_QTY = 1
MIN_METERAGE_OVERRIDE_SQMS = Decimal("0.0001")
MIN_METERAGE_OVERRIDE_LINEAR_M = Decimal("0.0001")


def normalize_original_filename(filename: str) -> str:
    original_name = os.path.basename(str(filename).replace("\\", "/")).strip()
    if not original_name:
        return "upload"
    validate_file_name(original_name, allow_relative_path=False)
    return original_name


def order_upload_path(instance, filename: str) -> str:
    original_name = instance.original_filename or filename or "upload"
    cleaned_name = get_valid_filename(normalize_original_filename(original_name)) or "upload"
    return f"orders/{instance.order.public_id}/{instance.public_id}-{cleaned_name}"


def asset_version_path(instance, filename: str) -> str:
    original_name = instance.original_filename or filename or "asset"
    cleaned_name = get_valid_filename(normalize_original_filename(original_name)) or "asset"
    return (
        f"assets/{instance.customer.public_id}/{instance.asset.public_id}/"
        f"v{instance.version_number}/{instance.public_id}-{cleaned_name}"
    )


def asset_thumbnail_path(instance, filename: str) -> str:
    return (
        f"assets/{instance.customer.public_id}/{instance.version.asset.public_id}/"
        f"v{instance.version.version_number}/thumbnails/{instance.public_id}.webp"
    )


def asset_thin_zone_overlay_path(instance, filename: str) -> str:
    return (
        f"assets/{instance.customer.public_id}/{instance.version.asset.public_id}/"
        f"v{instance.version.version_number}/analysis/{instance.public_id}-thin-zones.webp"
    )


class OrderUploadQuerySet(models.QuerySet):
    def for_order(self, order):
        return self.filter(order=order)

    def for_customer(self, customer):
        return self.filter(order__customer=customer)


class OrderUploadInspectionQuerySet(models.QuerySet):
    def for_order(self, order):
        return self.filter(order_upload__order=order)

    def for_customer(self, customer):
        return self.filter(order_upload__order__customer=customer)


class OrderDriveFolderQuerySet(models.QuerySet):
    def for_order(self, order):
        return self.filter(order=order)

    def for_customer(self, customer):
        return self.filter(order__customer=customer)


class OrderUploadDriveSyncQuerySet(models.QuerySet):
    def for_order(self, order):
        return self.filter(order_upload__order=order)

    def for_customer(self, customer):
        return self.filter(order_upload__order__customer=customer)


class AssetQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_archived=False)

    def for_customer(self, customer):
        return self.filter(customer=customer)


class AssetVersionQuerySet(models.QuerySet):
    def for_customer(self, customer):
        return self.filter(customer=customer)

    def for_asset(self, asset):
        return self.filter(customer=asset.customer, asset=asset)


class Asset(BaseModel):
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="assets",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_assets",
    )
    name = models.CharField(max_length=255)
    current_version = models.ForeignKey(
        "AssetVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="current_for_assets",
    )
    is_archived = models.BooleanField(default=False)

    objects = AssetQuerySet.as_manager()

    class Meta:
        ordering = ("-updated_at", "-created_at")
        indexes = [
            models.Index(fields=("customer", "is_archived", "updated_at")),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        super().clean()
        if self.current_version_id and (
            self.current_version.asset_id != self.id
            or self.current_version.customer_id != self.customer_id
        ):
            raise ValidationError(
                {"current_version": "La version courante doit appartenir à cet asset et ce client."}
            )


class AssetVersion(BaseModel):
    class AnalysisStatus(models.TextChoices):
        PENDING = "pending", "En attente"
        PROCESSING = "processing", "Analyse en cours"
        READY = "ready", "Analysé"
        WARNING = "warning", "À vérifier"
        FAILED = "failed", "Échec"

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="asset_versions",
    )
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="versions")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_asset_versions",
    )
    replaced_version = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="replacement_versions",
    )
    version_number = models.PositiveIntegerField()
    file = models.FileField(upload_to=asset_version_path, max_length=500)
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=255)
    size_bytes = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    analysis_status = models.CharField(
        max_length=16,
        choices=AnalysisStatus.choices,
        default=AnalysisStatus.PENDING,
    )
    analysis_error = models.CharField(max_length=255, blank=True)
    auto_size_requested = models.BooleanField(
        default=False,
        help_text="Appliquer une fois la taille physique détectée à la ligne projet.",
    )

    objects = AssetVersionQuerySet.as_manager()

    class Meta:
        ordering = ("-version_number",)
        constraints = [
            models.UniqueConstraint(
                fields=("customer", "asset", "version_number"),
                name="uniq_asset_version_number",
            ),
        ]
        indexes = [
            models.Index(fields=("customer", "analysis_status", "created_at")),
            models.Index(fields=("customer", "sha256")),
        ]
        permissions = [("analyze_assetversion", "Can analyze asset versions")]

    def __str__(self) -> str:
        return f"{self.asset.name} v{self.version_number}"

    def clean(self):
        super().clean()
        if self.customer_id and self.asset_id and self.customer_id != self.asset.customer_id:
            raise ValidationError(
                {"asset": "L'asset et sa version doivent appartenir au même client."}
            )
        if self.replaced_version_id and (
            self.replaced_version.asset_id != self.asset_id
            or self.replaced_version.customer_id != self.customer_id
        ):
            raise ValidationError(
                {"replaced_version": "La version remplacée doit appartenir au même asset."}
            )


class AssetAnalysis(BaseModel):
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="asset_analyses",
    )
    version = models.OneToOneField(
        AssetVersion,
        on_delete=models.CASCADE,
        related_name="analysis",
    )
    image_width = models.PositiveIntegerField(null=True, blank=True)
    image_height = models.PositiveIntegerField(null=True, blank=True)
    dpi_x = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    dpi_y = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    has_alpha = models.BooleanField(null=True, blank=True)
    probable_white_background = models.BooleanField(null=True, blank=True)
    thumbnail = models.FileField(upload_to=asset_thumbnail_path, max_length=500, blank=True)
    thin_zone_overlay = models.FileField(
        upload_to=asset_thin_zone_overlay_path,
        max_length=500,
        blank=True,
    )
    warnings = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    analyzed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-analyzed_at", "-created_at")
        indexes = [models.Index(fields=("customer", "analyzed_at"))]

    def __str__(self) -> str:
        return f"Analyse {self.version}"

    def clean(self):
        super().clean()
        if self.customer_id and self.version_id and self.customer_id != self.version.customer_id:
            raise ValidationError(
                {"version": "L'analyse et la version doivent appartenir au même client."}
            )


class OrderUpload(BaseModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="uploads")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_uploads",
    )
    asset_version = models.OneToOneField(
        AssetVersion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="legacy_order_upload",
    )
    file = models.FileField(upload_to=order_upload_path, max_length=500)
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=255)
    size_bytes = models.PositiveBigIntegerField()
    sort_order = models.PositiveIntegerField(default=0)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(MIN_QTY)])
    support_color_hex = models.CharField(
        max_length=7,
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^$|^#[0-9A-Fa-f]{6}$",
                message="Couleur attendue au format #RRVVBB.",
            )
        ],
    )
    meterage_sqm = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO_AMOUNT)],
    )
    meterage_override_sqm = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=(
            "Ancienne saisie opérateur en m² (rétrocompatibilité). "
            "Préférer meterage_override_linear_m."
        ),
        validators=[MinValueValidator(MIN_METERAGE_OVERRIDE_SQMS)],
    )
    meterage_override_linear_m = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=(
            "Saisie opérateur : mètres linéaires sur la laize (par exemplaire). "
            "Facturation m² = linéaire × laize × quantité."
        ),
        validators=[MinValueValidator(MIN_METERAGE_OVERRIDE_LINEAR_M)],
    )
    unit_price_eur = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO_AMOUNT)],
    )
    line_total_eur = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO_AMOUNT)],
    )

    objects = OrderUploadQuerySet.as_manager()

    class Meta:
        ordering = ("sort_order", "created_at")
        indexes = [
            models.Index(fields=("order", "created_at")),
            models.Index(fields=("order", "sort_order")),
        ]

    def __str__(self) -> str:
        return f"{self.order.public_id} - {self.original_filename}"


class OrderUploadInspection(BaseModel):
    class Status(models.TextChoices):
        OK = "ok", "OK"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    order_upload = models.OneToOneField(
        OrderUpload,
        on_delete=models.CASCADE,
        related_name="inspection",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OK)
    summary_message = models.CharField(max_length=255, blank=True)
    file_kind = models.CharField(max_length=32, blank=True)
    file_extension = models.CharField(max_length=32, blank=True)
    image_width = models.PositiveIntegerField(null=True, blank=True)
    image_height = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    checked_at = models.DateTimeField(default=timezone.now)

    objects = OrderUploadInspectionQuerySet.as_manager()

    class Meta:
        ordering = ("-checked_at", "-created_at")
        indexes = [
            models.Index(fields=("status", "checked_at")),
            models.Index(fields=("order_upload", "status")),
        ]

    def __str__(self) -> str:
        return f"{self.order_upload.public_id} - {self.status}"


class OrderDriveFolder(BaseModel):
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="drive_folder",
    )
    shared_drive_id = models.CharField(max_length=255)
    relative_path = models.CharField(max_length=512)
    order_folder_id = models.CharField(max_length=255)
    folder_ids = models.JSONField(default=dict, blank=True)

    objects = OrderDriveFolderQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("order",)),
            models.Index(fields=("shared_drive_id", "order_folder_id")),
        ]

    def google_drive_folder_url(self) -> str | None:
        """URL navigateur vers le dossier commande sur Drive (Shared Drive ou My Drive)."""
        if not self.order_folder_id:
            return None
        return f"https://drive.google.com/drive/folders/{self.order_folder_id}"

    def __str__(self) -> str:
        return f"{self.order.public_id} - {self.relative_path}"


class OrderUploadDriveSync(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SYNCED = "synced", "Synced"
        FAILED = "failed", "Failed"

    order_upload = models.OneToOneField(
        OrderUpload,
        on_delete=models.CASCADE,
        related_name="drive_sync",
    )
    drive_folder = models.ForeignKey(
        OrderDriveFolder,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="upload_syncs",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    drive_filename = models.CharField(max_length=255, blank=True)
    remote_folder_id = models.CharField(max_length=255, blank=True)
    drive_file_id = models.CharField(max_length=255, blank=True)
    last_error = models.CharField(max_length=255, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)

    objects = OrderUploadDriveSyncQuerySet.as_manager()

    class Meta:
        ordering = ("-updated_at", "-created_at")
        indexes = [
            models.Index(fields=("status", "last_attempt_at")),
            models.Index(fields=("order_upload", "status")),
        ]

    def google_drive_browser_url(self) -> str | None:
        """Lien navigateur : fichier si `drive_file_id`, sinon dossier distant
        si `remote_folder_id`.
        """
        if self.drive_file_id:
            return f"https://drive.google.com/file/d/{self.drive_file_id}/view"
        if self.remote_folder_id:
            return f"https://drive.google.com/drive/folders/{self.remote_folder_id}"
        return None

    def __str__(self) -> str:
        return f"{self.order_upload.public_id} - {self.status}"
