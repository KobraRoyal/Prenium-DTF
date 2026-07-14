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
        FILE_CORRECTION_REQUESTED = (
            "file_correction_requested",
            "Correction fichier demandée",
        )

    class Audience(models.TextChoices):
        CLIENT = "client", "Client"
        INTERNAL = "internal", "Équipe interne"

    event = models.CharField("Événement", max_length=32, choices=Event.choices)
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
