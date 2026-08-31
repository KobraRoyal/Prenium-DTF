from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import BaseModel

ZERO_AMOUNT = Decimal("0.00")


class ProcessingTimeOptionQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class ProcessingTimeOption(BaseModel):
    """Option de délai de traitement atelier avec majoration tarifaire.

    La majoration en pourcentage s'applique au montant DTF (planche) après remise
    volume éventuelle. Le forfait fixe s'ajoute en complément.
    """

    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    eta_label = models.CharField(
        max_length=255,
        help_text="Libellé délai affiché au client (ex. « Imprimé et expédié dans 3 jours »).",
    )
    disclaimer = models.CharField(
        max_length=255,
        default="Hors weekend et jour férié",
        help_text="Mention légale affichée entre guillemets après le délai.",
    )
    business_days = models.PositiveSmallIntegerField(
        default=3,
        validators=[MinValueValidator(0)],
        help_text="Délai métier en jours ouvrés (0 = demain / express).",
    )
    markup_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=ZERO_AMOUNT,
        validators=[MinValueValidator(ZERO_AMOUNT)],
        help_text="Majoration en % appliquée au montant DTF (planche).",
    )
    flat_fee_eur = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=ZERO_AMOUNT,
        validators=[MinValueValidator(ZERO_AMOUNT)],
        help_text="Forfait HT additionnel (ex. express +7 €).",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Option présélectionnée au checkout si aucun choix client.",
    )
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    objects = ProcessingTimeOptionQuerySet.as_manager()

    class Meta:
        ordering = ("display_order", "name")
        indexes = [
            models.Index(
                fields=("is_active", "display_order"),
                name="proc_time_is_act_disp_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def client_label(self) -> str:
        """Libellé complet pour affichage client."""
        parts = [self.eta_label.strip()]
        if self.disclaimer.strip():
            parts.append(f"« {self.disclaimer.strip()} »")
        return " ".join(part for part in parts if part)


class CustomerProcessingTimeOptionOverrideQuerySet(models.QuerySet):
    def for_customer(self, customer):
        return self.filter(customer=customer)


class CustomerProcessingTimeOptionOverride(BaseModel):
    """Dérogation client sur une option de délai de traitement globale.

    Champs vides (null) = hériter de la grille par défaut atelier.
    """

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="processing_time_overrides",
    )
    option = models.ForeignKey(
        ProcessingTimeOption,
        on_delete=models.CASCADE,
        related_name="customer_overrides",
    )
    markup_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO_AMOUNT)],
        help_text="Majoration % sur DTF. Vide = grille par défaut.",
    )
    flat_fee_eur = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO_AMOUNT)],
        help_text="Forfait HT. Vide = grille par défaut.",
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text="Décochez pour masquer cette option au client.",
    )

    objects = CustomerProcessingTimeOptionOverrideQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("customer", "option"),
                name="proc_time_cust_option_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("customer", "option"), name="proc_time_cust_opt_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.customer_id} — {self.option.code}"
