from __future__ import annotations

from django.core.exceptions import ValidationError

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.production.models import ProductionJobScanLog
from apps.production.services.workflow import ProductionWorkflowService


class ProductionScanService:
    def __init__(self):
        self.workflow_service = ProductionWorkflowService()

    def resolve_scan(self, *, scan_identifier: str, actor, source: str):
        normalized_scan_identifier = self.normalize_scan_identifier(scan_identifier)
        production_job = self._get_job_queryset().filter(
            scan_identifier=normalized_scan_identifier
        ).first()

        if production_job is None:
            self._record_scan_log(
                production_job=None,
                actor=actor,
                scan_identifier=normalized_scan_identifier,
                action=ProductionJobScanLog.Action.RESOLVE,
                outcome=ProductionJobScanLog.Outcome.NOT_FOUND,
                source=source,
                message="Unknown scan identifier.",
            )
            record_event(
                action="production.scan_rejected",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                status=AuditLogEntry.Status.FAILURE,
                message="Unknown scan identifier.",
                metadata={
                    "scan_identifier": normalized_scan_identifier,
                    "source": source,
                    "action": ProductionJobScanLog.Action.RESOLVE,
                },
            )
            return None

        self._record_scan_log(
            production_job=production_job,
            actor=actor,
            scan_identifier=normalized_scan_identifier,
            action=ProductionJobScanLog.Action.RESOLVE,
            outcome=ProductionJobScanLog.Outcome.RESOLVED,
            source=source,
            message="Scan resolved.",
        )
        record_event(
            action="production.scan_resolved",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=production_job,
            metadata={
                "order_public_id": str(production_job.order.public_id),
                "customer_public_id": str(production_job.order.customer.public_id),
                "production_job_public_id": str(production_job.public_id),
                "manufacturing_order_number": production_job.manufacturing_order_number,
                "scan_identifier": normalized_scan_identifier,
                "source": source,
                "action": ProductionJobScanLog.Action.RESOLVE,
            },
        )
        self.workflow_service.record_view_event(
            production_job=production_job,
            actor=actor,
            source=source,
        )
        return self._get_job_queryset().filter(pk=production_job.pk).first()

    def transition_by_scan(
        self,
        *,
        scan_identifier: str,
        to_status: str,
        actor,
        source: str,
        reason: str = "",
    ):
        production_job = self.resolve_scan(
            scan_identifier=scan_identifier,
            actor=actor,
            source=source,
        )
        if production_job is None:
            return None, None

        normalized_scan_identifier = self.normalize_scan_identifier(scan_identifier)
        try:
            updated_job, transition = self.workflow_service.transition_existing_job(
                production_job=production_job,
                actor=actor,
                source=source,
                to_status=to_status,
                reason=reason,
            )
        except ValidationError as error:
            self._record_scan_log(
                production_job=production_job,
                actor=actor,
                scan_identifier=normalized_scan_identifier,
                action=ProductionJobScanLog.Action.TRANSITION,
                outcome=ProductionJobScanLog.Outcome.REJECTED,
                requested_status=str(to_status).strip(),
                source=source,
                message=self._extract_validation_message(error),
            )
            raise

        self._record_scan_log(
            production_job=updated_job,
            actor=actor,
            scan_identifier=normalized_scan_identifier,
            action=ProductionJobScanLog.Action.TRANSITION,
            outcome=ProductionJobScanLog.Outcome.TRANSITIONED,
            requested_status=transition.to_status,
            source=source,
            message="Scan transition applied.",
        )
        updated_job = self._get_job_queryset().filter(pk=updated_job.pk).first()
        return updated_job, transition

    def normalize_scan_identifier(self, scan_identifier: str) -> str:
        normalized = str(scan_identifier).strip().upper()
        if not normalized:
            raise ValidationError("Scan identifier is required.")
        return normalized[:64]

    def serialize_scan_log(self, scan_log: ProductionJobScanLog) -> dict[str, object]:
        return {
            "public_id": str(scan_log.public_id),
            "action": scan_log.action,
            "outcome": scan_log.outcome,
            "scan_identifier": scan_log.scan_identifier,
            "requested_status": scan_log.requested_status,
            "source": scan_log.source,
            "message": scan_log.message,
            "created_at": scan_log.created_at.isoformat(),
            "actor": {
                "public_id": str(scan_log.actor.public_id),
                "email": scan_log.actor.email,
            }
            if scan_log.actor is not None
            else None,
        }

    def _extract_validation_message(self, error: ValidationError) -> str:
        if hasattr(error, "messages") and error.messages:
            return str(error.messages[0])
        return "Scan transition rejected."

    def _record_scan_log(
        self,
        *,
        production_job,
        actor,
        scan_identifier: str,
        action: str,
        outcome: str,
        source: str,
        message: str = "",
        requested_status: str = "",
    ) -> ProductionJobScanLog:
        return ProductionJobScanLog.objects.create(
            production_job=production_job,
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            scan_identifier=scan_identifier,
            action=action,
            outcome=outcome,
            requested_status=requested_status[:32],
            source=source,
            message=message[:255],
        )

    def _get_job_queryset(self):
        return self.workflow_service._get_job_queryset().prefetch_related(
            "scan_logs",
            "scan_logs__actor",
        )
