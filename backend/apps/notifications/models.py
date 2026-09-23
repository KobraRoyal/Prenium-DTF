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
        ORDER_READY_FOR_PICKUP = "order_ready_for_pickup", "Commande prête au retrait"
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


class StaffPushSubscription(BaseModel):
    """Encrypted Web Push subscription owned by one active workshop member."""

    staff_membership = models.ForeignKey(
        "accounts.StaffMembership",
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint_ciphertext = models.TextField()
    endpoint_digest = models.CharField(max_length=64, unique=True)
    p256dh_ciphertext = models.TextField()
    auth_ciphertext = models.TextField()
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField()
    disabled_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveSmallIntegerField(default=0)
    last_failure_code = models.CharField(max_length=32, blank=True)

    class Meta:
        ordering = ("-last_seen_at",)
        indexes = [
            models.Index(
                fields=("staff_membership", "is_active"),
                name="notif_push_member_active_idx",
            ),
            models.Index(fields=("is_active", "last_seen_at"), name="notif_push_active_seen_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(is_active=True, disabled_at__isnull=True) | models.Q(is_active=False)
                ),
                name="notif_push_active_not_disabled",
            ),
        ]
        verbose_name = "Abonnement Web Push Atelier"
        verbose_name_plural = "Abonnements Web Push Atelier"

    def __str__(self) -> str:
        return f"Abonnement {self.public_id}"


class WorkshopNotificationEvent(BaseModel):
    """Tenant-scoped, idempotent workshop event safe for browser polling."""

    class EventType(models.TextChoices):
        ORDER_SUBMITTED = "workshop.order_submitted", "Nouvelle commande Atelier"

    event_type = models.CharField(max_length=64, choices=EventType.choices)
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="workshop_notification_events",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="workshop_notification_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="published_workshop_notification_events",
    )
    source = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("event_type", "order"),
                name="uniq_workshop_event_type_order",
            ),
        ]
        indexes = [
            models.Index(
                fields=("customer", "created_at"),
                name="notif_workshop_customer_idx",
            ),
            models.Index(fields=("event_type", "created_at"), name="notif_workshop_type_idx"),
        ]
        verbose_name = "Événement Atelier"
        verbose_name_plural = "Événements Atelier"

    def __str__(self) -> str:
        return f"{self.event_type} ({self.public_id})"


class PushDelivery(BaseModel):
    """Idempotent delivery of one workshop event to one browser subscription."""

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        SENDING = "sending", "En cours"
        RETRY = "retry", "À réessayer"
        SENT = "sent", "Envoyée"
        SKIPPED = "skipped", "Ignorée"
        GONE = "gone", "Abonnement expiré"
        FAILED = "failed", "Échec définitif"

    event = models.ForeignKey(
        WorkshopNotificationEvent,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    subscription = models.ForeignKey(
        StaffPushSubscription,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    claimed_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failure_code = models.CharField(max_length=32, blank=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("event", "subscription"),
                name="uniq_workshop_event_subscription",
            ),
            models.CheckConstraint(
                condition=(~models.Q(status="sent") | models.Q(delivered_at__isnull=False)),
                name="notif_delivery_sent_at",
            ),
            models.CheckConstraint(
                condition=(~models.Q(status="sending") | models.Q(claimed_at__isnull=False)),
                name="notif_delivery_claimed_at",
            ),
        ]
        indexes = [
            models.Index(fields=("status", "next_attempt_at"), name="notif_delivery_retry_idx"),
            models.Index(fields=("event", "status"), name="notif_delivery_event_idx"),
            models.Index(fields=("subscription", "status"), name="notif_delivery_sub_idx"),
        ]
        verbose_name = "Livraison Web Push"
        verbose_name_plural = "Livraisons Web Push"

    def __str__(self) -> str:
        return f"Livraison {self.public_id} ({self.status})"
