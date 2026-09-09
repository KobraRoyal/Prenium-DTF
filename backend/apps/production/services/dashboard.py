from __future__ import annotations

from collections import Counter
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, Exists, F, OuterRef, Q
from django.urls import reverse
from django.utils import timezone

from apps.billing.services.production_payment_gate import (
    order_awaits_client_payment,
    production_start_blocked_reason,
)
from apps.orders.models import Order
from apps.orders.references import order_business_number, order_client_reference, order_uuid_short
from apps.production.models import ProductionJob, ProductionPrintRecord
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
            "activity_kpi_rows": self._build_activity_kpi_rows(),
            "production_health": self._build_production_health(),
            "production_trend": self._build_production_trend(),
            "printed_meterage_trend": self._build_printed_meterage_trend(),
            "printable_count": sum(row["print_eligible"] for row in rows),
            "unprinted_of_total": unprinted_total,
            "unprinted_of_batch_count": min(unprinted_total, batch_service.max_batch_size),
            "batch_print_limit": batch_service.max_batch_size,
        }

    def _build_production_trend(self) -> dict[str, object]:
        """Historique réel à sept jours : entrées Atelier et commandes terminées."""
        today = timezone.localdate()
        dates = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
        entries = {
            day: Order.objects.filter(status=Order.Status.SUBMITTED, created_at__date=day).count()
            for day in dates
        }
        completed = {
            day: ProductionJob.objects.filter(
                status=ProductionJob.Status.COMPLETED,
                updated_at__date=day,
            ).count()
            for day in dates
        }
        maximum = max([*entries.values(), *completed.values(), 1])

        def points(values: dict) -> list[dict[str, object]]:
            return [
                {
                    "x": round(index * (100 / (len(dates) - 1)), 2),
                    "y": round(100 - (values[day] / maximum) * 100, 2),
                    "label": day.strftime("%d/%m"),
                    "value": values[day],
                }
                for index, day in enumerate(dates)
            ]

        return {
            "maximum": maximum,
            "labels": [day.strftime("%d/%m") for day in dates],
            "entry_values": [entries[day] for day in dates],
            "completed_values": [completed[day] for day in dates],
            "entries": points(entries),
            "completed": points(completed),
        }

    def build_financial_trend(self) -> dict[str, object]:
        """CA TTC des commandes validées, pour le pilotage administratif Atelier."""
        today = timezone.localdate()
        dates = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
        revenue_by_day = {day: Decimal("0.00") for day in dates}
        orders_by_day = {day: 0 for day in dates}
        priced_orders = Order.objects.filter(
            status=Order.Status.SUBMITTED,
            pricing_status=Order.PricingStatus.PRICED,
            created_at__date__gte=dates[0],
        ).values_list("created_at__date", "total_amount")
        for created_on, total_amount in priced_orders:
            if created_on not in revenue_by_day:
                continue
            revenue_by_day[created_on] += total_amount or Decimal("0.00")
            orders_by_day[created_on] += 1

        total = sum(revenue_by_day.values(), Decimal("0.00"))
        order_count = sum(orders_by_day.values())
        return {
            "labels": [day.strftime("%d/%m") for day in dates],
            "revenue_values": [float(revenue_by_day[day]) for day in dates],
            "seven_day_total": total,
            "today_total": revenue_by_day[today],
            "average_order_total": total / order_count if order_count else Decimal("0.00"),
            "order_count": order_count,
        }

    def _build_printed_meterage_trend(self) -> dict[str, object]:
        """Métrage linéaire issu des preuves d'impression, réimpressions incluses."""
        today = timezone.localdate()
        dates = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
        meterage_by_day = {day: Decimal("0.0000") for day in dates}
        prints_by_day = {day: 0 for day in dates}
        printed_meterages: list[Decimal] = []
        print_records = ProductionPrintRecord.objects.filter(
            printed_at__date__gte=dates[0],
            printed_linear_m__isnull=False,
        ).values_list("printed_at__date", "printed_linear_m")
        for printed_on, printed_linear_m in print_records:
            if printed_on not in meterage_by_day:
                continue
            meterage_by_day[printed_on] += printed_linear_m
            prints_by_day[printed_on] += 1
            printed_meterages.append(printed_linear_m)

        total = sum(meterage_by_day.values(), Decimal("0.0000"))
        print_count = sum(prints_by_day.values())
        today_total = meterage_by_day[today]
        average_per_print = total / print_count if print_count else Decimal("0.0000")
        peak_day_total = max(meterage_by_day.values(), default=Decimal("0.0000"))
        largest_print = max(printed_meterages, default=Decimal("0.0000"))
        active_day_count = sum(1 for meterage in meterage_by_day.values() if meterage > 0)

        def percentage(value: Decimal, reference: Decimal) -> int:
            if reference <= 0:
                return 0
            return min(100, round((value / reference) * 100))

        return {
            "seven_day_total": total,
            "today_total": today_total,
            "average_per_print": average_per_print,
            "print_count": print_count,
            "metric_gauges": [
                {
                    "label": "7 jours",
                    "value": total,
                    "detail": f"{active_day_count}/7 jours actifs",
                    "progress": round((active_day_count / len(dates)) * 100),
                },
                {
                    "label": "Aujourd’hui",
                    "value": today_total,
                    "detail": "vs pic quotidien",
                    "progress": percentage(today_total, peak_day_total),
                },
                {
                    "label": "Par impression",
                    "value": average_per_print,
                    "detail": "vs plus grand tirage",
                    "progress": percentage(average_per_print, largest_print),
                },
            ],
        }

    def _build_production_health(self) -> dict[str, list[dict[str, object]]]:
        """Indicateurs actionnables du responsable de production."""
        now = timezone.now()
        today = timezone.localdate()
        aging_cutoff = now - timedelta(hours=24)
        seven_day_start = today - timedelta(days=6)
        orders_url = reverse("portal:staff-order-list")

        job_counts = ProductionJob.objects.aggregate(
            blocked=Count(
                "pk",
                filter=Q(status=ProductionJob.Status.BLOCKED),
            ),
            overdue=Count(
                "pk",
                filter=(
                    ~Q(status=ProductionJob.Status.COMPLETED)
                    & Q(order__estimated_handover_date__lt=today)
                ),
            ),
            aging=Count(
                "pk",
                filter=(
                    Q(
                        status__in=(
                            ProductionJob.Status.QUEUED,
                            ProductionJob.Status.IN_PROGRESS,
                        )
                    )
                    & (
                        Q(last_transition_at__lt=aging_cutoff)
                        | Q(
                            last_transition_at__isnull=True,
                            created_at__lt=aging_cutoff,
                        )
                    )
                ),
            ),
        )

        recent_prints = ProductionPrintRecord.objects.filter(
            printed_at__date__gte=seven_day_start,
        )
        has_previous_print = Exists(
            ProductionPrintRecord.objects.filter(
                production_job_id=OuterRef("production_job_id"),
                created_at__lt=OuterRef("created_at"),
            )
        )
        print_count = recent_prints.count()
        reprint_count = (
            recent_prints.annotate(
                _has_previous_print=has_previous_print,
            )
            .filter(_has_previous_print=True)
            .count()
        )
        reprint_rate = (
            (Decimal(reprint_count) * Decimal("100") / Decimal(print_count)).quantize(
                Decimal("0.1")
            )
            if print_count
            else Decimal("0.0")
        )

        completed_durations = ProductionJob.objects.filter(
            status=ProductionJob.Status.COMPLETED,
            completed_at__date__gte=seven_day_start,
            started_at__isnull=False,
            completed_at__isnull=False,
            completed_at__gte=F("started_at"),
        ).values_list("started_at", "completed_at")
        duration_seconds = [
            Decimal(str((completed_at - started_at).total_seconds()))
            for started_at, completed_at in completed_durations
        ]
        average_duration_hours = (
            (
                sum(duration_seconds, Decimal("0"))
                / Decimal(len(duration_seconds))
                / Decimal("3600")
            ).quantize(Decimal("0.1"))
            if duration_seconds
            else Decimal("0.0")
        )

        blocked_count = job_counts["blocked"]
        overdue_count = job_counts["overdue"]
        aging_count = job_counts["aging"]
        return {
            "alerts": [
                {
                    "key": "blocked",
                    "label": "OF bloquées",
                    "value": blocked_count,
                    "detail": "À débloquer maintenant" if blocked_count else "Aucun blocage actif",
                    "tone": "is-danger" if blocked_count else "is-success",
                    "href": f"{orders_url}?status={ProductionJob.Status.BLOCKED}",
                },
                {
                    "key": "overdue",
                    "label": "Retards de remise",
                    "value": overdue_count,
                    "detail": "Date de remise dépassée" if overdue_count else "Délais tenus",
                    "tone": "is-danger" if overdue_count else "is-success",
                },
                {
                    "key": "aging",
                    "label": "Encours > 24 h",
                    "value": aging_count,
                    "detail": "Sans progression depuis 24 h" if aging_count else "Encours récents",
                    "tone": "is-warning" if aging_count else "is-success",
                },
            ],
            "quality": [
                {
                    "key": "reprint_rate",
                    "label": "Taux de réimpression",
                    "value": reprint_rate,
                    "unit": "%",
                    "detail": f"{reprint_count} sur {print_count} impressions · 7 j",
                    "tone": "is-warning" if reprint_count else "is-success",
                }
            ],
            "flow": [
                {
                    "key": "average_production_time",
                    "label": "Délai moyen de production",
                    "value": average_duration_hours,
                    "unit": "h",
                    "detail": f"{len(duration_seconds)} OF terminés · 7 j",
                    "tone": "is-neutral",
                }
            ],
        }

    def _build_activity_kpi_rows(self) -> list[dict[str, object]]:
        """KPI de production destinés au responsable Atelier."""
        orders_url = reverse("portal:staff-order-list")
        today = timezone.localdate()
        jobs = ProductionJob.objects.all()
        completed_today = jobs.filter(
            status=ProductionJob.Status.COMPLETED,
            updated_at__date=today,
        ).count()
        rows = [
            {
                "label": "En traitement",
                "value": jobs.filter(status=ProductionJob.Status.QUEUED).count(),
                "hint": "OF à lancer en production.",
                "card_href": f"{orders_url}?status={ProductionJob.Status.QUEUED}",
            },
            {
                "label": "En production",
                "value": jobs.filter(status=ProductionJob.Status.IN_PROGRESS).count(),
                "hint": "OF actuellement sur le flux Atelier.",
                "tone": "is-attention",
                "card_href": f"{orders_url}?status={ProductionJob.Status.IN_PROGRESS}",
            },
            {
                "label": "Prêtes à remettre",
                "value": jobs.filter(status=ProductionJob.Status.READY_TO_SHIP).count(),
                "hint": "Expédition ou retrait à confirmer.",
                "tone": "is-ready",
                "card_href": f"{orders_url}?status={ProductionJob.Status.READY_TO_SHIP}",
            },
            {
                "label": "Terminées aujourd’hui",
                "value": completed_today,
                "hint": "Commandes finalisées depuis ce matin.",
                "card_href": f"{orders_url}?status={ProductionJob.Status.COMPLETED}",
            },
        ]
        maximum = max((int(row["value"]) for row in rows), default=0)
        for row in rows:
            row["share"] = round((int(row["value"]) / maximum) * 100) if maximum else 0
        return rows

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
