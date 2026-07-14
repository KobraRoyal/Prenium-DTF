from __future__ import annotations

from collections import Counter

from django.core.exceptions import ObjectDoesNotExist

from apps.core.public_refs import short_public_ref
from apps.orders.models import Order
from apps.production.models import ProductionJob
from apps.production.services.workflow import ProductionWorkflowService
from apps.uploads.models import OrderUploadDriveSync, OrderUploadReview


class AtelierDashboardService:
    """Construit la file opérationnelle Atelier sans données commerciales inutiles."""

    recent_limit = 12
    default_tab = "to_review"
    tab_definitions = (
        ("to_review", "À traiter"),
        ("ready", "Prêts à imprimer"),
        ("production", "En production"),
        ("all", "Tous"),
    )

    def build_dashboard(self, *, active_tab: str | None = None) -> dict[str, object]:
        normalized_tab = self._normalize_tab(active_tab)
        orders = list(self._recent_orders_queryset()[: self.recent_limit])
        all_rows = [self._serialize_order(order=order) for order in orders]
        rows = [row for row in all_rows if self._row_matches_tab(row=row, tab=normalized_tab)]
        tab_counts = {
            tab: sum(self._row_matches_tab(row=row, tab=tab) for row in all_rows)
            for tab, _label in self.tab_definitions
        }
        return {
            "rows": rows,
            "active_tab": normalized_tab,
            "tabs": [
                {
                    "key": tab,
                    "label": label,
                    "count": tab_counts[tab],
                    "is_active": tab == normalized_tab,
                }
                for tab, label in self.tab_definitions
            ],
            "metrics": {
                "pending_review": sum(
                    row["review_status"] in {"missing_files", "pending"} for row in all_rows
                ),
                "changes_requested": sum(
                    row["review_status"] == "changes_requested" for row in all_rows
                ),
                "ready_to_print": sum(row["ready_to_print"] for row in all_rows),
                "in_production": sum(
                    row["production_status"]
                    in {ProductionJob.Status.IN_PROGRESS, ProductionJob.Status.BLOCKED}
                    for row in all_rows
                ),
            },
            "printable_count": sum(row["print_eligible"] for row in rows),
        }

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

    def _normalize_tab(self, active_tab: str | None) -> str:
        allowed = {tab for tab, _label in self.tab_definitions}
        return active_tab if active_tab in allowed else self.default_tab

    def _row_matches_tab(self, *, row: dict[str, object], tab: str) -> bool:
        if tab == "to_review":
            return row["review_status"] in {"missing_files", "pending", "changes_requested"}
        if tab == "ready":
            return bool(row["ready_to_print"])
        if tab == "production":
            return row["production_status"] in {
                ProductionJob.Status.IN_PROGRESS,
                ProductionJob.Status.BLOCKED,
            }
        return True

    def _recent_orders_queryset(self):
        return (
            Order.objects.filter(status=Order.Status.SUBMITTED)
            .select_related("customer", "production_job")
            .prefetch_related("uploads", "uploads__atelier_review")
            .order_by("-created_at")
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
        all_approved = bool(uploads) and review_counter[OrderUploadReview.Status.APPROVED] == len(
            uploads
        )
        ready_to_print = bool(
            all_approved
            and production_job is not None
            and production_status == ProductionJob.Status.QUEUED
        )
        print_eligible = bool(
            all_approved
            and production_job is not None
            and production_status != ProductionJob.Status.COMPLETED
        )
        next_action, next_panel = self._next_action(
            review_status=review_status,
            production_status=production_status,
        )

        return {
            "order": order,
            "order_reference": short_public_ref(order.public_id).upper(),
            "of_number": production_job.manufacturing_order_number
            if production_job is not None
            else "OF à générer",
            "review_status": review_status,
            "review_label": review_label,
            "review_tone": review_tone,
            "approved_count": review_counter[OrderUploadReview.Status.APPROVED],
            "upload_count": len(uploads),
            "production_status": production_status,
            "production_label": ProductionWorkflowService.document_status_labels.get(
                production_status,
                production_status,
            ),
            "ready_to_print": ready_to_print,
            "print_eligible": print_eligible,
            "next_action": next_action,
            "next_panel": next_panel,
        }

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

    def _next_action(self, *, review_status: str, production_status: str) -> tuple[str, str]:
        if review_status in {"missing_files", "changes_requested", "pending"}:
            return "Contrôler", "inspection"
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
            "Tous les visuels sont approuvés. Vérifiez le métrage puis lancez la fabrication.",
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
