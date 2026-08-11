import os
from decimal import Decimal

from django.conf import settings
from django.core.files.utils import validate_file_name
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import get_valid_filename

from apps.core.models import BaseModel
from apps.orders.models import Order

ZERO_AMOUNT = Decimal("0.00")


class ShippingMethodQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class ShippingMethod(BaseModel):
    """Option de livraison commerciale (retrait / standard / express).

    Les montants sont HT. Le snapshot commande fige code, libellé et prix
    au moment du choix client pour éviter les dérives tarifaires.
    """

    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    base_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=ZERO_AMOUNT,
        validators=[MinValueValidator(ZERO_AMOUNT)],
        help_text="Frais d’expédition HT (EUR). Forcé à 0 si retrait atelier.",
    )
    currency = models.CharField(max_length=3, default="EUR")
    is_pickup = models.BooleanField(
        default=False,
        help_text="Retrait atelier : aucun frais d’expédition.",
    )
    eta_label = models.CharField(
        max_length=128,
        blank=True,
        help_text="Indication délai affichée au client (ex. 48–72 h).",
    )
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    objects = ShippingMethodQuerySet.as_manager()

    class Meta:
        ordering = ("display_order", "name")
        indexes = [
            models.Index(
                fields=("is_active", "display_order"),
                name="shipping_sh_is_acti_7cf301_idx",
            ),
            models.Index(
                fields=("is_pickup", "is_active"),
                name="shipping_sh_is_pick_e4f587_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def resolved_price(self) -> Decimal:
        if self.is_pickup:
            return ZERO_AMOUNT
        return (self.base_price or ZERO_AMOUNT).quantize(Decimal("0.01"))


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
    sendcloud_order_id = models.CharField(max_length=255, blank=True)
    sendcloud_shipment_id = models.CharField(max_length=255, blank=True)
    sendcloud_parcel_id = models.CharField(max_length=255, blank=True)
    sendcloud_status_code = models.CharField(max_length=64, blank=True)
    sendcloud_status_message = models.CharField(max_length=255, blank=True)
    shipping_option_code = models.CharField(
        max_length=128,
        blank=True,
        help_text=(
            "Indication transporteur / service (optionnelle) ; "
            "l’étiquette est créée dans Sendcloud."
        ),
    )
    contract_id = models.PositiveIntegerField(null=True, blank=True)
    tracking_number = models.CharField(max_length=255, blank=True)
    tracking_url = models.CharField(max_length=2048, blank=True)
    label_file = models.FileField(upload_to=shipment_label_path, max_length=500, blank=True)
    label_filename = models.CharField(max_length=255, blank=True)
    label_mime_type = models.CharField(max_length=128, blank=True)
    label_retrieved_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
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
            models.Index(
                fields=("status", "updated_at"),
                name="shipping_sh_status_755ce0_idx",
            ),
            models.Index(
                fields=("sendcloud_order_id",),
                name="shipping_sh_sendclo_6f3a91_idx",
            ),
            models.Index(
                fields=("sendcloud_parcel_id",),
                name="shipping_sh_sendclo_26eb4a_idx",
            ),
            models.Index(
                fields=("order", "status"),
                name="shipping_sh_order_i_242975_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.order.public_id} - {self.status}"


class SendcloudWebhookEventQuerySet(models.QuerySet):
    def for_customer(self, customer):
        return self.filter(customer=customer)


class SendcloudWebhookEvent(BaseModel):
    """Trace d'idempotence d'un webhook Sendcloud, sans conserver son payload."""

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="sendcloud_webhook_events",
    )
    shipment = models.ForeignKey(
        Shipment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="webhook_events",
    )
    event_key = models.CharField(max_length=80)
    provider_event_id = models.CharField(max_length=255, blank=True)
    payload_hash = models.CharField(max_length=64)
    processed_at = models.DateTimeField(null=True, blank=True)

    objects = SendcloudWebhookEventQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("customer", "event_key"),
                name="shipping_sc_event_key_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("customer", "created_at"),
                name="ship_sc_cust_created_idx",
            ),
            models.Index(
                fields=("shipment", "created_at"),
                name="ship_sc_ship_created_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.customer.public_id} - {self.event_key}"
