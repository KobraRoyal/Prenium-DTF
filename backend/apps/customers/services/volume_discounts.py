from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.customers.models import (
    Customer,
    CustomerVolumeDiscountTier,
    DefaultCustomerVolumeDiscountTier,
)


class DefaultCustomerVolumeDiscountTierService:
    """Grille Atelier globale appliquée aux nouveaux comptes en encours."""

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
        if customer.default_billing_mode != Customer.DefaultBillingMode.DEFERRED:
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
    """Configuration auditée des paliers et recalcul du mois civil courant."""

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
        """Synthèse Atelier du volume DTF non relevé du mois civil courant."""
        from apps.catalog.models import CatalogService
        from apps.orders.models import Order, OrderLine

        month_start = timezone.localdate().replace(day=1)
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)
        current_tz = timezone.get_current_timezone()
        starts_at = timezone.make_aware(datetime.combine(month_start, time.min), current_tz)
        ends_at = timezone.make_aware(datetime.combine(next_month, time.min), current_tz)
        eligible_orders = Order.objects.filter(
            customer=customer,
            billing_mode=Order.BillingMode.DEFERRED,
            pricing_status=Order.PricingStatus.PRICED,
            billing_statement__isnull=True,
            status=Order.Status.SUBMITTED,
            created_at__gte=starts_at,
            created_at__lt=ends_at,
        )
        total_sqm = OrderLine.objects.filter(
            order__in=eligible_orders,
            service_type=CatalogService.ServiceType.DTF_TRANSFER,
        ).aggregate(total=Sum("quantity"))["total"] or Decimal("0.00")
        laize_m = Decimal(int(getattr(settings, "DTF_LAIZE_CM", 55))) / Decimal("100")
        monthly_volume = (
            (total_sqm / laize_m).quantize(Decimal("0.0001")) if laize_m > 0 else Decimal("0.0000")
        )
        discount_amount = (
            eligible_orders.aggregate(total=Sum("volume_discount_amount"))["total"]
            or Decimal("0.00")
        ).quantize(Decimal("0.01"))
        active_tiers = CustomerVolumeDiscountTier.objects.for_customer(customer).active()
        current_tier = (
            active_tiers.filter(minimum_monthly_linear_m__lte=monthly_volume)
            .order_by("-minimum_monthly_linear_m")
            .first()
        )
        next_tier = (
            active_tiers.filter(minimum_monthly_linear_m__gt=monthly_volume)
            .order_by("minimum_monthly_linear_m")
            .first()
        )
        remaining_to_next_tier = (
            (next_tier.minimum_monthly_linear_m - monthly_volume).quantize(Decimal("0.0001"))
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
        }

    def _validate_deferred_customer(self, *, customer: Customer) -> None:
        if customer.default_billing_mode != Customer.DefaultBillingMode.DEFERRED:
            raise ValidationError(
                "Les paliers de remise mensuelle sont réservés aux clients avec encours."
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
        self._validate_deferred_customer(customer=customer)
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
        self._validate_deferred_customer(customer=customer)
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
