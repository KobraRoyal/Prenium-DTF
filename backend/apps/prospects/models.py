from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.customers.models import Customer


class ProspectProfile(BaseModel):
    """Profil qualifié créé à l’issue du tunnel prospect (distinct du checkout)."""

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
        NEW = "new", "Nouveau"
        QUALIFIED = "qualified", "Qualifié"
        ACCOUNT_CREATED = "account_created", "Compte créé"
        CONVERTED = "converted", "Converti"

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
        default=Status.NEW,
        db_index=True,
    )
    source = models.CharField(max_length=64, default="tunnel_web")

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("status", "created_at")),
            models.Index(fields=("email",)),
        ]

    def __str__(self) -> str:
        return f"{self.company} ({self.email})"
