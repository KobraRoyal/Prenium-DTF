import os

from django.conf import settings
from django.core.files.utils import validate_file_name
from django.db import models
from django.utils.text import get_valid_filename

from apps.core.models import BaseModel
from apps.orders.models import Order


def normalize_label_filename(filename: str) -> str:
    original_name = os.path.basename(str(filename).replace("\\", "/")).strip()
    if not original_name:
        return "label.pdf"
    validate_file_name(original_name, allow_relative_path=False)
    return original_name


def shipment_label_path(instance, filename: str) -> str:
    original_name = instance.label_filename or filename or "label.pdf"
    cleaned_name = get_valid_filename(normalize_label_filename(original_name)) or "label.pdf"
    return f"shipping/{instance.order.public_id}/{instance.public_id}-{cleaned_name}"


class ShipmentQuerySet(models.QuerySet):
    def for_order(self, order):
        return self.filter(order=order)

    def for_customer(self, customer):
        return self.filter(order__customer=customer)


class Shipment(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CREATED = "created", "Created"
        FAILED = "failed", "Failed"

    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="shipment",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_shipments",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_shipments",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    sendcloud_shipment_id = models.CharField(max_length=255, blank=True)
    sendcloud_parcel_id = models.CharField(max_length=255, blank=True)
    sendcloud_status_code = models.CharField(max_length=64, blank=True)
    sendcloud_status_message = models.CharField(max_length=255, blank=True)
    shipping_option_code = models.CharField(max_length=128)
    contract_id = models.PositiveIntegerField(null=True, blank=True)
    tracking_number = models.CharField(max_length=255, blank=True)
    tracking_url = models.CharField(max_length=2048, blank=True)
    label_file = models.FileField(upload_to=shipment_label_path, max_length=500, blank=True)
    label_filename = models.CharField(max_length=255, blank=True)
    label_mime_type = models.CharField(max_length=128, blank=True)
    label_retrieved_at = models.DateTimeField(null=True, blank=True)
    last_api_sync_at = models.DateTimeField(null=True, blank=True)
    last_error_message = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=32, default="staff_api")
    request_snapshot = models.JSONField(default=dict, blank=True)

    objects = ShipmentQuerySet.as_manager()

    class Meta:
        ordering = ("-updated_at", "-created_at")
        permissions = [
            ("create_shipment", "Can create shipment"),
        ]
        indexes = [
            models.Index(fields=("status", "updated_at")),
            models.Index(fields=("sendcloud_parcel_id",)),
            models.Index(fields=("order", "status")),
        ]

    def __str__(self) -> str:
        return f"{self.order.public_id} - {self.status}"
