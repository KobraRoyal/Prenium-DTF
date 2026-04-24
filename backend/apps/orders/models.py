from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.catalog.models import CatalogService
from apps.core.models import BaseModel
from apps.customers.models import Customer

ZERO_AMOUNT = Decimal("0.00")
MIN_QUANTITY = Decimal("0.01")
MIN_METERAGE_LINEAR_M = Decimal("0.0001")


class OrderQuerySet(models.QuerySet):
    def for_customer(self, customer):
        return self.filter(customer=customer)

    def for_user(self, user):
        if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
            return self.none()
        return (
            self.filter(
                customer__memberships__user=user,
                customer__memberships__is_active=True,
                customer__is_active=True,
            )
            .distinct()
        )


class Order(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"

    class BillingMode(models.TextChoices):
        IMMEDIATE = "immediate", "Paiement à la commande"
        DEFERRED = "deferred", "Facturation différée"

    class PricingStatus(models.TextChoices):
        PENDING = "pending", "Prix en attente"
        PRICED = "priced", "Prix calculé"
        FAILED = "failed", "Échec calcul"

    class CreditHoldStatus(models.TextChoices):
        NONE = "none", "Non applicable"
        CLEAR = "clear", "Encours dans la limite"
        WARNING = "warning", "Encours dépassé (alerte)"
        BLOCKED = "blocked", "Encours dépassé (blocage)"

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="orders")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_orders",
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.SUBMITTED)
    currency = models.CharField(max_length=3, default="EUR")
    subtotal_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=ZERO_AMOUNT,
        validators=[MinValueValidator(ZERO_AMOUNT)],
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=ZERO_AMOUNT,
        validators=[MinValueValidator(ZERO_AMOUNT)],
    )
    customer_note = models.TextField(blank=True)
    source = models.CharField(max_length=32, default="client_portal")
    billing_mode = models.CharField(
        max_length=16,
        choices=BillingMode.choices,
        default=BillingMode.IMMEDIATE,
    )
    pricing_status = models.CharField(
        max_length=16,
        choices=PricingStatus.choices,
        default=PricingStatus.PENDING,
    )
    credit_hold_status = models.CharField(
        max_length=16,
        choices=CreditHoldStatus.choices,
        default=CreditHoldStatus.NONE,
    )
    billing_statement = models.ForeignKey(
        "billing.BillingStatement",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
    )
    meterage_override_linear_m = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=(
            "Saisie opérateur : mètres linéaires sur la laize pour toute la commande. "
            "Surface facturable = linéaire × laize, répartie entre les fichiers au tarif."
        ),
        validators=[MinValueValidator(MIN_METERAGE_LINEAR_M)],
    )

    objects = OrderQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("customer", "status", "created_at")),
            models.Index(fields=("status", "created_at")),
            models.Index(fields=("customer", "billing_mode", "pricing_status")),
            models.Index(fields=("billing_statement", "created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.customer.name} - {self.public_id}"


class OrderLine(BaseModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    service = models.ForeignKey(
        CatalogService,
        on_delete=models.PROTECT,
        related_name="order_lines",
    )
    position = models.PositiveIntegerField()
    service_code = models.CharField(max_length=64)
    service_name = models.CharField(max_length=255)
    service_type = models.CharField(max_length=32)
    unit = models.CharField(max_length=32)
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(MIN_QUANTITY)],
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(ZERO_AMOUNT)],
    )
    line_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(ZERO_AMOUNT)],
    )

    class Meta:
        ordering = ("position", "created_at")
        constraints = [
            models.UniqueConstraint(fields=("order", "position"), name="uniq_order_line_position"),
        ]
        indexes = [
            models.Index(fields=("order", "position")),
            models.Index(fields=("service_code", "service_type")),
        ]

    def __str__(self) -> str:
        return f"{self.order.public_id} - {self.service_name}"

