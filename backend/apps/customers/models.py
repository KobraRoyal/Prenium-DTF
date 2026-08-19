from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel

CUSTOMER_ROLE_OWNER = "owner"
CUSTOMER_ROLE_ADMIN = "admin"
CUSTOMER_ROLE_MEMBER = "member"
CUSTOMER_ROLE_READONLY = "readonly"

ZERO_AMOUNT = Decimal("0.00")
MIN_VOLUME_LINEAR_M = Decimal("0.0001")
MAX_DISCOUNT_PERCENT = Decimal("100.00")


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
        STRIPE = "stripe", "Stripe (carte)"
        WIRE_TRANSFER = "wire_transfer", "Virement bancaire"

    class DefaultBillingMode(models.TextChoices):
        DEFERRED = "deferred", "Encours / facturation différée"
        IMMEDIATE = "immediate", "Paiement comptant (carte bancaire)"

    name = models.CharField(max_length=255)
    billing_email = models.EmailField(blank=True)
    siren = models.CharField(max_length=9, blank=True)
    vat_number = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True)
    b2b_order_projects_enabled = models.BooleanField(
        "Projets de commande B2B activés (historique)",
        default=True,
        help_text=(
            "Champ historique. Le parcours projet est le flux standard pour tous les "
            "clients actifs lorsque B2B_DTF_ORDER_PROJECT_ENABLED est actif."
        ),
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
    default_shipping_method = models.ForeignKey(
        "shipping.ShippingMethod",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="default_for_customers",
        verbose_name="Option de livraison préférée",
        help_text=(
            "Préselection client à la transmission (retrait / standard / express). "
            "Si vide : dérivée du mode d’acheminement par défaut."
        ),
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
            "Préférence affichée côté Atelier. "
            "Pour une commande en paiement immédiat, le client choisit "
            "parmi les moyens installés (PayPal, carte / Stripe)."
        ),
    )
    default_billing_mode = models.CharField(
        "Mode de règlement par défaut",
        max_length=16,
        choices=DefaultBillingMode.choices,
        default=DefaultBillingMode.DEFERRED,
        help_text=(
            "Mode de règlement du compte B2B : encours (facturation différée) "
            "ou comptant carte bancaire. En comptant, l’encours n’est plus "
            "proposé à la transmission. En encours, le client peut encore "
            "passer une commande en comptant CB."
        ),
    )

    objects = CustomerQuerySet.as_manager()

    class Meta:
        ordering = ("name",)
        permissions = [
            (
                "manage_customer_pricing",
                "Peut définir les conditions tarifaires d’un compte client",
            ),
        ]

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


class CustomerVolumeDiscountTierQuerySet(models.QuerySet):
    def for_customer(self, customer):
        return self.filter(customer=customer)

    def active(self):
        return self.filter(is_active=True)


class CustomerVolumeDiscountTier(BaseModel):
    """Palier de remise volume DTF mensuel (rétroactif encours / prospectif comptant)."""

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="volume_discount_tiers",
    )
    minimum_monthly_linear_m = models.DecimalField(
        "Seuil mensuel (m linéaires)",
        max_digits=12,
        decimal_places=4,
        validators=[MinValueValidator(MIN_VOLUME_LINEAR_M)],
    )
    discount_percent = models.DecimalField(
        "Remise (%)",
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.01")),
            MaxValueValidator(MAX_DISCOUNT_PERCENT),
        ],
    )
    is_active = models.BooleanField("Palier actif", default=True)

    objects = CustomerVolumeDiscountTierQuerySet.as_manager()

    class Meta:
        ordering = ("minimum_monthly_linear_m", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("customer", "minimum_monthly_linear_m"),
                name="uniq_customer_volume_discount_threshold",
            ),
            models.CheckConstraint(
                condition=models.Q(minimum_monthly_linear_m__gt=0),
                name="customer_volume_discount_threshold_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(discount_percent__gt=0)
                    & models.Q(discount_percent__lte=MAX_DISCOUNT_PERCENT)
                ),
                name="customer_volume_discount_percent_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("customer", "is_active", "minimum_monthly_linear_m"),
                name="cust_vol_tier_lookup_idx",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.customer.name} — {self.minimum_monthly_linear_m} m : -{self.discount_percent} %"
        )


class DefaultCustomerVolumeDiscountTierQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class DefaultCustomerVolumeDiscountTier(BaseModel):
    """Palier global copié sur chaque nouveau client encours ou comptant."""

    minimum_monthly_linear_m = models.DecimalField(
        "Seuil mensuel (m linéaires)",
        max_digits=12,
        decimal_places=4,
        validators=[MinValueValidator(MIN_VOLUME_LINEAR_M)],
    )
    discount_percent = models.DecimalField(
        "Remise (%)",
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.01")),
            MaxValueValidator(MAX_DISCOUNT_PERCENT),
        ],
    )
    is_active = models.BooleanField("Palier actif", default=True)

    objects = DefaultCustomerVolumeDiscountTierQuerySet.as_manager()

    class Meta:
        ordering = ("minimum_monthly_linear_m", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("minimum_monthly_linear_m",),
                name="uniq_default_volume_discount_threshold",
            ),
            models.CheckConstraint(
                condition=models.Q(minimum_monthly_linear_m__gt=0),
                name="default_volume_discount_threshold_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(discount_percent__gt=0)
                    & models.Q(discount_percent__lte=MAX_DISCOUNT_PERCENT)
                ),
                name="default_volume_discount_percent_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("is_active", "minimum_monthly_linear_m"),
                name="default_vol_tier_lookup_idx",
            ),
        ]
        verbose_name = "Palier de remise par défaut"
        verbose_name_plural = "Paliers de remise par défaut"

    def __str__(self) -> str:
        return f"{self.minimum_monthly_linear_m} m : -{self.discount_percent} %"


class VolumeDiscountDashboardCopy(BaseModel):
    """Messages d’encouragement du dashboard client (singleton Atelier)."""

    singleton = models.BooleanField(default=True, unique=True, editable=False)
    start_immediate = models.CharField("Compteur à zéro (comptant)", max_length=400, blank=True)
    start_deferred = models.CharField("Compteur à zéro (encours)", max_length=400, blank=True)
    warm_immediate = models.CharField("En route (comptant)", max_length=400, blank=True)
    warm_deferred = models.CharField("En route (encours)", max_length=400, blank=True)
    hold_immediate = models.CharField("Palier en poche (comptant)", max_length=400, blank=True)
    hold_deferred = models.CharField("Palier en poche (encours)", max_length=400, blank=True)
    hot_immediate = models.CharField("Tout proche (comptant)", max_length=400, blank=True)
    hot_deferred = models.CharField("Tout proche (encours)", max_length=400, blank=True)
    max_immediate = models.CharField("Palier max (comptant)", max_length=400, blank=True)
    max_deferred = models.CharField("Palier max (encours)", max_length=400, blank=True)

    class Meta:
        verbose_name = "Messages dashboard remise volume"
        verbose_name_plural = "Messages dashboard remise volume"

    def __str__(self) -> str:
        return "Messages dashboard remise volume"


class CustomerMembership(BaseModel):
    class Role(models.TextChoices):
        OWNER = CUSTOMER_ROLE_OWNER, "Propriétaire"
        ADMIN = CUSTOMER_ROLE_ADMIN, "Administrateur"
        MEMBER = CUSTOMER_ROLE_MEMBER, "Collaborateur"
        READONLY = CUSTOMER_ROLE_READONLY, "Lecture seule"

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

    @property
    def can_manage_team(self) -> bool:
        return self.role in {self.Role.OWNER, self.Role.ADMIN}


class CustomerInvitation(BaseModel):
    """Invitation à rejoindre une organisation, sans stocker le jeton brut."""

    class Kind(models.TextChoices):
        OWNER_ACTIVATION = "owner_activation", "Activation du propriétaire"
        COLLABORATOR = "collaborator", "Invitation d'un collaborateur"

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        ACCEPTED = "accepted", "Acceptée"
        REVOKED = "revoked", "Révoquée"
        EXPIRED = "expired", "Expirée"

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    email = models.EmailField()
    role = models.CharField(
        max_length=16,
        choices=CustomerMembership.Role.choices,
        default=CustomerMembership.Role.MEMBER,
    )
    kind = models.CharField(
        max_length=24,
        choices=Kind.choices,
        default=Kind.COLLABORATOR,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_invitations_sent",
    )
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_invitations_accepted",
    )
    token_version = models.PositiveIntegerField(default=1)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("customer", "email"),
                condition=models.Q(status="pending"),
                name="uniq_pending_customer_invitation_email",
            ),
        ]
        indexes = [
            models.Index(fields=("customer", "status", "created_at")),
            models.Index(fields=("email", "status")),
        ]

    def __str__(self) -> str:
        return f"{self.email} -> {self.customer} ({self.role})"
