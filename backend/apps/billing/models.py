import os
from decimal import Decimal

from django.conf import settings
from django.core.files.utils import validate_file_name
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.text import get_valid_filename

from apps.core.models import BaseModel
from apps.customers.models import Customer
from apps.orders.models import Order

ZERO_AMOUNT = Decimal("0.00")


class BillingStatementQuerySet(models.QuerySet):
    def for_customer(self, customer):
        return self.filter(customer=customer)


class BillingStatement(BaseModel):
    """Regroupement mensuel / bi-mensuel des commandes facturées en différé."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Brouillon"
        ISSUED = "issued", "Emise"
        PAID = "paid", "Payee"

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="billing_statements",
    )
    label = models.CharField(max_length=64, blank=True)
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=ZERO_AMOUNT,
        validators=[MinValueValidator(ZERO_AMOUNT)],
    )
    currency = models.CharField(max_length=3, default="EUR")

    objects = BillingStatementQuerySet.as_manager()

    class Meta:
        ordering = ("-period_end", "-created_at")
        indexes = [
            models.Index(fields=("customer", "status", "period_end")),
        ]

    def __str__(self) -> str:
        return f"{self.customer.name} — {self.label or self.period_start}"


def normalize_invoice_filename(filename: str) -> str:
    original_name = os.path.basename(str(filename).replace("\\", "/")).strip()
    if not original_name:
        return "invoice.txt"
    validate_file_name(original_name, allow_relative_path=False)
    return original_name


def invoice_document_path(instance, filename: str) -> str:
    original_name = instance.file_name or filename or "invoice.txt"
    cleaned_name = get_valid_filename(normalize_invoice_filename(original_name)) or "invoice.txt"
    return f"billing/invoices/{instance.order.public_id}/{instance.public_id}-{cleaned_name}"


class PaymentQuerySet(models.QuerySet):
    def for_customer(self, customer):
        return self.filter(order__customer=customer)

    def for_order(self, order):
        return self.filter(order=order)


class Payment(BaseModel):
    class Provider(models.TextChoices):
        PAYPAL = "paypal", "PayPal"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        CAPTURED = "captured", "Captured"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_payments",
    )
    provider = models.CharField(max_length=16, choices=Provider.choices, default=Provider.PAYPAL)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(ZERO_AMOUNT)],
    )
    currency = models.CharField(max_length=3)
    paypal_order_id = models.CharField(max_length=255, blank=True)
    paypal_capture_id = models.CharField(max_length=255, blank=True)
    approval_url = models.URLField(max_length=2048, blank=True)
    source = models.CharField(max_length=32, default="client_api")
    request_snapshot = models.JSONField(default=dict, blank=True)
    provider_payload = models.JSONField(default=dict, blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    last_error_message = models.CharField(max_length=255, blank=True)

    objects = PaymentQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        permissions = [
            ("confirm_payment", "Can confirm payment"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("paypal_order_id",),
                condition=~Q(paypal_order_id=""),
                name="uniq_payment_paypal_order_id_non_empty",
            ),
            models.UniqueConstraint(
                fields=("paypal_capture_id",),
                condition=~Q(paypal_capture_id=""),
                name="uniq_payment_paypal_capture_id_non_empty",
            ),
        ]
        indexes = [
            models.Index(fields=("order", "status", "created_at")),
            models.Index(fields=("status", "updated_at")),
        ]

    def __str__(self) -> str:
        return f"{self.order.public_id} - {self.provider} - {self.status}"


class InvoiceQuerySet(models.QuerySet):
    def for_customer(self, customer):
        return self.filter(order__customer=customer)


class Invoice(BaseModel):
    class Status(models.TextChoices):
        ISSUED = "issued", "Issued"
        VOID = "void", "Void"

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="invoice")
    payment = models.ForeignKey(
        Payment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invoices",
    )
    paid_at = models.DateTimeField(
        "Payée le",
        null=True,
        blank=True,
        help_text=(
            "Règlement reçu : date de confirmation (virement ou équivalent). "
            "Les factures PayPal sont soldées à l’émission."
        ),
    )
    paid_recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invoices_marked_paid",
        verbose_name="Paiement enregistré par",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ISSUED)
    invoice_number = models.CharField(max_length=64, unique=True)
    subtotal_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(ZERO_AMOUNT)],
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(ZERO_AMOUNT)],
    )
    currency = models.CharField(max_length=3)
    billing_name = models.CharField(max_length=255, blank=True)
    billing_email = models.EmailField(blank=True)
    file = models.FileField(upload_to=invoice_document_path, max_length=500, blank=True)
    file_name = models.CharField(max_length=255, blank=True)
    file_mime_type = models.CharField(max_length=128, blank=True)
    source = models.CharField(max_length=32, default="backend_capture")
    snapshot = models.JSONField(default=dict, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)

    objects = InvoiceQuerySet.as_manager()

    class Meta:
        ordering = ("-issued_at", "-created_at")
        indexes = [
            models.Index(fields=("status", "issued_at")),
            models.Index(fields=("order", "status")),
            models.Index(fields=("paid_at",)),
        ]
        permissions = [
            ("mark_invoice_paid", "Marquer une facture comme payée (virement)"),
        ]

    def __str__(self) -> str:
        return f"{self.invoice_number} - {self.status}"
