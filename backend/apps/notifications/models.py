from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class EmailTemplate(BaseModel):
    """System-wide transactional email override managed by authorised staff."""

    class Event(models.TextChoices):
        ORDER_CREATED = "order_created", "Commande créée"
        PAYMENT_CAPTURED = "payment_captured", "Paiement confirmé"
        ORDER_PROCESSING = "order_processing", "Commande en traitement"
        ORDER_READY_TO_SHIP = "order_ready_to_ship", "Commande traitée"
        ORDER_SHIPPED = "order_shipped", "Commande expédiée"
        ORDER_PRICED = "order_priced", "Commande tarifée"
        ORDER_AWAITING_PAYMENT = (
            "order_awaiting_payment",
            "Paiement carte à effectuer",
        )
        FILE_CORRECTION_REQUESTED = (
            "file_correction_requested",
            "Correction fichier demandée",
        )
        ACCESS_REQUEST_EMAIL_VERIFICATION = (
            "access_request_email_verification",
            "Vérification demande d'accès",
        )
        ACCESS_REQUEST_SUBMITTED_INTERNAL = (
            "access_request_submitted_internal",
            "Nouvelle demande d'accès",
        )
        ACCESS_REQUEST_APPROVED = "access_request_approved", "Demande d'accès validée"
        ACCESS_REQUEST_REJECTED = "access_request_rejected", "Demande d'accès refusée"
        ACCOUNT_ACTIVATED = "account_activated", "Compte activé"
        CUSTOMER_MEMBER_INVITED = "customer_member_invited", "Collaborateur invité"
        STAFF_MEMBER_INVITED = "staff_member_invited", "Collaborateur Atelier invité"
        STAFF_ACCOUNT_ACTIVATED = "staff_account_activated", "Accès Atelier activé"
        PASSWORD_RESET = "password_reset", "Réinitialisation du mot de passe"
        VOLUME_DISCOUNT_TIER_REACHED = (
            "volume_discount_tier_reached",
            "Palier de remise atteint",
        )

    class Audience(models.TextChoices):
        CLIENT = "client", "Client"
        INTERNAL = "internal", "Équipe interne"

    event = models.CharField("Événement", max_length=48, choices=Event.choices)
    audience = models.CharField("Audience", max_length=16, choices=Audience.choices)
    subject_template = models.CharField("Objet", max_length=255)
    body_template = models.TextField("Message")
    is_active = models.BooleanField("Actif", default=True)
    version = models.PositiveIntegerField(default=1, editable=False)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Modifié par",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_email_templates",
    )

    class Meta:
        ordering = ("event", "audience")
        verbose_name = "Modèle d’e-mail"
        verbose_name_plural = "Modèles d’e-mails"
        constraints = [
            models.UniqueConstraint(
                fields=("event", "audience"),
                name="uniq_notification_email_template_event_audience",
            ),
        ]
        indexes = [
            models.Index(
                fields=("audience", "is_active"),
                name="notif_email_aud_active_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        from apps.notifications.services.email_templates import validate_template_pair

        validate_template_pair(
            subject_template=self.subject_template,
            body_template=self.body_template,
        )

    def __str__(self) -> str:
        return f"{self.get_event_display()} — {self.get_audience_display()}"


class VolumeDiscountTierNotification(BaseModel):
    """Trace idempotente d'un palier mensuel notifié à un client."""

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        SENDING = "sending", "En cours d’envoi"
        SENT = "sent", "Envoyé"
        SKIPPED = "skipped", "Ignoré"
        FAILED = "failed", "Échec d’envoi"

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="volume_discount_notifications",
    )
    month = models.DateField("Mois civil")
    threshold_linear_m = models.DecimalField(
        "Seuil atteint (m linéaires)",
        max_digits=12,
        decimal_places=4,
    )
    monthly_volume_linear_m = models.DecimalField(
        "Volume mensuel (m linéaires)",
        max_digits=12,
        decimal_places=4,
    )
    discount_percent = models.DecimalField(
        "Remise (%)",
        max_digits=5,
        decimal_places=2,
    )
    discount_amount = models.DecimalField(
        "Remise cumulée HT (EUR)",
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    delivery_started_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("-month", "-threshold_linear_m", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("customer", "month", "threshold_linear_m"),
                name="uniq_customer_month_volume_tier_notification",
            ),
            models.CheckConstraint(
                condition=models.Q(threshold_linear_m__gt=0),
                name="volume_tier_notification_threshold_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(monthly_volume_linear_m__gte=0),
                name="volume_tier_notification_volume_nonnegative",
            ),
            models.CheckConstraint(
                condition=(models.Q(discount_percent__gt=0) & models.Q(discount_percent__lte=100)),
                name="volume_tier_notification_discount_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("customer", "month", "status"),
                name="notif_customer_month_tier_idx",
            ),
        ]
        verbose_name = "Notification de palier de remise"
        verbose_name_plural = "Notifications de paliers de remise"

    def __str__(self) -> str:
        return f"{self.customer} — {self.month:%m/%Y} — {self.threshold_linear_m} m"
