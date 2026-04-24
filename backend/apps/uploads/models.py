import os
from decimal import Decimal

from django.conf import settings
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


class OrderUpload(BaseModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="uploads")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_uploads",
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
