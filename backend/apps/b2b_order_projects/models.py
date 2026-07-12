from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

from apps.core.models import BaseModel
from apps.customers.models import Customer

ZERO_AMOUNT = Decimal("0.00")
MIN_DIMENSION_MM = Decimal("0.01")
SUPPORT_COLOR_MULTICOLOR = "#multicolor"
SUPPORT_COLOR_HEX_VALIDATOR = RegexValidator(
    regex=r"^$|^#[0-9A-Fa-f]{6}$|^#multicolor$",
    message="Couleur support : #RRGGBB ou #multicolor attendu.",
)


class B2BOrderProjectQuerySet(models.QuerySet):
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


class B2BOrderProjectItemQuerySet(models.QuerySet):
    def for_customer(self, customer):
        return self.filter(customer=customer)

    def for_project(self, project):
        return self.filter(customer=project.customer, project=project)


class B2BOrderProjectNumberSequence(models.Model):
    year = models.PositiveSmallIntegerField(primary_key=True)
    next_value = models.PositiveBigIntegerField(default=1)

    class Meta:
        verbose_name = "Séquence de numéro de projet B2B"


class B2BOrderProject(BaseModel):
    class OrderMode(models.TextChoices):
        INDIVIDUAL_DESIGNS = "individual_designs", "Visuels individuels"
        READY_GANG_SHEET = "ready_gang_sheet", "Planche prête à imprimer"
        REORDER = "reorder", "Recommande"

    class Status(models.TextChoices):
        DRAFT = "draft", "Brouillon"
        INCOMPLETE = "incomplete", "Incomplet"
        ANALYZING = "analyzing", "Analyse en cours"
        ACTION_REQUIRED = "action_required", "Action requise"
        READY_TO_SUBMIT = "ready_to_submit", "Prêt à transmettre"
        SUBMITTED = "submitted", "Transmis"
        UNDER_REVIEW = "under_review", "En contrôle"
        CHANGES_REQUESTED = "changes_requested", "Corrections demandées"
        PRICE_CONFIRMATION_REQUIRED = "price_confirmation_required", "Tarif à confirmer"
        CONFIRMED = "confirmed", "Confirmé"
        CONVERTED = "converted", "Converti"
        CANCELLED = "cancelled", "Annulé"
        BLOCKED = "blocked", "Bloqué"

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="b2b_order_projects",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_b2b_order_projects",
    )
    project_number = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=255)
    customer_reference = models.CharField(max_length=128, blank=True)
    end_customer_reference = models.CharField(max_length=128, blank=True)
    order_mode = models.CharField(
        max_length=32,
        choices=OrderMode.choices,
        default=OrderMode.INDIVIDUAL_DESIGNS,
    )
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.DRAFT)
    requested_date = models.DateField(null=True, blank=True)
    delivery_method = models.CharField(max_length=32, blank=True)
    shipping_address = models.JSONField(default=dict, blank=True)
    customer_comment = models.TextField(blank=True)
    internal_comment = models.TextField(blank=True)
    estimated_length_mm = models.PositiveBigIntegerField(null=True, blank=True)
    confirmed_length_mm = models.PositiveBigIntegerField(null=True, blank=True)
    estimated_subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO_AMOUNT)],
    )
    estimated_tax = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO_AMOUNT)],
    )
    estimated_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO_AMOUNT)],
    )
    confirmed_subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO_AMOUNT)],
    )
    confirmed_tax = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO_AMOUNT)],
    )
    confirmed_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO_AMOUNT)],
    )
    price_confirmation_required = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    review_started_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    converted_at = models.DateTimeField(null=True, blank=True)
    converted_order = models.OneToOneField(
        "orders.Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_b2b_order_project",
    )

    objects = B2BOrderProjectQuerySet.as_manager()

    class Meta:
        ordering = ("-updated_at", "-created_at")
        indexes = [
            models.Index(fields=("customer", "status", "created_at")),
            models.Index(fields=("customer", "updated_at")),
            models.Index(fields=("status", "submitted_at")),
        ]
        permissions = [
            ("review_b2borderproject", "Can review B2B order projects"),
            ("force_transition_b2borderproject", "Can force B2B order project transitions"),
        ]

    def __str__(self) -> str:
        return f"{self.project_number} — {self.name}"


class B2BOrderProjectItem(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "À compléter"
        READY = "ready", "Prêt"
        ACTION_REQUIRED = "action_required", "Action requise"

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="b2b_order_project_items",
    )
    project = models.ForeignKey(
        B2BOrderProject,
        on_delete=models.CASCADE,
        related_name="items",
    )
    asset = models.ForeignKey(
        "uploads.Asset",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="b2b_order_project_items",
    )
    client_confirmed_asset_version = models.ForeignKey(
        "uploads.AssetVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    client_confirmed_at = models.DateTimeField(null=True, blank=True)
    client_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="confirmed_b2b_order_project_items",
    )
    name = models.CharField(max_length=255)
    customer_reference = models.CharField(max_length=128, blank=True)
    placement = models.CharField(max_length=128, blank=True)
    width_mm = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(MIN_DIMENSION_MM)],
    )
    height_mm = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(MIN_DIMENSION_MM)],
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    rotation_allowed = models.BooleanField(default=True)
    individual_cutting = models.BooleanField(default=False)
    support_color_hex = models.CharField(
        max_length=16,
        blank=True,
        default="",
        validators=[SUPPORT_COLOR_HEX_VALIDATOR],
    )
    customer_comment = models.TextField(blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.READY)
    sort_order = models.PositiveIntegerField(default=1)

    objects = B2BOrderProjectItemQuerySet.as_manager()

    class Meta:
        ordering = ("sort_order", "created_at")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(width_mm__gt=0), name="b2b_item_width_gt_zero"
            ),
            models.CheckConstraint(
                condition=models.Q(height_mm__gt=0), name="b2b_item_height_gt_zero"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="b2b_item_quantity_gt_zero"
            ),
            models.UniqueConstraint(
                fields=("customer", "project", "sort_order"),
                name="uniq_b2b_project_item_position",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        client_confirmed_asset_version__isnull=True,
                        client_confirmed_at__isnull=True,
                    )
                    | models.Q(
                        client_confirmed_asset_version__isnull=False,
                        client_confirmed_at__isnull=False,
                    )
                ),
                name="b2b_item_confirmation_pair",
            ),
        ]
        indexes = [
            models.Index(fields=("customer", "project", "sort_order")),
            models.Index(fields=("customer", "status")),
        ]

    def __str__(self) -> str:
        return f"{self.project.project_number} — {self.name}"

    @property
    def support_color_is_multicolor(self) -> bool:
        return self.support_color_hex == SUPPORT_COLOR_MULTICOLOR

    @property
    def support_color_label(self) -> str:
        if not self.support_color_hex:
            return ""
        if self.support_color_is_multicolor:
            return "Multicolore"
        return self.support_color_hex.upper()

    def clean(self):
        super().clean()
        if self.customer_id and self.project_id and self.customer_id != self.project.customer_id:
            raise ValidationError(
                {"customer": "La ligne et le projet doivent appartenir au même client."}
            )
        if self.customer_id and self.asset_id and self.customer_id != self.asset.customer_id:
            raise ValidationError(
                {"asset": "Le fichier et la ligne doivent appartenir au même client."}
            )
        if self.client_confirmed_asset_version_id:
            version = self.client_confirmed_asset_version
            if (
                not self.asset_id
                or version.asset_id != self.asset_id
                or version.customer_id != self.customer_id
            ):
                raise ValidationError(
                    {
                        "client_confirmed_asset_version": (
                            "La confirmation doit cibler une version du fichier courant "
                            "appartenant au même client."
                        )
                    }
                )
