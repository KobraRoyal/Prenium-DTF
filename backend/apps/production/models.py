import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

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


class ProductionMachineQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=ProductionMachine.Status.ACTIVE)


class ProductionMachine(BaseModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Disponible"
        MAINTENANCE = "maintenance", "Maintenance"
        RETIRED = "retired", "Retirée du parc"

    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    manufacturer = models.CharField(max_length=80, blank=True)
    model_name = models.CharField(max_length=120, blank=True)
    serial_number = models.CharField(max_length=120, blank=True)
    location = models.CharField(max_length=120, blank=True)
    max_print_width_cm = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    notes = models.TextField(blank=True)
    status_changed_at = models.DateTimeField(default=timezone.now)
    status_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="production_machines_status_changed",
    )

    objects = ProductionMachineQuerySet.as_manager()

    class Meta:
        ordering = ("code", "name")
        permissions = [
            ("manage_productionmachine", "Can manage the DTF machine fleet"),
            ("assign_productionmachine", "Can assign production jobs to DTF machines"),
            ("confirm_productionprint", "Can confirm a production print"),
        ]
        constraints = [
            models.UniqueConstraint(
                Lower("code"),
                name="production_machine_code_ci_unique",
            ),
        ]
        indexes = [
            models.Index(fields=("status", "name")),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


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
    assigned_machine = models.ForeignKey(
        ProductionMachine,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assigned_jobs",
    )
    machine_assigned_at = models.DateTimeField(null=True, blank=True)
    machine_assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="production_jobs_machine_assigned",
    )

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
            models.Index(fields=("assigned_machine", "status", "updated_at")),
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


class ProductionJobMachineAssignment(BaseModel):
    production_job = models.ForeignKey(
        ProductionJob,
        on_delete=models.PROTECT,
        related_name="machine_assignments",
    )
    machine = models.ForeignKey(
        ProductionMachine,
        on_delete=models.PROTECT,
        related_name="job_assignments",
    )
    previous_machine = models.ForeignKey(
        ProductionMachine,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="job_reassignments_from",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="production_machine_assignments",
    )
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="production_machine_assignments_ended",
    )
    source = models.CharField(max_length=32, default="staff_portal")
    reason = models.CharField(max_length=255, blank=True)
    machine_public_id_snapshot = models.UUIDField()
    machine_code_snapshot = models.CharField(max_length=32)
    machine_name_snapshot = models.CharField(max_length=120)
    previous_machine_public_id_snapshot = models.UUIDField(null=True, blank=True)
    previous_machine_code_snapshot = models.CharField(max_length=32, blank=True)
    previous_machine_name_snapshot = models.CharField(max_length=120, blank=True)
    printing_started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("production_job",),
                condition=models.Q(ended_at__isnull=True),
                name="production_one_open_machine_assignment_per_job",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(previous_machine__isnull=True)
                    | ~models.Q(previous_machine=models.F("machine"))
                ),
                name="production_machine_reassignment_changes_machine",
            ),
        ]
        indexes = [
            models.Index(fields=("production_job", "created_at")),
            models.Index(fields=("machine", "created_at")),
            models.Index(fields=("machine", "ended_at")),
        ]

    def __str__(self) -> str:
        return f"{self.production_job.manufacturing_order_number} → {self.machine_code_snapshot}"


class ProductionPrintRecord(BaseModel):
    production_job = models.ForeignKey(
        ProductionJob,
        on_delete=models.PROTECT,
        related_name="print_records",
    )
    machine = models.ForeignKey(
        ProductionMachine,
        on_delete=models.PROTECT,
        related_name="print_records",
    )
    assignment = models.ForeignKey(
        ProductionJobMachineAssignment,
        on_delete=models.PROTECT,
        related_name="print_records",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="production_print_records",
    )
    printed_at = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=32, default="staff_portal")
    note = models.CharField(max_length=255, blank=True)
    request_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    machine_public_id_snapshot = models.UUIDField()
    machine_code_snapshot = models.CharField(max_length=32)
    machine_name_snapshot = models.CharField(max_length=120)
    manufacturing_order_number_snapshot = models.CharField(max_length=64)
    order_public_id_snapshot = models.UUIDField()
    customer_public_id_snapshot = models.UUIDField()

    class Meta:
        ordering = ("-printed_at", "-created_at")
        indexes = [
            models.Index(fields=("production_job", "printed_at")),
            models.Index(fields=("machine", "printed_at")),
        ]

    def __str__(self) -> str:
        return (
            f"{self.manufacturing_order_number_snapshot} "
            f"imprimé sur {self.machine_code_snapshot}"
        )
