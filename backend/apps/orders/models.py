from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.catalog.models import CatalogService
from apps.core.models import BaseModel
from apps.core.public_refs import short_public_ref
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
        return self.filter(
            customer__memberships__user=user,
            customer__memberships__is_active=True,
            customer__is_active=True,
        ).distinct()


class Order(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        CANCELLED = "cancelled", "Cancelled"

    class BillingMode(models.TextChoices):
        IMMEDIATE = "immediate", "Paiement comptant (carte bancaire)"
        DEFERRED = "deferred", "Encours / facturation différée"

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
        help_text="Sous-total HT lignes produit (DTF + préparation fichier).",
    )
    shipping_method_code = models.SlugField(
        max_length=64,
        blank=True,
        help_text="Snapshot code option livraison (pickup / standard / express).",
    )
    shipping_method_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Snapshot libellé option livraison au moment du choix.",
    )
    estimated_handover_date = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "Date prévisionnelle de remise : retrait atelier ou livraison, selon le mode choisi."
        ),
    )
    shipping_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=ZERO_AMOUNT,
        validators=[MinValueValidator(ZERO_AMOUNT)],
        help_text="Frais d’expédition HT figés (0 si retrait atelier).",
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=ZERO_AMOUNT,
        validators=[MinValueValidator(ZERO_AMOUNT)],
        help_text="Taux TVA appliqué (ex. 0.2000 = 20 %). 0 si encours / hors TVA.",
    )
    tax_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=ZERO_AMOUNT,
        validators=[MinValueValidator(ZERO_AMOUNT)],
        help_text="Montant TVA (comptant CB : 20 % sur sous-total HT + port).",
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=ZERO_AMOUNT,
        validators=[MinValueValidator(ZERO_AMOUNT)],
        help_text="Total dû / encaissé : subtotal + shipping + tax.",
    )
    volume_discount_month = models.DateField(
        null=True,
        blank=True,
        help_text="Premier jour du mois civil utilisé pour la remise volume.",
    )
    monthly_volume_linear_m = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO_AMOUNT)],
        help_text="Volume linéaire mensuel éligible au dernier calcul.",
    )
    volume_discount_threshold_linear_m = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO_AMOUNT)],
        help_text="Seuil du palier mensuel appliqué, si un palier est atteint.",
    )
    volume_discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=ZERO_AMOUNT,
        validators=[MinValueValidator(ZERO_AMOUNT)],
        help_text="Pourcentage de remise rétroactive appliqué au DTF de la commande.",
    )
    volume_discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=ZERO_AMOUNT,
        validators=[MinValueValidator(ZERO_AMOUNT)],
        help_text="Montant HT de remise volume appliqué au DTF de la commande.",
    )
    volume_discount_base_unit_price_eur = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO_AMOUNT)],
        help_text="Prix DTF brut au m² conservé avant remise volume.",
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
        on_delete=models.PROTECT,
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
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cancelled_orders",
    )
    cancellation_reason = models.CharField(max_length=255, blank=True)

    objects = OrderQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("customer", "status", "created_at")),
            models.Index(fields=("status", "created_at")),
            models.Index(fields=("customer", "billing_mode", "pricing_status")),
            models.Index(fields=("billing_statement", "created_at")),
            models.Index(
                fields=("customer", "created_at"),
                name="order_billable_month_idx",
                condition=models.Q(
                    status="submitted",
                    billing_mode="deferred",
                    pricing_status="priced",
                    billing_statement__isnull=True,
                ),
            ),
        ]
        permissions = [
            ("delete_atelier_order", "Peut supprimer une commande Atelier"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(volume_discount_percent__gte=0)
                & models.Q(volume_discount_percent__lte=100),
                name="order_volume_discount_percent_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(volume_discount_amount__gte=0),
                name="order_volume_discount_amount_nonnegative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.customer.name} - {self.public_id}"

    def clean(self):
        super().clean()
        if (
            self.billing_statement_id is not None
            and self.billing_statement.customer_id != self.customer_id
        ):
            from django.core.exceptions import ValidationError

            raise ValidationError(
                {"billing_statement": "Le relevé doit appartenir au même client que la commande."}
            )

    @property
    def short_ref(self) -> str:
        return short_public_ref(self.public_id)

    def uses_atelier_pricing(self) -> bool:
        """Prix calculé sur métrage (encours ou comptant CB portail).

        Exclut le flux catalogue / API déjà tarifé à la création.
        Les dépôts portail restent en tarification métrage même après création
        des lignes (self-service Gang Sheet ou calcul atelier).
        """
        if self.billing_mode == self.BillingMode.DEFERRED:
            return True
        if self.billing_mode != self.BillingMode.IMMEDIATE:
            return False
        if self.source in {"client_api", "api"}:
            return False
        # create_order catalogue : lignes présentes dès la création, sans dépôt.
        # Gang Sheet / projet : fichiers d’abord, lignes ensuite → reste métrage.
        if self.items.exists() and not self.uploads.exists():
            return False
        return True


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
        decimal_places=4,
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
