from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class AuditLogEntry(BaseModel):
    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    action = models.CharField(max_length=128)
    target_model = models.CharField(max_length=128, blank=True)
    target_public_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SUCCESS)
    message = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("action", "created_at")),
            models.Index(fields=("target_model", "target_public_id")),
        ]

    def __str__(self) -> str:
        return f"{self.action} ({self.status})"
