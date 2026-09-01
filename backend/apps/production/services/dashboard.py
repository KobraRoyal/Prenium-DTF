from __future__ import annotations

from collections import Counter

from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse

from apps.billing.services.production_payment_gate import (
    order_awaits_client_payment,
    production_start_blocked_reason,
)
from apps.orders.models import Order
from apps.orders.references import order_business_number, order_client_reference, order_uuid_short
from apps.production.models import ProductionJob
from apps.production.services.manufacturing_order_batch import ManufacturingOrderBatchService
from apps.production.services.staff_order_list_filters import StaffOrderListFilterService
from apps.production.services.workflow import ProductionWorkflowService
from apps.uploads.models import OrderUploadDriveSync, OrderUploadReview


def _file_count_label(count: int) -> str:
    return f"{count} fichier" if count == 1 else f"{count} fichiers"


class AtelierDashboardService:
    """Tour de contrôle : commandes soumises dont l'OF PDF n'a pas encore été émis."""

    pilotage_url = "/staff/atelier/pilotage/"

    def build_dashboard(self) -> dict[str, object]:
        all_orders = list(self._unissued_orders_queryset())
        rows = [self._serialize_order(order=order) for order in all_orders]
        queue_counts = StaffOrderListFilterService().count_by_queue(Order.objects.all())
        metrics = self._build_metrics(queue_counts)
        batch_service = ManufacturingOrderBatchService()
        unprinted_total = metrics["unprinted"]
        return {
            "rows": rows,
            "metrics": metrics,
            "kpi_rows": self._build_kpi_rows(
                metrics=metrics,
                unprinted_total=unprinted_total,
            ),
            "printable_count": sum(row["print_eligible"] for row in rows),
            "unprinted_of_total": unprinted_total,
            "unprinted_of_batch_count": min(unprinted_total, batch_service.max_batch_size),
            "batch_print_limit": batch_service.max_batch_size,
        }

    def _build_metrics(self, queue_counts: dict[str, int]) -> dict[str, int]:
        return {
            "unprinted": queue_counts["unprinted"],
            "pending_review": queue_counts["to_review"],
            "changes_requested": queue_counts["changes"],
            "files_validated": queue_counts["approved"],
        }

    def _build_kpi_rows(
        self,
        *,
        metrics: dict[str, int],
        unprinted_total: int,
    ) -> list[dict[str, object]]:
        orders_url = reverse("portal:staff-order-list")
        return [
            {
                "label": "OF non imprimés",
                "value": unprinted_total,
                "hint": "Voir la liste filtrée des OF à émettre.",
                "tone": "is-ready" if unprinted_total else "",
                "card_href": f"{orders_url}?queue=unprinted",
            },
            {
                "label": "À contrôler",
                "value": metrics["pending_review"],
                "hint": "OF émis, fichiers à valider dans le pilotage.",
                "tone": "is-attention" if metrics["pending_review"] else "",
                "card_href": f"{orders_url}?queue=to_review",
            },
            {
                "label": "Corrections client",
                "value": metrics["changes_requested"],
                "hint": "OF émis, visuels à corriger par le client.",
                "tone": "is-danger" if metrics["changes_requested"] else "",
                "card_href": f"{orders_url}?queue=changes",
            },
            {
                "label": "Fichiers validés",
                "value": metrics["files_validated"],
                "hint": "OF émis et tous les fichiers approuvés.",
                "tone": "" if not metrics["files_validated"] else "is-ready",
                "card_href": f"{orders_url}?queue=approved",
            },
        ]

    def build_order_focus(self, *, order: Order) -> dict[str, object]:
        """Expose la seule prochaine action utile à la fiche commande Atelier."""
        focus = self._serialize_order(order=order)
        focus["has_drive_issues"] = any(
            self._drive_needs_attention(upload) for upload in order.uploads.all()
        )
        action_label, action_message = self._focus_action(focus=focus)
        focus["action_label"] = action_label
        focus["action_message"] = action_message
        return focus

    def _unissued_orders_queryset(self):
        return (
            ManufacturingOrderBatchService()
            ._unissued_queryset()
            .select_related("production_job__assigned_machine")
        )

    def _serialize_order(self, *, order: Order) -> dict[str, object]:
        uploads = list(order.uploads.all())
        review_counter = Counter(self._review_status(upload) for upload in uploads)
        review_status, review_label, review_tone = self._review_state(
            upload_count=len(uploads),
            counter=review_counter,
        )
        try:
            production_job = order.production_job
        except ProductionJob.DoesNotExist:
            production_job = None

        production_status = (
            production_job.status if production_job is not None else ProductionJob.Status.QUEUED
        )
        assigned_machine = production_job.assigned_machine if production_job is not None else None
        all_approved = bool(uploads) and review_counter[OrderUploadReview.Status.APPROVED] == len(
            uploads
        )
        ready_to_print = bool(
            all_approved
            and production_job is not None
            and production_status == ProductionJob.Status.QUEUED
            and not order_awaits_client_payment(order)
            and production_start_blocked_reason(order) is None
        )
        print_eligible = bool(
            production_job is not None
            and production_job.of_document_issued_at is None
            and production_status != ProductionJob.Status.COMPLETED
            and order.status == Order.Status.SUBMITTED
        )
        files_to_process_count, files_to_process_label = self._files_to_process_summary(
            upload_count=len(uploads),
            review_status=review_status,
            review_counter=review_counter,
        )
        next_action, next_panel = self._next_action(
            review_status=review_status,
            production_status=production_status,
            order=order,
        )

        return {
            "order": order,
            "order_uuid_short": order_uuid_short(order),
            "order_business_number": order_business_number(order),
            "order_client_label": order_client_reference(order),
            # Compat listes / breadcrumbs : prioriser le n° métier, sinon UUID court.
            "order_reference": order_business_number(order) or order_uuid_short(order).upper(),
            "of_number": production_job.manufacturing_order_number
            if production_job is not None
            else "OF à générer",
            "review_status": review_status,
            "review_label": review_label,
            "review_tone": review_tone,
            "approved_count": review_counter[OrderUploadReview.Status.APPROVED],
            "upload_count": len(uploads),
            "files_to_process_count": files_to_process_count,
            "files_to_process_label": files_to_process_label,
            "production_status": production_status,
            "production_label": ProductionWorkflowService.document_status_labels.get(
                production_status,
                production_status,
            ),
            "assigned_machine": assigned_machine,
            "machine_label": (
                f"{assigned_machine.code} · {assigned_machine.name}"
                if assigned_machine is not None
                else "Machine non attribuée"
            ),
            "machine_missing": assigned_machine is None,
            "ready_to_print": ready_to_print,
            "print_eligible": print_eligible,
            "of_unissued": print_eligible,
            "next_action": next_action,
            "next_panel": next_panel,
            "next_via_operations": next_action in {"Contrôler", "Suivre", "Lancer", "Expédier"},
        }

    def _files_to_process_summary(
        self,
        *,
        upload_count: int,
        review_status: str,
        review_counter: Counter,
    ) -> tuple[int, str]:
        if upload_count == 0:
            return 0, "Aucun fichier"
        pending = review_counter[OrderUploadReview.Status.PENDING]
        changes = review_counter[OrderUploadReview.Status.CHANGES_REQUESTED]
        to_process = pending + changes
        if review_status == "missing_files":
            return 0, "Aucun fichier"
        if to_process == 0:
            suffix = "" if upload_count == 1 else "s"
            return 0, f"{_file_count_label(upload_count)} validé{suffix}"
        if to_process == upload_count:
            return to_process, f"{_file_count_label(to_process)} à traiter"
        return to_process, (f"{to_process} à traiter sur {_file_count_label(upload_count)}")

    def _review_state(self, *, upload_count: int, counter: Counter) -> tuple[str, str, str]:
        if upload_count == 0:
            return "missing_files", "Aucun fichier", "is-danger"
        changes = counter[OrderUploadReview.Status.CHANGES_REQUESTED]
        if changes:
            return (
                "changes_requested",
                f"{changes} correction(s) demandée(s)",
                "is-danger",
            )
        pending = counter[OrderUploadReview.Status.PENDING]
        if pending:
            return "pending", f"{pending} à contrôler", "is-warning"
        return "approved", f"{upload_count}/{upload_count} approuvés", "is-success"

    def _next_action(
        self,
        *,
        review_status: str,
        production_status: str,
        order: Order,
    ) -> tuple[str, str]:
        if review_status in {"missing_files", "changes_requested", "pending"}:
            return "Contrôler", "inspection"
        if order_awaits_client_payment(order):
            return "Attendre paiement", "billing"
        if production_start_blocked_reason(order) is not None:
            return "Tarifer", "production"
        if production_status == ProductionJob.Status.READY_TO_SHIP:
            return "Expédier", "shipping"
        if production_status == ProductionJob.Status.COMPLETED:
            return "Consulter", "production"
        if production_status == ProductionJob.Status.IN_PROGRESS:
            return "Suivre", "production"
        return "Lancer", "production"

    def _focus_action(self, *, focus: dict[str, object]) -> tuple[str, str]:
        review_status = str(focus["review_status"])
        production_status = str(focus["production_status"])
        if review_status == "missing_files":
            return (
                "Consulter les visuels",
                "Aucun visuel reçu. La production ne peut pas démarrer.",
            )
        if review_status == "changes_requested":
            return (
                "Suivre les corrections",
                f"{focus['review_label']}. Attendez les fichiers corrigés avant la production.",
            )
        if review_status == "pending":
            return (
                "Contrôler les visuels",
                f"{focus['review_label']}. Validez-les avant de lancer la production.",
            )
        if production_status == ProductionJob.Status.BLOCKED:
            return (
                "Lever le blocage",
                "La production est bloquée et nécessite une décision Atelier.",
            )
        if production_status == ProductionJob.Status.READY_TO_SHIP:
            return "Préparer l’expédition", "La production est terminée et prête à être expédiée."
        if production_status == ProductionJob.Status.IN_PROGRESS:
            return "Suivre la production", "La commande est en cours de fabrication."
        if production_status == ProductionJob.Status.COMPLETED:
            return "Consulter la production", "La fabrication est terminée. Vérifiez la clôture."
        return (
            "Préparer la production",
            "Tous les visuels sont approuvés. Sélectionnez une machine s’il y en a "
            "plusieurs, saisissez le métrage, puis confirmez l’impression.",
        )

    def _drive_needs_attention(self, upload) -> bool:
        try:
            drive_sync = upload.drive_sync
        except ObjectDoesNotExist:
            return True
        return bool(
            drive_sync.status != OrderUploadDriveSync.Status.SYNCED or drive_sync.last_error
        )

    def _review_status(self, upload) -> str:
        try:
            return upload.atelier_review.status
        except ObjectDoesNotExist:
            return OrderUploadReview.Status.PENDING
