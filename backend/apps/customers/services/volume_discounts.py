from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Exists, OuterRef, Sum
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.customers.models import (
    Customer,
    CustomerVolumeDiscountTier,
    DefaultCustomerVolumeDiscountTier,
)

FOURPLACES = Decimal("0.0001")
TWOPLACES = Decimal("0.01")
ZERO_AMOUNT = Decimal("0.00")
ZERO_VOLUME = Decimal("0.0000")

DEFERRED_APPLICATION_SCOPE = "sur l’ensemble du volume DTF éligible du mois"
IMMEDIATE_APPLICATION_SCOPE = "sur cette commande et les suivantes, sans effet rétroactif"


@dataclass(frozen=True)
class ResolvedVolumeTier:
    minimum_monthly_linear_m: Decimal
    discount_percent: Decimal
    pk: int | None = None


def month_bounds(month):
    month_start = month.replace(day=1)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)
    current_tz = timezone.get_current_timezone()
    starts_at = timezone.make_aware(datetime.combine(month_start, time.min), current_tz)
    ends_at = timezone.make_aware(datetime.combine(next_month, time.min), current_tz)
    return month_start, next_month, starts_at, ends_at


def linear_meters_from_sqm(total_sqm: Decimal) -> Decimal:
    laize_m = Decimal(int(getattr(settings, "DTF_LAIZE_CM", 55))) / Decimal("100")
    if laize_m <= 0:
        raise ValidationError("DTF_LAIZE_CM doit être strictement positif.")
    return (Decimal(str(total_sqm)) / laize_m).quantize(FOURPLACES, rounding=ROUND_HALF_UP)


def customer_has_personalized_ladder(customer: Customer) -> bool:
    return CustomerVolumeDiscountTier.objects.for_customer(customer).exists()


def resolve_active_ladder(customer: Customer) -> list[ResolvedVolumeTier]:
    """Paliers actifs : grille client prioritaire, sinon grille globale par défaut."""
    if customer_has_personalized_ladder(customer):
        rows = (
            CustomerVolumeDiscountTier.objects.for_customer(customer)
            .active()
            .order_by("minimum_monthly_linear_m", "created_at")
        )
        return [
            ResolvedVolumeTier(
                minimum_monthly_linear_m=row.minimum_monthly_linear_m,
                discount_percent=row.discount_percent,
                pk=row.pk,
            )
            for row in rows
        ]
    rows = DefaultCustomerVolumeDiscountTier.objects.active().order_by(
        "minimum_monthly_linear_m",
        "created_at",
    )
    return [
        ResolvedVolumeTier(
            minimum_monthly_linear_m=row.minimum_monthly_linear_m,
            discount_percent=row.discount_percent,
            pk=row.pk,
        )
        for row in rows
    ]


def pick_tier_for_volume(
    *,
    ladder: list[ResolvedVolumeTier],
    monthly_volume: Decimal,
) -> ResolvedVolumeTier | None:
    eligible = [tier for tier in ladder if tier.minimum_monthly_linear_m <= monthly_volume]
    if not eligible:
        return None
    return max(eligible, key=lambda tier: (tier.minimum_monthly_linear_m, tier.discount_percent))


def next_tier_for_volume(
    *,
    ladder: list[ResolvedVolumeTier],
    monthly_volume: Decimal,
) -> ResolvedVolumeTier | None:
    upcoming = [tier for tier in ladder if tier.minimum_monthly_linear_m > monthly_volume]
    if not upcoming:
        return None
    return min(upcoming, key=lambda tier: (tier.minimum_monthly_linear_m, tier.pk or 0))


def paid_immediate_orders_qs(*, customer: Customer, starts_at, ends_at, exclude_order_id=None):
    from apps.billing.models import Payment
    from apps.orders.models import Order

    captured = Payment.objects.filter(
        order_id=OuterRef("pk"),
        status=Payment.Status.CAPTURED,
    )
    queryset = (
        Order.objects.filter(
            customer=customer,
            billing_mode=Order.BillingMode.IMMEDIATE,
            pricing_status=Order.PricingStatus.PRICED,
            status=Order.Status.SUBMITTED,
            created_at__gte=starts_at,
            created_at__lt=ends_at,
        )
        .annotate(_has_captured_payment=Exists(captured))
        .filter(_has_captured_payment=True)
    )
    if exclude_order_id is not None:
        queryset = queryset.exclude(pk=exclude_order_id)
    return queryset


def paid_monthly_dtf_volume_linear_m(
    *,
    customer: Customer,
    month,
    exclude_order_id=None,
) -> Decimal:
    from apps.catalog.models import CatalogService
    from apps.orders.models import OrderLine

    _month_start, _next_month, starts_at, ends_at = month_bounds(month)
    eligible_orders = paid_immediate_orders_qs(
        customer=customer,
        starts_at=starts_at,
        ends_at=ends_at,
        exclude_order_id=exclude_order_id,
    )
    total_sqm = OrderLine.objects.filter(
        order__in=eligible_orders,
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
    ).aggregate(total=Sum("quantity"))["total"] or Decimal("0.00")
    return linear_meters_from_sqm(total_sqm)


def quote_volume_and_tier(
    *,
    customer: Customer,
    additional_linear_m: Decimal,
    month=None,
    exclude_order_id=None,
) -> tuple[Decimal, Decimal, ResolvedVolumeTier | None]:
    """Volume payé + commande en cours, et palier prospectif associé."""
    resolved_month = month or timezone.localdate()
    paid_volume = paid_monthly_dtf_volume_linear_m(
        customer=customer,
        month=resolved_month,
        exclude_order_id=exclude_order_id,
    )
    quote_volume = (paid_volume + Decimal(str(additional_linear_m))).quantize(
        FOURPLACES,
        rounding=ROUND_HALF_UP,
    )
    tier = pick_tier_for_volume(
        ladder=resolve_active_ladder(customer),
        monthly_volume=quote_volume,
    )
    return paid_volume, quote_volume, tier


def application_scope_for_customer(customer: Customer) -> str:
    if customer.default_billing_mode == Customer.DefaultBillingMode.IMMEDIATE:
        return IMMEDIATE_APPLICATION_SCOPE
    return DEFERRED_APPLICATION_SCOPE


def is_cash_volume_customer(customer: Customer) -> bool:
    return customer.default_billing_mode == Customer.DefaultBillingMode.IMMEDIATE


class DefaultCustomerVolumeDiscountTierService:
    """Grille Atelier globale copiée sur les nouveaux comptes encours ou comptant."""

    _POSTGRES_LOCK_ID = 8_103_701_337

    def _lock_ladder(self) -> None:
        """Sérialise validation + écriture de la grille globale."""
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [self._POSTGRES_LOCK_ID])
            return
        # Verrou de meilleure intention pour les moteurs sans advisory lock (tests SQLite).
        list(
            DefaultCustomerVolumeDiscountTier.objects.select_for_update().values_list(
                "pk",
                flat=True,
            )
        )

    def list_tiers(self):
        return DefaultCustomerVolumeDiscountTier.objects.order_by(
            "minimum_monthly_linear_m",
            "created_at",
        )

    def get_tier(self, *, tier_public_id):
        return DefaultCustomerVolumeDiscountTier.objects.filter(public_id=tier_public_id).first()

    def _validate_ladder(
        self,
        *,
        minimum_monthly_linear_m: Decimal,
        discount_percent: Decimal,
        is_active: bool,
        exclude_pk=None,
    ) -> None:
        duplicate_threshold = (
            DefaultCustomerVolumeDiscountTier.objects.exclude(pk=exclude_pk)
            .filter(minimum_monthly_linear_m=minimum_monthly_linear_m)
            .exists()
        )
        if duplicate_threshold:
            raise ValidationError("Un palier par défaut existe déjà pour ce seuil.")
        if not is_active:
            return
        tiers = list(
            DefaultCustomerVolumeDiscountTier.objects.active()
            .exclude(pk=exclude_pk)
            .values_list("minimum_monthly_linear_m", "discount_percent")
        )
        tiers.append((minimum_monthly_linear_m, discount_percent))
        tiers.sort(key=lambda row: row[0])
        for previous, current in zip(tiers, tiers[1:], strict=False):
            if current[1] <= previous[1]:
                raise ValidationError(
                    "La remise par défaut doit augmenter strictement avec le volume."
                )

    @transaction.atomic
    def create_tier(self, *, cleaned_data: dict, actor, source: str):
        self._lock_ladder()
        threshold = cleaned_data["minimum_monthly_linear_m"]
        discount = cleaned_data["discount_percent"]
        is_active = bool(cleaned_data.get("is_active", True))
        self._validate_ladder(
            minimum_monthly_linear_m=threshold,
            discount_percent=discount,
            is_active=is_active,
        )
        tier = DefaultCustomerVolumeDiscountTier.objects.create(
            minimum_monthly_linear_m=threshold,
            discount_percent=discount,
            is_active=is_active,
        )
        record_event(
            action="customer.default_volume_discount_tier_created",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=tier,
            metadata={
                "tier_public_id": str(tier.public_id),
                "minimum_monthly_linear_m": f"{threshold:.4f}",
                "discount_percent": f"{discount:.2f}",
                "is_active": is_active,
                "source": source,
            },
        )
        return tier

    @transaction.atomic
    def update_tier(
        self,
        *,
        tier_public_id,
        cleaned_data: dict,
        actor,
        source: str,
    ):
        self._lock_ladder()
        tier = (
            DefaultCustomerVolumeDiscountTier.objects.select_for_update()
            .filter(public_id=tier_public_id)
            .first()
        )
        if tier is None:
            raise DefaultCustomerVolumeDiscountTier.DoesNotExist
        threshold = cleaned_data["minimum_monthly_linear_m"]
        discount = cleaned_data["discount_percent"]
        is_active = bool(cleaned_data.get("is_active"))
        self._validate_ladder(
            minimum_monthly_linear_m=threshold,
            discount_percent=discount,
            is_active=is_active,
            exclude_pk=tier.pk,
        )
        before = {
            "minimum_monthly_linear_m": tier.minimum_monthly_linear_m,
            "discount_percent": tier.discount_percent,
            "is_active": tier.is_active,
        }
        tier.minimum_monthly_linear_m = threshold
        tier.discount_percent = discount
        tier.is_active = is_active
        tier.save(
            update_fields=[
                "minimum_monthly_linear_m",
                "discount_percent",
                "is_active",
                "updated_at",
            ]
        )
        record_event(
            action="customer.default_volume_discount_tier_updated",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=tier,
            metadata={
                "tier_public_id": str(tier.public_id),
                "source": source,
                "changes": {
                    field: {"before": str(before[field]), "after": str(getattr(tier, field))}
                    for field in before
                    if before[field] != getattr(tier, field)
                },
            },
        )
        return tier

    @transaction.atomic
    def apply_to_customer(self, *, customer: Customer, actor, source: str):
        customer = Customer.objects.select_for_update().get(pk=customer.pk)
        if customer.default_billing_mode not in {
            Customer.DefaultBillingMode.DEFERRED,
            Customer.DefaultBillingMode.IMMEDIATE,
        }:
            return []
        if CustomerVolumeDiscountTier.objects.for_customer(customer).exists():
            return []
        self._lock_ladder()
        defaults = list(
            DefaultCustomerVolumeDiscountTier.objects.active().order_by(
                "minimum_monthly_linear_m",
                "created_at",
            )
        )
        tiers = CustomerVolumeDiscountTier.objects.bulk_create(
            [
                CustomerVolumeDiscountTier(
                    customer=customer,
                    minimum_monthly_linear_m=default.minimum_monthly_linear_m,
                    discount_percent=default.discount_percent,
                    is_active=True,
                )
                for default in defaults
            ]
        )
        if tiers:
            record_event(
                action="customer.default_volume_discount_tiers_applied",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=customer,
                metadata={
                    "customer_public_id": str(customer.public_id),
                    "tier_count": len(tiers),
                    "thresholds": [f"{tier.minimum_monthly_linear_m:.4f}" for tier in tiers],
                    "source": source,
                },
            )
        return tiers


class CustomerVolumeDiscountTierService:
    """Configuration auditée des paliers ; retarif rétroactif réservé à l’encours."""

    def list_tiers(self, *, customer: Customer):
        return CustomerVolumeDiscountTier.objects.for_customer(customer).order_by(
            "minimum_monthly_linear_m",
            "created_at",
        )

    def get_tier(self, *, customer: Customer, tier_public_id):
        return (
            CustomerVolumeDiscountTier.objects.for_customer(customer)
            .filter(public_id=tier_public_id)
            .first()
        )

    def get_current_month_summary(self, *, customer: Customer) -> dict[str, object]:
        """Synthèse du volume DTF du mois civil courant (encours ou comptant payé)."""
        from apps.catalog.models import CatalogService
        from apps.orders.models import Order, OrderLine

        month_start, _next_month, starts_at, ends_at = month_bounds(timezone.localdate())
        is_immediate = is_cash_volume_customer(customer)
        if is_immediate:
            eligible_orders = paid_immediate_orders_qs(
                customer=customer,
                starts_at=starts_at,
                ends_at=ends_at,
            )
            policy = "prospective"
        else:
            eligible_orders = Order.objects.filter(
                customer=customer,
                billing_mode=Order.BillingMode.DEFERRED,
                pricing_status=Order.PricingStatus.PRICED,
                billing_statement__isnull=True,
                status=Order.Status.SUBMITTED,
                created_at__gte=starts_at,
                created_at__lt=ends_at,
            )
            policy = "retroactive"
        total_sqm = OrderLine.objects.filter(
            order__in=eligible_orders,
            service_type=CatalogService.ServiceType.DTF_TRANSFER,
        ).aggregate(total=Sum("quantity"))["total"] or Decimal("0.00")
        monthly_volume = linear_meters_from_sqm(total_sqm)
        discount_amount = (
            eligible_orders.aggregate(total=Sum("volume_discount_amount"))["total"]
            or Decimal("0.00")
        ).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        ladder = resolve_active_ladder(customer)
        current_tier = pick_tier_for_volume(ladder=ladder, monthly_volume=monthly_volume)
        next_tier = next_tier_for_volume(ladder=ladder, monthly_volume=monthly_volume)
        remaining_to_next_tier = (
            (next_tier.minimum_monthly_linear_m - monthly_volume).quantize(FOURPLACES)
            if next_tier is not None
            else None
        )
        return {
            "month": month_start,
            "eligible_order_count": eligible_orders.count(),
            "monthly_volume_linear_m": monthly_volume,
            "discount_amount": discount_amount,
            "current_tier": current_tier,
            "next_tier": next_tier,
            "remaining_to_next_tier_linear_m": remaining_to_next_tier,
            "policy": policy,
            "uses_default_ladder": not customer_has_personalized_ladder(customer),
            "application_scope": application_scope_for_customer(customer),
        }

    def notify_immediate_tier_after_capture(self, *, order, actor, source: str) -> None:
        """E-mail palier après paiement capturé, jamais au devis."""
        customer = order.customer
        if not is_cash_volume_customer(customer):
            return
        from apps.orders.models import Order

        if getattr(order, "billing_mode", None) != Order.BillingMode.IMMEDIATE:
            return
        threshold = order.volume_discount_threshold_linear_m
        percent = order.volume_discount_percent or ZERO_AMOUNT
        if threshold is None or percent <= 0:
            return
        month = order.volume_discount_month or timezone.localdate().replace(day=1)
        paid_volume = paid_monthly_dtf_volume_linear_m(customer=customer, month=month)
        summary = self.get_current_month_summary(customer=customer)
        from apps.notifications.services.transactional import (
            schedule_volume_discount_tier_reached_email,
        )

        schedule_volume_discount_tier_reached_email(
            customer=customer,
            month=month,
            threshold_linear_m=threshold,
            monthly_volume_linear_m=paid_volume,
            discount_percent=percent,
            discount_amount=summary["discount_amount"],
            actor=actor,
            source=source,
        )

    def _validate_volume_discount_customer(self, *, customer: Customer) -> None:
        if customer.default_billing_mode not in {
            Customer.DefaultBillingMode.DEFERRED,
            Customer.DefaultBillingMode.IMMEDIATE,
        }:
            raise ValidationError(
                "Les paliers de remise mensuelle sont réservés aux comptes encours ou comptant."
            )

    def _validate_ladder(
        self,
        *,
        customer: Customer,
        minimum_monthly_linear_m: Decimal,
        discount_percent: Decimal,
        is_active: bool,
        exclude_pk=None,
    ) -> None:
        duplicate_threshold = (
            CustomerVolumeDiscountTier.objects.for_customer(customer)
            .exclude(pk=exclude_pk)
            .filter(minimum_monthly_linear_m=minimum_monthly_linear_m)
            .exists()
        )
        if duplicate_threshold:
            raise ValidationError("Un palier existe déjà pour ce seuil mensuel.")
        if not is_active:
            return
        tiers = list(
            CustomerVolumeDiscountTier.objects.for_customer(customer)
            .active()
            .exclude(pk=exclude_pk)
            .values_list("minimum_monthly_linear_m", "discount_percent")
        )
        tiers.append((minimum_monthly_linear_m, discount_percent))
        tiers.sort(key=lambda row: row[0])
        for previous, current in zip(tiers, tiers[1:], strict=False):
            if current[1] <= previous[1]:
                raise ValidationError(
                    "La remise doit augmenter strictement lorsque le seuil de volume augmente."
                )

    def _reprice_current_month(self, *, customer, actor, source):
        if is_cash_volume_customer(customer):
            summary = self.get_current_month_summary(customer=customer)
            return {
                "repriced_count": 0,
                "monthly_volume_linear_m": summary["monthly_volume_linear_m"],
                "discount_percent": (
                    summary["current_tier"].discount_percent
                    if summary["current_tier"] is not None
                    else ZERO_AMOUNT
                ),
                "threshold_linear_m": (
                    summary["current_tier"].minimum_monthly_linear_m
                    if summary["current_tier"] is not None
                    else None
                ),
                "month": summary["month"],
                "policy": "prospective",
            }
        from apps.orders.services.pricing import OrderPricingService

        return OrderPricingService().reprice_deferred_month(
            customer=customer,
            month=timezone.localdate(),
            actor=actor,
            source=source,
        )

    @transaction.atomic
    def create_tier(
        self,
        *,
        customer: Customer,
        cleaned_data: dict,
        actor,
        source: str,
    ) -> tuple[CustomerVolumeDiscountTier, dict[str, object]]:
        customer = Customer.objects.select_for_update().get(pk=customer.pk)
        self._validate_volume_discount_customer(customer=customer)
        threshold = cleaned_data["minimum_monthly_linear_m"]
        discount = cleaned_data["discount_percent"]
        is_active = bool(cleaned_data.get("is_active", True))
        self._validate_ladder(
            customer=customer,
            minimum_monthly_linear_m=threshold,
            discount_percent=discount,
            is_active=is_active,
        )
        tier = CustomerVolumeDiscountTier.objects.create(
            customer=customer,
            minimum_monthly_linear_m=threshold,
            discount_percent=discount,
            is_active=is_active,
        )
        actor_or_none = actor if getattr(actor, "is_authenticated", False) else None
        record_event(
            action="customer.volume_discount_tier_created",
            actor=actor_or_none,
            target=customer,
            metadata={
                "customer_public_id": str(customer.public_id),
                "tier_public_id": str(tier.public_id),
                "minimum_monthly_linear_m": f"{threshold:.4f}",
                "discount_percent": f"{discount:.2f}",
                "is_active": is_active,
                "source": source,
            },
        )
        summary = self._reprice_current_month(
            customer=customer,
            actor=actor,
            source=f"{source}.tier_created",
        )
        return tier, summary

    @transaction.atomic
    def update_tier(
        self,
        *,
        customer: Customer,
        tier_public_id,
        cleaned_data: dict,
        actor,
        source: str,
    ) -> tuple[CustomerVolumeDiscountTier, dict[str, object]]:
        customer = Customer.objects.select_for_update().get(pk=customer.pk)
        self._validate_volume_discount_customer(customer=customer)
        tier = (
            CustomerVolumeDiscountTier.objects.select_for_update()
            .for_customer(customer)
            .filter(public_id=tier_public_id)
            .first()
        )
        if tier is None:
            raise CustomerVolumeDiscountTier.DoesNotExist
        threshold = cleaned_data["minimum_monthly_linear_m"]
        discount = cleaned_data["discount_percent"]
        is_active = bool(cleaned_data.get("is_active"))
        self._validate_ladder(
            customer=customer,
            minimum_monthly_linear_m=threshold,
            discount_percent=discount,
            is_active=is_active,
            exclude_pk=tier.pk,
        )
        before = {
            "minimum_monthly_linear_m": tier.minimum_monthly_linear_m,
            "discount_percent": tier.discount_percent,
            "is_active": tier.is_active,
        }
        tier.minimum_monthly_linear_m = threshold
        tier.discount_percent = discount
        tier.is_active = is_active
        tier.save(
            update_fields=[
                "minimum_monthly_linear_m",
                "discount_percent",
                "is_active",
                "updated_at",
            ]
        )
        record_event(
            action="customer.volume_discount_tier_updated",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=customer,
            metadata={
                "customer_public_id": str(customer.public_id),
                "tier_public_id": str(tier.public_id),
                "source": source,
                "changes": {
                    field: {"before": str(before[field]), "after": str(getattr(tier, field))}
                    for field in before
                    if before[field] != getattr(tier, field)
                },
            },
        )
        summary = self._reprice_current_month(
            customer=customer,
            actor=actor,
            source=f"{source}.tier_updated",
        )
        return tier, summary
