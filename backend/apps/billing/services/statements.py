from __future__ import annotations

import csv
import hashlib
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from io import StringIO

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.formats import date_format

from apps.auditlog.services import record_event
from apps.billing.models import BillingStatement
from apps.catalog.models import CatalogService
from apps.customers.models import Customer
from apps.orders.models import Order

TWOPLACES = Decimal("0.01")
FOURPLACES = Decimal("0.0001")


def _next_month(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


def _statement_reference(statement: BillingStatement) -> str:
    return (
        f"REL-{statement.period_start:%Y%m}-"
        f"{str(statement.public_id).split('-', maxsplit=1)[0].upper()}"
    )


def _safe_csv_text(value: object) -> str:
    text = str(value or "").replace("\x00", "").strip()
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{text}"
    return text


def _csv_decimal(value: object, *, places: int = 2) -> str:
    try:
        decimal_value = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("Une valeur monétaire du snapshot comptable est invalide.") from exc
    pattern = Decimal("1").scaleb(-places)
    return f"{decimal_value.quantize(pattern, rounding=ROUND_HALF_UP):f}".replace(".", ",")


class BillingStatementService:
    """Clôture et exporte un relevé mensuel destiné à la facturation externe."""

    def list_for_customer(self, *, customer: Customer, limit: int = 12):
        return (
            BillingStatement.objects.for_customer(customer)
            .annotate(order_count=Count("orders"))
            .order_by("-period_end", "-created_at")[:limit]
        )

    def get_for_customer(self, *, customer: Customer, statement_public_id):
        return (
            BillingStatement.objects.for_customer(customer)
            .filter(public_id=statement_public_id)
            .select_related("customer")
            .first()
        )

    @transaction.atomic
    def generate_monthly_statement(
        self,
        *,
        customer: Customer,
        month: date,
        actor,
        source: str,
    ) -> BillingStatement:
        period_start = month.replace(day=1)
        next_month = _next_month(period_start)
        period_end = next_month - timedelta(days=1)
        current_month = timezone.localdate().replace(day=1)
        if period_start >= current_month:
            raise ValidationError("Le mois doit être clôturé avant de générer son récapitulatif.")

        locked_customer = Customer.objects.select_for_update().get(pk=customer.pk)
        existing = BillingStatement.objects.filter(
            customer=locked_customer,
            period_start=period_start,
        ).first()
        if existing is not None:
            raise ValidationError("Un récapitulatif existe déjà pour ce client et ce mois.")

        current_zone = timezone.get_current_timezone()
        starts_at = timezone.make_aware(datetime.combine(period_start, time.min), current_zone)
        ends_at = timezone.make_aware(datetime.combine(next_month, time.min), current_zone)
        orders = list(
            Order.objects.select_for_update()
            .prefetch_related("items")
            .filter(
                customer=locked_customer,
                status=Order.Status.SUBMITTED,
                billing_mode=Order.BillingMode.DEFERRED,
                pricing_status=Order.PricingStatus.PRICED,
                billing_statement__isnull=True,
                created_at__gte=starts_at,
                created_at__lt=ends_at,
            )
            .order_by("created_at", "pk")
        )
        if not orders:
            raise ValidationError(
                "Aucune commande en encours, soumise et tarifée n’est disponible pour ce mois."
            )

        currencies = {order.currency for order in orders}
        if len(currencies) != 1:
            raise ValidationError(
                "Les commandes du récapitulatif doivent utiliser une devise unique."
            )
        currency = currencies.pop()
        for order in orders:
            order_lines = list(order.items.all())
            if not order_lines:
                raise ValidationError("Une commande en encours ne contient aucune ligne comptable.")
            if any(line.line_total < 0 for line in order_lines):
                raise ValidationError(
                    "Une commande en encours contient une ligne comptable négative."
                )
            line_subtotal = sum(
                (line.line_total for line in order_lines),
                Decimal("0.00"),
            ).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
            if order.subtotal_amount != line_subtotal:
                raise ValidationError(
                    "Le sous-total d’une commande ne correspond pas à ses lignes comptables."
                )
            expected_total = (order.subtotal_amount + order.shipping_amount).quantize(
                TWOPLACES,
                rounding=ROUND_HALF_UP,
            )
            if order.tax_rate or order.tax_amount or order.total_amount != expected_total:
                raise ValidationError(
                    "Une commande en encours contient une ventilation TVA incohérente."
                )
            if not Decimal("0") <= order.volume_discount_percent <= Decimal("100"):
                raise ValidationError("Une remise volume de commande est hors limites.")
            if order.volume_discount_amount < 0:
                raise ValidationError("Une remise volume de commande est négative.")
        total_amount = sum((order.total_amount for order in orders), Decimal("0.00")).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )

        try:
            statement = BillingStatement(
                customer=locked_customer,
                label=f"Récapitulatif {date_format(period_start, 'F Y')}",
                period_start=period_start,
                period_end=period_end,
                status=BillingStatement.Status.ISSUED,
                total_amount=total_amount,
                currency=currency,
                issued_at=timezone.now(),
            )
            statement.snapshot = self._build_snapshot(
                statement=statement,
                customer=locked_customer,
                orders=orders,
            )
            canonical_csv = self.render_csv(statement=statement, verify_relations=False)
            statement.snapshot_sha256 = hashlib.sha256(canonical_csv.encode("utf-8")).hexdigest()
            statement.save()
        except IntegrityError as exc:
            raise ValidationError(
                "Un récapitulatif existe déjà pour ce client et ce mois."
            ) from exc

        order_ids = [order.pk for order in orders]
        attached_count = Order.objects.filter(
            pk__in=order_ids,
            customer=locked_customer,
            billing_statement__isnull=True,
        ).update(
            billing_statement=statement,
            updated_at=timezone.now(),
        )
        if attached_count != len(order_ids):
            raise ValidationError("La liste des commandes a changé pendant la clôture. Réessayez.")
        record_event(
            action="billing.statement_generated",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=statement,
            metadata={
                "customer_public_id": str(locked_customer.public_id),
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "order_count": len(order_ids),
                "total_amount": f"{total_amount:.2f}",
                "currency": currency,
                "snapshot_sha256": statement.snapshot_sha256,
                "source": source,
            },
        )
        return statement

    def _build_snapshot(
        self,
        *,
        statement: BillingStatement,
        customer: Customer,
        orders: list[Order],
    ) -> dict[str, object]:
        laize_m = Decimal(int(getattr(settings, "DTF_LAIZE_CM", 55))) / Decimal("100")
        if laize_m <= 0:
            raise ValidationError("La laize DTF doit être strictement positive.")
        totals = {
            "surface": Decimal("0"),
            "linear": Decimal("0"),
            "dtf_gross": Decimal("0"),
            "discount": Decimal("0"),
            "dtf_net": Decimal("0"),
            "other_services": Decimal("0"),
            "subtotal": Decimal("0"),
            "shipping": Decimal("0"),
            "total": Decimal("0"),
        }
        dtf_type = CatalogService.ServiceType.DTF_TRANSFER
        order_snapshots = []
        for order in orders:
            all_lines = list(order.items.all())
            dtf_lines = [line for line in all_lines if line.service_type == dtf_type]
            surface = sum((line.quantity for line in dtf_lines), Decimal("0")).quantize(
                FOURPLACES,
                rounding=ROUND_HALF_UP,
            )
            linear = (surface / laize_m).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
            dtf_net = sum((line.line_total for line in dtf_lines), Decimal("0")).quantize(
                TWOPLACES,
                rounding=ROUND_HALF_UP,
            )
            other_services = sum(
                (line.line_total for line in all_lines if line.service_type != dtf_type),
                Decimal("0"),
            ).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
            discount = order.volume_discount_amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
            dtf_gross = (dtf_net + discount).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
            order_snapshots.append(
                {
                    "order_public_id": str(order.public_id),
                    "order_date": timezone.localtime(order.created_at).date().isoformat(),
                    "surface_dtf_sqm": f"{surface:.4f}",
                    "volume_dtf_linear_m": f"{linear:.4f}",
                    "dtf_gross_ht": f"{dtf_gross:.2f}",
                    "volume_discount_percent": f"{order.volume_discount_percent:.2f}",
                    "volume_discount_ht": f"{discount:.2f}",
                    "dtf_net_ht": f"{dtf_net:.2f}",
                    "other_services_ht": f"{other_services:.2f}",
                    "subtotal_ht": f"{order.subtotal_amount:.2f}",
                    "shipping_ht": f"{order.shipping_amount:.2f}",
                    "total_to_invoice_ht": f"{order.total_amount:.2f}",
                }
            )
            totals["surface"] += surface
            totals["linear"] += linear
            totals["dtf_gross"] += dtf_gross
            totals["discount"] += discount
            totals["dtf_net"] += dtf_net
            totals["other_services"] += other_services
            totals["subtotal"] += order.subtotal_amount
            totals["shipping"] += order.shipping_amount
            totals["total"] += order.total_amount
        return {
            "version": 1,
            "statement": {
                "reference": _statement_reference(statement),
                "period_start": statement.period_start.isoformat(),
                "period_end": statement.period_end.isoformat(),
                "currency": statement.currency,
                "issued_at": statement.issued_at.isoformat() if statement.issued_at else "",
            },
            "customer": {
                "public_id": str(customer.public_id),
                "name": customer.name,
                "siren": customer.siren,
                "vat_number": customer.vat_number,
                "billing_email": customer.billing_email,
                "billing_address_line1": customer.billing_address_line1,
                "billing_address_line2": customer.billing_address_line2,
                "billing_postal_code": customer.billing_postal_code,
                "billing_city": customer.billing_city,
                "billing_country": customer.billing_country,
            },
            "orders": order_snapshots,
            "totals": {
                "surface_dtf_sqm": f"{totals['surface']:.4f}",
                "volume_dtf_linear_m": f"{totals['linear']:.4f}",
                "dtf_gross_ht": f"{totals['dtf_gross']:.2f}",
                "volume_discount_ht": f"{totals['discount']:.2f}",
                "dtf_net_ht": f"{totals['dtf_net']:.2f}",
                "other_services_ht": f"{totals['other_services']:.2f}",
                "subtotal_ht": f"{totals['subtotal']:.2f}",
                "shipping_ht": f"{totals['shipping']:.2f}",
                "total_to_invoice_ht": f"{totals['total']:.2f}",
            },
        }

    def _validate_snapshot_integrity(self, *, statement: BillingStatement) -> None:
        snapshot = statement.snapshot or {}
        if not isinstance(snapshot, dict):
            raise ValidationError("Le snapshot comptable est invalide.")
        if snapshot.get("version") != 1 or not statement.snapshot_sha256:
            raise ValidationError(
                "Ce relevé historique ne possède pas de snapshot comptable exportable."
            )
        if statement.status not in {
            BillingStatement.Status.ISSUED,
            BillingStatement.Status.PAID,
        }:
            raise ValidationError("Seul un relevé émis peut être exporté.")
        order_rows = snapshot.get("orders", [])
        snapshot_statement = snapshot.get("statement", {})
        snapshot_customer = snapshot.get("customer", {})
        snapshot_totals = snapshot.get("totals", {})
        if (
            not isinstance(order_rows, list)
            or any(not isinstance(row, dict) for row in order_rows)
            or not isinstance(snapshot_statement, dict)
            or not isinstance(snapshot_customer, dict)
            or not isinstance(snapshot_totals, dict)
        ):
            raise ValidationError("La structure du snapshot comptable est invalide.")
        snapshot_orders = {row.get("order_public_id") for row in order_rows}
        try:
            snapshot_total = Decimal(snapshot_totals.get("total_to_invoice_ht", "-1"))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationError("Le total du snapshot comptable est invalide.") from exc
        if (
            snapshot_customer.get("public_id") != str(statement.customer.public_id)
            or snapshot_statement.get("period_start") != statement.period_start.isoformat()
            or snapshot_statement.get("period_end") != statement.period_end.isoformat()
            or snapshot_statement.get("currency") != statement.currency
            or snapshot_total != statement.total_amount
        ):
            raise ValidationError("Les métadonnées du relevé ne correspondent plus au snapshot.")
        relation_rows = list(statement.orders.values_list("public_id", "customer_id"))
        if any(customer_id != statement.customer_id for _public_id, customer_id in relation_rows):
            raise ValidationError("Le relevé contient une commande appartenant à un autre client.")
        if {str(public_id) for public_id, _customer_id in relation_rows} != snapshot_orders:
            raise ValidationError("Les commandes rattachées ne correspondent plus au snapshot.")

    def render_csv(
        self,
        *,
        statement: BillingStatement,
        verify_relations: bool = True,
    ) -> str:
        if verify_relations:
            self._validate_snapshot_integrity(statement=statement)
        snapshot = statement.snapshot or {}
        if not isinstance(snapshot, dict):
            raise ValidationError("Snapshot comptable invalide.")
        statement_data = snapshot.get("statement", {})
        customer_data = snapshot.get("customer", {})
        order_rows = snapshot.get("orders", [])
        totals = snapshot.get("totals", {})
        if (
            snapshot.get("version") != 1
            or not isinstance(statement_data, dict)
            or not isinstance(customer_data, dict)
            or not isinstance(order_rows, list)
            or any(not isinstance(row, dict) for row in order_rows)
            or not isinstance(totals, dict)
        ):
            raise ValidationError("Snapshot comptable invalide.")

        fieldnames = [
            "type_ligne",
            "releve_reference",
            "periode_debut",
            "periode_fin",
            "client",
            "siren",
            "tva_intracommunautaire",
            "email_facturation",
            "adresse_facturation_1",
            "adresse_facturation_2",
            "code_postal_facturation",
            "ville_facturation",
            "pays_facturation",
            "commande_reference",
            "date_commande",
            "surface_dtf_m2",
            "volume_dtf_m_lineaires",
            "dtf_brut_ht",
            "remise_volume_pourcent",
            "remise_volume_ht",
            "dtf_net_ht",
            "autres_services_ht",
            "sous_total_ht",
            "livraison_ht",
            "total_a_facturer_ht",
            "devise",
        ]
        output = StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter=";", lineterminator="\r\n")
        writer.writeheader()
        identity = {
            "releve_reference": _safe_csv_text(statement_data.get("reference")),
            "periode_debut": _safe_csv_text(statement_data.get("period_start")),
            "periode_fin": _safe_csv_text(statement_data.get("period_end")),
            "client": _safe_csv_text(customer_data.get("name")),
            "siren": _safe_csv_text(customer_data.get("siren")),
            "tva_intracommunautaire": _safe_csv_text(customer_data.get("vat_number")),
            "email_facturation": _safe_csv_text(customer_data.get("billing_email")),
            "adresse_facturation_1": _safe_csv_text(customer_data.get("billing_address_line1")),
            "adresse_facturation_2": _safe_csv_text(customer_data.get("billing_address_line2")),
            "code_postal_facturation": _safe_csv_text(customer_data.get("billing_postal_code")),
            "ville_facturation": _safe_csv_text(customer_data.get("billing_city")),
            "pays_facturation": _safe_csv_text(customer_data.get("billing_country")),
            "devise": _safe_csv_text(statement_data.get("currency")),
        }
        for row in order_rows:
            writer.writerow(
                {
                    **identity,
                    "type_ligne": "commande",
                    "commande_reference": _safe_csv_text(row.get("order_public_id")),
                    "date_commande": _safe_csv_text(row.get("order_date")),
                    "surface_dtf_m2": _csv_decimal(row.get("surface_dtf_sqm"), places=4),
                    "volume_dtf_m_lineaires": _csv_decimal(
                        row.get("volume_dtf_linear_m"), places=4
                    ),
                    "dtf_brut_ht": _csv_decimal(row.get("dtf_gross_ht")),
                    "remise_volume_pourcent": _csv_decimal(row.get("volume_discount_percent")),
                    "remise_volume_ht": _csv_decimal(row.get("volume_discount_ht")),
                    "dtf_net_ht": _csv_decimal(row.get("dtf_net_ht")),
                    "autres_services_ht": _csv_decimal(row.get("other_services_ht")),
                    "sous_total_ht": _csv_decimal(row.get("subtotal_ht")),
                    "livraison_ht": _csv_decimal(row.get("shipping_ht")),
                    "total_a_facturer_ht": _csv_decimal(row.get("total_to_invoice_ht")),
                }
            )
        writer.writerow(
            {
                **identity,
                "type_ligne": "total",
                "commande_reference": "TOTAL",
                "surface_dtf_m2": _csv_decimal(totals.get("surface_dtf_sqm"), places=4),
                "volume_dtf_m_lineaires": _csv_decimal(totals.get("volume_dtf_linear_m"), places=4),
                "dtf_brut_ht": _csv_decimal(totals.get("dtf_gross_ht")),
                "remise_volume_ht": _csv_decimal(totals.get("volume_discount_ht")),
                "dtf_net_ht": _csv_decimal(totals.get("dtf_net_ht")),
                "autres_services_ht": _csv_decimal(totals.get("other_services_ht")),
                "sous_total_ht": _csv_decimal(totals.get("subtotal_ht")),
                "livraison_ht": _csv_decimal(totals.get("shipping_ht")),
                "total_a_facturer_ht": _csv_decimal(totals.get("total_to_invoice_ht")),
            }
        )
        content = "\ufeff" + output.getvalue()
        if verify_relations:
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if digest != statement.snapshot_sha256:
                raise ValidationError("L’empreinte du snapshot comptable est invalide.")
        return content

    def record_export(self, *, statement: BillingStatement, actor, source: str) -> None:
        snapshot = statement.snapshot or {}
        snapshot_customer = snapshot.get("customer", {})
        snapshot_orders = snapshot.get("orders", [])
        record_event(
            action="billing.statement_exported",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=statement,
            metadata={
                "customer_public_id": snapshot_customer.get("public_id", ""),
                "period_start": statement.period_start.isoformat(),
                "period_end": statement.period_end.isoformat(),
                "order_count": len(snapshot_orders),
                "total_amount": f"{statement.total_amount:.2f}",
                "currency": statement.currency,
                "snapshot_sha256": statement.snapshot_sha256,
                "source": source,
            },
        )

    def record_export_failure(
        self,
        *,
        statement: BillingStatement,
        actor,
        source: str,
        reason_code: str,
    ) -> None:
        record_event(
            action="billing.statement_export_failed",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=statement,
            metadata={
                "customer_public_id": str(statement.customer.public_id),
                "period_start": statement.period_start.isoformat(),
                "period_end": statement.period_end.isoformat(),
                "reason_code": reason_code,
                "source": source,
            },
        )

    @staticmethod
    def reference(statement: BillingStatement) -> str:
        return _statement_reference(statement)
