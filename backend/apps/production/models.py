import uuid

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.orders.models import Order


def generate_production_scan_identifier() -> str:
    return f"PJSCAN-{uuid.uuid4().hex[:20].upper()}"


class ProductionJobQuerySet(models.QuerySet):
    def for_order(self, order):
        return self.filter(order=order)


class ProductionJobTransitionQuerySet(models.QuerySet):
    def for_job(self, production_job):
        return self.filter(production_job=production_job)


class ProductionJobScanLogQuerySet(models.QuerySet):
    def for_job(self, production_job):
        return self.filter(production_job=production_job)


class ProductionJob(BaseModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        IN_PROGRESS = "in_progress", "In progress"
        READY_TO_SHIP = "ready_to_ship", "Ready to ship"
        BLOCKED = "blocked", "Blocked"
        COMPLETED = "completed", "Completed"

    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="production_job",
    )
    manufacturing_order_number = models.CharField(max_length=64, unique=True)
    scan_identifier = models.CharField(
        max_length=64,
        unique=True,
        default=generate_production_scan_identifier,
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.QUEUED)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_transition_at = models.DateTimeField(null=True, blank=True)
    last_transition_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="production_jobs_last_changed",
    )
    last_transition_note = models.CharField(max_length=255, blank=True)

    objects = ProductionJobQuerySet.as_manager()

    class Meta:
        ordering = ("-updated_at", "-created_at")
        permissions = [
            ("scan_productionjob", "Can resolve production job by scan"),
            ("scan_transition_productionjob", "Can transition production job by scan"),
            ("transition_productionjob", "Can transition production job"),
        ]
        indexes = [
            models.Index(fields=("status", "updated_at")),
            models.Index(fields=("manufacturing_order_number",)),
        ]

    def __str__(self) -> str:
        return f"{self.manufacturing_order_number} - {self.status}"


class ProductionJobTransition(BaseModel):
    production_job = models.ForeignKey(
        ProductionJob,
        on_delete=models.CASCADE,
        related_name="transitions",
    )
    from_status = models.CharField(max_length=32, choices=ProductionJob.Status.choices)
    to_status = models.CharField(max_length=32, choices=ProductionJob.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="production_job_transitions",
    )
    reason = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=32, default="staff_api")

    objects = ProductionJobTransitionQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("production_job", "created_at")),
            models.Index(fields=("to_status", "created_at")),
        ]

    def __str__(self) -> str:
        return (
            f"{self.production_job.manufacturing_order_number}: "
            f"{self.from_status} -> {self.to_status}"
        )


class ProductionJobScanLog(BaseModel):
    class Action(models.TextChoices):
        RESOLVE = "resolve", "Resolve"
        TRANSITION = "transition", "Transition"

    class Outcome(models.TextChoices):
        RESOLVED = "resolved", "Resolved"
        TRANSITIONED = "transitioned", "Transitioned"
        NOT_FOUND = "not_found", "Not found"
        REJECTED = "rejected", "Rejected"

    production_job = models.ForeignKey(
        ProductionJob,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scan_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="production_job_scan_logs",
    )
    scan_identifier = models.CharField(max_length=64)
    action = models.CharField(max_length=16, choices=Action.choices)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    requested_status = models.CharField(max_length=32, blank=True)
    source = models.CharField(max_length=32, default="staff_scan_api")
    message = models.CharField(max_length=255, blank=True)

    objects = ProductionJobScanLogQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("scan_identifier", "created_at")),
            models.Index(fields=("action", "created_at")),
            models.Index(fields=("production_job", "created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.scan_identifier} ({self.action}/{self.outcome})"
