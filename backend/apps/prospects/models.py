from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.customers.models import Customer


class ProspectProfile(BaseModel):
    """Demande d'accès pré-tenant soumise avant création du compte client."""

    class ActivityType(models.TextChoices):
        BRAND = "brand", "Marque textile"
        PRINTER = "printer", "Imprimeur / revendeur"
        WORKSHOP = "workshop", "Atelier"
        CREATOR = "creator", "Créateur / studio"
        OTHER = "other", "Autre"

    class ServiceInterest(models.TextChoices):
        DTF_METER = "dtf_meter", "DTF au mètre"
        FILE_PREP = "file_prep", "Préparation de fichier DTF"
        BOTH = "both", "Les deux"
        UNSURE = "unsure", "Je ne sais pas encore"

    class ProjectTiming(models.TextChoices):
        IMMEDIATE = "immediate", "Besoin immédiat"
        ONGOING = "ongoing", "Projet en cours"
        EXPLORING = "exploring", "Exploration / veille"

    class MonthlyVolume(models.TextChoices):
        LT10 = "lt10", "Moins de 10 mètres"
        M10_50 = "10_50", "10 à 50 mètres"
        M50_200 = "50_200", "50 à 200 mètres"
        GT200 = "gt200", "200 mètres et plus"

    class OrderFrequency(models.TextChoices):
        PUNCTUAL = "punctual", "Ponctuel"
        MONTHLY = "monthly", "Mensuel"
        REGULAR = "regular", "Régulier"
        INTENSIVE = "intensive", "Intensif"

    class Urgency(models.TextChoices):
        LOW = "low", "Faible"
        MEDIUM = "medium", "Moyenne"
        HIGH = "high", "Élevée"

    class Status(models.TextChoices):
        PENDING_EMAIL_VERIFICATION = (
            "pending_email_verification",
            "E-mail à vérifier",
        )
        PENDING_REVIEW = "pending_review", "En attente de validation"
        NEEDS_INFORMATION = "needs_information", "Informations complémentaires requises"
        APPROVED_PENDING_ACTIVATION = (
            "approved_pending_activation",
            "Validée — activation requise",
        )
        ACTIVE = "active", "Compte actif"
        REJECTED = "rejected", "Refusée"
        EXPIRED = "expired", "Expirée"
        CANCELLED = "cancelled", "Annulée"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="prospect_profile",
        null=True,
        blank=True,
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prospect_profiles",
    )

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(db_index=True)
    phone = models.CharField(max_length=32)
    company = models.CharField(max_length=255)
    country = models.CharField(max_length=2)
    siren = models.CharField(max_length=9, blank=True)
    vat_number = models.CharField(max_length=32, blank=True)
    normalized_email = models.EmailField(blank=True, db_index=True)

    activity_type = models.CharField(max_length=32, choices=ActivityType.choices)
    service_interest = models.CharField(max_length=32, choices=ServiceInterest.choices)
    main_goal = models.CharField(max_length=500, blank=True)
    project_timing = models.CharField(max_length=32, choices=ProjectTiming.choices)

    monthly_volume = models.CharField(max_length=16, choices=MonthlyVolume.choices)
    order_frequency = models.CharField(max_length=16, choices=OrderFrequency.choices)
    urgency = models.CharField(max_length=16, choices=Urgency.choices)

    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING_EMAIL_VERIFICATION,
        db_index=True,
    )
    is_open = models.BooleanField(default=False, db_index=True)
    verification_version = models.PositiveIntegerField(default=1)
    submitted_at = models.DateTimeField(null=True, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_prospect_profiles",
    )
    review_note = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=64, default="tunnel_web")

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("status", "created_at")),
            models.Index(fields=("email",)),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("normalized_email",),
                condition=models.Q(is_open=True),
                name="uniq_open_prospect_normalized_email",
            ),
        ]
        permissions = [
            ("review_prospectprofile", "Can approve or reject access requests"),
        ]

    def __str__(self) -> str:
        return f"{self.company} ({self.email})"
