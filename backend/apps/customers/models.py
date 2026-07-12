from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import BaseModel

CUSTOMER_ROLE_OWNER = "owner"
CUSTOMER_ROLE_MEMBER = "member"

ZERO_AMOUNT = Decimal("0.00")


class CustomerQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def for_user(self, user):
        if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
            return self.none()
        return self.active().filter(memberships__user=user, memberships__is_active=True).distinct()


class CustomerMembershipQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True, customer__is_active=True, user__is_active=True)

    def for_user(self, user):
        if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
            return self.none()
        return self.filter(user=user)

    def for_customer(self, customer):
        return self.filter(customer=customer)

    def owners(self):
        return self.filter(role=CUSTOMER_ROLE_OWNER)


class Customer(BaseModel):
    class DefaultShippingMode(models.TextChoices):
        PICKUP = "pickup", "Retrait atelier"
        CARRIER = "carrier", "Expédition (transporteur)"
        DIRECT = "direct", "Livraison directe au client"

    class PreferredSettlementMethod(models.TextChoices):
        PAYPAL = "paypal", "PayPal"
        WIRE_TRANSFER = "wire_transfer", "Virement bancaire"

    name = models.CharField(max_length=255)
    billing_email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    b2b_order_projects_enabled = models.BooleanField(
        "Projets de commande B2B activés",
        default=False,
        help_text="Activation IDS explicite du parcours projet avant commande.",
    )
    notes = models.TextField(blank=True)

    billing_address_line1 = models.CharField(
        "Facturation — ligne 1",
        max_length=255,
        blank=True,
    )
    billing_address_line2 = models.CharField(
        "Facturation — ligne 2",
        max_length=255,
        blank=True,
    )
    billing_postal_code = models.CharField(
        "Facturation — code postal",
        max_length=32,
        blank=True,
    )
    billing_city = models.CharField(
        "Facturation — ville",
        max_length=128,
        blank=True,
    )
    billing_country = models.CharField(
        "Facturation — pays (ISO 3166-1 alpha-2)",
        max_length=2,
        default="FR",
    )
    shipping_address_line1 = models.CharField(
        "Livraison — ligne 1",
        max_length=255,
        blank=True,
        help_text="Par défaut pour expédition / étiquette ; peut être repris sur la commande.",
    )
    shipping_address_line2 = models.CharField(
        "Livraison — ligne 2",
        max_length=255,
        blank=True,
    )
    shipping_postal_code = models.CharField(
        "Livraison — code postal",
        max_length=32,
        blank=True,
    )
    shipping_city = models.CharField(
        "Livraison — ville",
        max_length=128,
        blank=True,
    )
    shipping_country = models.CharField(
        "Livraison — pays (ISO 3166-1 alpha-2)",
        max_length=2,
        default="FR",
    )
    default_shipping_mode = models.CharField(
        "Mode d’acheminement par défaut",
        max_length=16,
        choices=DefaultShippingMode.choices,
        default=DefaultShippingMode.CARRIER,
    )
    negotiated_file_preparation_fee_eur = models.DecimalField(
        "Forfait préparation fichier négocié (EUR / fichier)",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO_AMOUNT)],
        help_text=(
            "Si renseigné : forfait « préparation fichier » par fichier pour ce client. "
            "Sinon : prix du service catalogue « Préparation fichier » (ex. 10 €)."
        ),
    )
    preferred_settlement_method = models.CharField(
        "Mode de règlement préféré",
        max_length=24,
        choices=PreferredSettlementMethod.choices,
        default=PreferredSettlementMethod.WIRE_TRANSFER,
        help_text=(
            "PayPal (paiement en ligne) ou virement — utilisé comme référence comptable / UI."
        ),
    )

    objects = CustomerQuerySet.as_manager()

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class CustomerBillingProfile(BaseModel):
    """Paramètres B2B : facturation différée, encours, grille tarifaire optionnelle."""

    class BillingCycle(models.TextChoices):
        MONTHLY = "monthly", "Mensuelle"
        BI_MONTHLY = "bi_monthly", "Bi-mensuelle"

    customer = models.OneToOneField(
        Customer,
        on_delete=models.CASCADE,
        related_name="billing_profile",
    )
    billing_cycle = models.CharField(
        max_length=16,
        choices=BillingCycle.choices,
        default=BillingCycle.MONTHLY,
    )
    credit_limit_eur = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO_AMOUNT)],
        help_text="Plafond d'encours optionnel (EUR).",
    )
    enforce_credit_block = models.BooleanField(
        default=False,
        help_text="Si vrai, dépassement de plafond marque la commande en blocage encours.",
    )
    price_per_sqm_eur = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO_AMOUNT)],
        help_text=(
            "Prix au m² DTF pour ce client : si renseigné, il remplace "
            "le prix du service catalogue "
            "pour le calcul de tarification différée."
        ),
    )

    class Meta:
        ordering = ("customer__name",)

    def __str__(self) -> str:
        return f"Facturation {self.customer.name}"


class CustomerMembership(BaseModel):
    class Role(models.TextChoices):
        OWNER = CUSTOMER_ROLE_OWNER, "Owner"
        MEMBER = CUSTOMER_ROLE_MEMBER, "Member"

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_memberships",
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)
    is_active = models.BooleanField(default=True)

    objects = CustomerMembershipQuerySet.as_manager()

    class Meta:
        ordering = ("customer__name", "user__email")
        constraints = [
            models.UniqueConstraint(fields=("customer", "user"), name="uniq_customer_membership"),
        ]
        indexes = [
            models.Index(fields=("customer", "role")),
            models.Index(fields=("user", "is_active")),
        ]

    def __str__(self) -> str:
        return f"{self.customer} -> {self.user} ({self.role})"

    @property
    def is_owner(self) -> bool:
        return self.role == self.Role.OWNER
