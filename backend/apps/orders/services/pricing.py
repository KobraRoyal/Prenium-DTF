from __future__ import annotations

from datetime import datetime, time
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.catalog.models import CatalogService
from apps.catalog.services.default_catalog import DefaultCatalogService
from apps.customers.models import (
    Customer,
    CustomerBillingProfile,
    CustomerVolumeDiscountTier,
)
from apps.customers.services.volume_discounts import (
    is_cash_volume_customer,
    linear_meters_from_sqm,
    quote_volume_and_tier,
)
from apps.orders.models import ZERO_AMOUNT, Order, OrderLine
from apps.shipping.services.methods import ShippingMethodService

TWOPLACES = Decimal("0.01")
FOURPLACES = Decimal("0.0001")


def billable_sqm_from_physical_size(
    *,
    width_m: Decimal,
    height_m: Decimal,
    laize_m: Decimal,
    mode: str,
) -> Decimal:
    """Surface facturable (m²) à partir des côtés physiques du fichier (inspection / DPI).

    - pixel_rectangle : aire du rectangle (comportement historique).
    - laize_fit : impression sur laize fixe — si le plus petit côté dépasse la laize,
      on facture au minimum une bande pleine laize × grand côté (conso. film réaliste).
    """
    if mode == "pixel_rectangle":
        return (width_m * height_m).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
    if mode == "laize_fit":
        short_side = min(width_m, height_m)
        long_side = max(width_m, height_m)
        if short_side <= laize_m:
            return (short_side * long_side).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
        return (long_side * laize_m).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
    raise ValidationError(
        f"DTF_METERAGE_AREA_MODE invalide ({mode!r}). Utilisez pixel_rectangle ou laize_fit."
    )


class OrderPricingService:
    """Tarification B2B différée.

    Règle unique : **tarif client si présent**, sinon **tarif du service catalogue** actif
    (DTF au m², préparation fichier au forfait). Les enregistrements `OrderLine` référencent
    toujours les services catalogue pour l’intitulé / traçabilité ; les montants utilisent les
    montants résolus ci-dessous.

    Ventilation persistée :
    - ``subtotal_amount`` = HT produit (DTF + préparation)
    - ``shipping_amount`` = HT port (0 si retrait / sans option)
    - ``tax_amount`` = TVA 20 % si ``billing_mode=immediate`` (sur HT + port), sinon 0
      (encours : facturation TVA externalisée mensuelle / bimensuelle)
    - ``total_amount`` = subtotal + shipping + tax
      (comptant = TTC Stripe ; encours = HT + port)
    """

    def __init__(self, *, shipping_methods: ShippingMethodService | None = None):
        self.shipping_methods = shipping_methods or ShippingMethodService()
        self.catalog_bootstrap = DefaultCatalogService()

    def _pick_preferred_catalog_service(
        self,
        *,
        queryset,
        preferred_codes: list[str],
        missing_message: str,
        prefer_seed_fallback: bool = False,
    ) -> CatalogService:
        """Choisit un service actif : code préféré (settings) puis ordre catalogue."""
        active = queryset.order_by("display_order", "name", "code")
        codes = [str(c).strip() for c in preferred_codes if str(c).strip()]
        for code in codes:
            service = active.filter(code=code).first()
            if service is not None:
                return service
        if prefer_seed_fallback:
            seed = active.filter(code__startswith="seed-").first()
            if seed is not None:
                return seed
        service = active.first()
        if service is None:
            raise ValidationError(missing_message)
        return service

    def get_default_dtf_service(self) -> CatalogService:
        try:
            return self._pick_preferred_catalog_service(
                queryset=CatalogService.objects.active().filter(
                    service_type=CatalogService.ServiceType.DTF_TRANSFER,
                    unit=CatalogService.Unit.LINEAR_METER,
                ),
                preferred_codes=list(getattr(settings, "CATALOG_PREFERRED_DTF_CODES", []) or []),
                missing_message="Aucun service DTF au mètre actif dans le catalogue.",
                prefer_seed_fallback=False,
            )
        except ValidationError:
            self.catalog_bootstrap.ensure_default_services()
            return self._pick_preferred_catalog_service(
                queryset=CatalogService.objects.active().filter(
                    service_type=CatalogService.ServiceType.DTF_TRANSFER,
                    unit=CatalogService.Unit.LINEAR_METER,
                ),
                preferred_codes=list(getattr(settings, "CATALOG_PREFERRED_DTF_CODES", []) or []),
                missing_message="Aucun service DTF au mètre actif dans le catalogue.",
                prefer_seed_fallback=False,
            )

    def get_default_file_preparation_service(self) -> CatalogService:
        try:
            return self._pick_preferred_catalog_service(
                queryset=CatalogService.objects.active().filter(
                    service_type=CatalogService.ServiceType.FILE_PREPARATION,
                    unit=CatalogService.Unit.FIXED,
                ),
                preferred_codes=list(
                    getattr(settings, "CATALOG_PREFERRED_FILE_PREP_CODES", []) or []
                ),
                missing_message=(
                    "Aucun service « Préparation fichier » (forfait) actif dans le catalogue."
                ),
                prefer_seed_fallback=True,
            )
        except ValidationError:
            self.catalog_bootstrap.ensure_default_services()
            return self._pick_preferred_catalog_service(
                queryset=CatalogService.objects.active().filter(
                    service_type=CatalogService.ServiceType.FILE_PREPARATION,
                    unit=CatalogService.Unit.FIXED,
                ),
                preferred_codes=list(
                    getattr(settings, "CATALOG_PREFERRED_FILE_PREP_CODES", []) or []
                ),
                missing_message=(
                    "Aucun service « Préparation fichier » (forfait) actif dans le catalogue."
                ),
                prefer_seed_fallback=True,
            )

    def resolve_unit_price_per_sqm(self, *, customer) -> Decimal:
        """Prix au m² DTF.

        `CustomerBillingProfile.price_per_sqm_eur` si renseigné, sinon
        `CatalogService` DTF actif (`base_price`).
        """
        profile = CustomerBillingProfile.objects.filter(customer=customer).first()
        if profile is not None and profile.price_per_sqm_eur is not None:
            return profile.price_per_sqm_eur.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        service = self.get_default_dtf_service()
        return service.base_price.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    def resolve_file_preparation_fee_per_file(self, *, customer) -> Decimal:
        """Forfait fichier.

        `Customer.negotiated_file_preparation_fee_eur` si renseigné, sinon
        `CatalogService` préparation fichier actif (`base_price`).
        """
        fee = getattr(customer, "negotiated_file_preparation_fee_eur", None)
        if fee is not None:
            return fee.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        service = self.get_default_file_preparation_service()
        return service.base_price.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    def resolve_vat_rate(self, *, billing_mode: str) -> Decimal:
        if billing_mode == Order.BillingMode.IMMEDIATE:
            rate = getattr(settings, "ORDER_VAT_RATE_IMMEDIATE", Decimal("0.20"))
            return Decimal(str(rate)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        return ZERO_AMOUNT

    def compose_order_totals(
        self,
        *,
        subtotal_ht: Decimal,
        shipping_ht: Decimal,
        billing_mode: str,
    ) -> dict[str, Decimal]:
        subtotal = subtotal_ht.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        shipping = shipping_ht.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        tax_rate = self.resolve_vat_rate(billing_mode=billing_mode)
        taxable = (subtotal + shipping).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        tax_amount = (taxable * tax_rate).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        total = (taxable + tax_amount).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        return {
            "subtotal_amount": subtotal,
            "shipping_amount": shipping,
            "tax_rate": tax_rate,
            "tax_amount": tax_amount,
            "total_amount": total,
        }

    def estimate_gang_sheet_quote(
        self,
        *,
        customer,
        surface_sqm: Decimal | str | float,
        quantity: int = 1,
        file_count: int = 1,
        shipping_method_code: str | None = None,
        billing_mode: str | None = None,
    ) -> dict[str, object]:
        """Devis avant transmission : produit HT + port + TVA (si comptant)."""
        unit_price = self.resolve_unit_price_per_sqm(customer=customer)
        prep_fee = self.resolve_file_preparation_fee_per_file(customer=customer)
        qty = max(int(quantity or 1), 1)
        files = max(int(file_count or 1), 1)
        surface = Decimal(str(surface_sqm)).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
        if surface <= 0:
            raise ValidationError("La surface de la Gang Sheet est invalide.")
        billable = (surface * Decimal(qty)).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
        dtf_amount = (billable * unit_price).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        prep_amount = (prep_fee * Decimal(files)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        subtotal = (dtf_amount + prep_amount).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        method = self.shipping_methods.resolve_method_for_customer(
            customer=customer,
            shipping_method_code=shipping_method_code,
        )
        shipping_snap = self.shipping_methods.snapshot_dict(method)
        resolved_billing = (
            str(billing_mode).strip().lower()
            if billing_mode
            else str(getattr(customer, "default_billing_mode", Order.BillingMode.DEFERRED))
            .strip()
            .lower()
        )
        dtf_gross_amount = dtf_amount
        volume_discount_percent = ZERO_AMOUNT
        volume_discount_amount = ZERO_AMOUNT
        volume_discount_threshold = None
        paid_monthly_volume = ZERO_AMOUNT
        monthly_volume = ZERO_AMOUNT
        if resolved_billing == Order.BillingMode.IMMEDIATE and is_cash_volume_customer(customer):
            additional_linear = linear_meters_from_sqm(billable)
            paid_monthly_volume, monthly_volume, tier = quote_volume_and_tier(
                customer=customer,
                additional_linear_m=additional_linear,
            )
            if tier is not None:
                volume_discount_percent = tier.discount_percent.quantize(
                    TWOPLACES,
                    rounding=ROUND_HALF_UP,
                )
                volume_discount_threshold = tier.minimum_monthly_linear_m
                factor = (Decimal("100.00") - volume_discount_percent) / Decimal("100.00")
                dtf_amount = (dtf_gross_amount * factor).quantize(
                    TWOPLACES,
                    rounding=ROUND_HALF_UP,
                )
                unit_price = (unit_price * factor).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
                volume_discount_amount = (dtf_gross_amount - dtf_amount).quantize(
                    TWOPLACES,
                    rounding=ROUND_HALF_UP,
                )
                subtotal = (dtf_amount + prep_amount).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        totals = self.compose_order_totals(
            subtotal_ht=subtotal,
            shipping_ht=Decimal(str(shipping_snap["shipping_amount"])),
            billing_mode=resolved_billing,
        )
        return {
            "surface_sqm": surface,
            "quantity": qty,
            "file_count": files,
            "billable_sqm": billable,
            "unit_price_eur": unit_price,
            "dtf_amount_eur": dtf_amount,
            "dtf_gross_amount_eur": dtf_gross_amount,
            "prep_fee_eur": prep_fee,
            "prep_amount_eur": prep_amount,
            "subtotal_eur": totals["subtotal_amount"],
            "shipping_method_code": shipping_snap["shipping_method_code"],
            "shipping_method_name": shipping_snap["shipping_method_name"],
            "shipping_amount_eur": totals["shipping_amount"],
            "shipping_is_pickup": shipping_snap["shipping_is_pickup"],
            "tax_rate": totals["tax_rate"],
            "tax_amount_eur": totals["tax_amount"],
            "total_eur": totals["total_amount"],
            "billing_mode": resolved_billing,
            "currency": "EUR",
            "volume_discount_percent": volume_discount_percent,
            "volume_discount_amount_eur": volume_discount_amount,
            "volume_discount_threshold_linear_m": volume_discount_threshold,
            "paid_monthly_volume_linear_m": paid_monthly_volume,
            "monthly_volume_linear_m": monthly_volume,
        }

    def estimate_reorder_quote(
        self,
        *,
        customer,
        items: list[dict],
        shipping_method_code: str | None = None,
        billing_mode: str | None = None,
    ) -> dict[str, object]:
        """Devis réassort : somme des surfaces déclarées (mm) × quantités."""
        if not items:
            raise ValidationError("Aucun visuel à tarifer pour le réassort.")
        laize_cm = Decimal(int(getattr(settings, "DTF_LAIZE_CM", 55)))
        laize_m = (laize_cm / Decimal("100")).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
        mode = str(getattr(settings, "DTF_METERAGE_AREA_MODE", "laize_fit") or "laize_fit")
        billable = Decimal("0.0000")
        for item in items:
            width_mm = Decimal(str(item["width_mm"]))
            height_mm = Decimal(str(item["height_mm"]))
            qty = max(int(item.get("quantity") or 1), 1)
            if width_mm <= 0 or height_mm <= 0:
                raise ValidationError("Dimensions de réassort invalides.")
            width_m = (width_mm / Decimal("1000")).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
            height_m = (height_mm / Decimal("1000")).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
            area = billable_sqm_from_physical_size(
                width_m=width_m,
                height_m=height_m,
                laize_m=laize_m,
                mode=mode,
            )
            billable += (area * Decimal(qty)).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
        billable = max(billable, Decimal("0.0001"))
        return self.estimate_gang_sheet_quote(
            customer=customer,
            surface_sqm=billable,
            quantity=1,
            file_count=len(items),
            shipping_method_code=shipping_method_code,
            billing_mode=billing_mode,
        )

    def estimate_meterage_from_declared_mm(self, *, upload) -> Decimal | None:
        """Surface m² depuis ``width_mm`` / ``height_mm`` saisis (réassort, config)."""
        width_mm = getattr(upload, "width_mm", None)
        height_mm = getattr(upload, "height_mm", None)
        if width_mm is None or height_mm is None:
            return None
        if width_mm <= 0 or height_mm <= 0:
            return None
        width_m = (Decimal(width_mm) / Decimal("1000")).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
        height_m = (Decimal(height_mm) / Decimal("1000")).quantize(
            FOURPLACES, rounding=ROUND_HALF_UP
        )
        laize_cm = Decimal(int(getattr(settings, "DTF_LAIZE_CM", 55)))
        laize_m = (laize_cm / Decimal("100")).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
        mode = str(getattr(settings, "DTF_METERAGE_AREA_MODE", "laize_fit") or "laize_fit")
        area = billable_sqm_from_physical_size(
            width_m=width_m,
            height_m=height_m,
            laize_m=laize_m,
            mode=mode,
        )
        qty = Decimal(max(int(upload.quantity or 1), 1))
        total = (area * qty).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
        return max(total, Decimal("0.0001"))

    def estimate_meterage_from_inspection(self, *, upload) -> Decimal | None:
        """Surface m² dérivée du contrôle technique (pixels + DPI), sans saisie opérateur.

        Le mode ``laize_fit`` (défaut) aligne le facturable sur une laize configurable
        (``DTF_LAIZE_CM``, ex. 55 cm) : prix au m² cohérent avec une conso. bande sur ce largeur.
        """
        inspection = getattr(upload, "inspection", None)
        if inspection is None:
            return None
        w = inspection.image_width
        h = inspection.image_height
        if not w or not h:
            return None
        dpi = Decimal(int(getattr(settings, "DTF_PRINT_DPI", 300)))
        width_m = Decimal(w) / dpi * Decimal("0.0254")
        height_m = Decimal(h) / dpi * Decimal("0.0254")
        laize_cm = Decimal(int(getattr(settings, "DTF_LAIZE_CM", 55)))
        laize_m = (laize_cm / Decimal("100")).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
        mode = str(getattr(settings, "DTF_METERAGE_AREA_MODE", "laize_fit") or "laize_fit")
        area = billable_sqm_from_physical_size(
            width_m=width_m,
            height_m=height_m,
            laize_m=laize_m,
            mode=mode,
        )
        qty = Decimal(upload.quantity)
        total = (area * qty).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
        return max(total, Decimal("0.0001"))

    def compute_meterage_sqm_for_upload(self, *, upload) -> Decimal | None:
        """Métrage facturable : saisie commande (linéaire × laize réparti),
        puis fichier, sinon inspection.
        """
        order = upload.order
        order_linear = getattr(order, "meterage_override_linear_m", None)
        if order_linear is not None:
            if order_linear <= 0:
                return None
            n = order.uploads.count()
            if n < 1:
                return None
            laize_cm = Decimal(int(getattr(settings, "DTF_LAIZE_CM", 55)))
            laize_m = (laize_cm / Decimal("100")).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
            total_sqm = (order_linear * laize_m).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
            per = (total_sqm / Decimal(n)).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
            return max(per, Decimal("0.0001"))
        linear = getattr(upload, "meterage_override_linear_m", None)
        if linear is not None:
            if linear <= 0:
                return None
            laize_cm = Decimal(int(getattr(settings, "DTF_LAIZE_CM", 55)))
            laize_m = (laize_cm / Decimal("100")).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
            qty = Decimal(upload.quantity)
            total = (linear * laize_m * qty).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
            return max(total, Decimal("0.0001"))
        override = getattr(upload, "meterage_override_sqm", None)
        if override is not None:
            if override <= 0:
                return None
            return override.quantize(FOURPLACES, rounding=ROUND_HALF_UP)
        declared = self.estimate_meterage_from_declared_mm(upload=upload)
        if declared is not None:
            return declared
        return self.estimate_meterage_from_inspection(upload=upload)

    def apply_declared_size_self_service_pricing(
        self,
        *,
        order: Order,
        actor,
        source: str,
    ) -> Order:
        """Fige le métrage depuis les dimensions déclarées (réassort comptant) puis prix."""
        if order.billing_mode != Order.BillingMode.IMMEDIATE:
            raise ValidationError(
                "Le tarif automatique dimensions s’applique aux commandes comptant CB."
            )
        if not order.uses_atelier_pricing():
            raise ValidationError(
                "Le calcul automatique s'applique aux commandes atelier (encours ou comptant CB)."
            )

        uploads = list(order.uploads.all().order_by("sort_order", "created_at"))
        if not uploads:
            raise ValidationError("Aucun fichier à tarifer.")

        for upload in uploads:
            meterage = self.estimate_meterage_from_declared_mm(upload=upload)
            if meterage is None:
                meterage = self.estimate_meterage_from_inspection(upload=upload)
            if meterage is None:
                raise ValidationError(
                    f"Dimensions manquantes pour le fichier « {upload.original_filename} » "
                    ": impossible de calculer le prix du réassort."
                )
            upload.meterage_override_sqm = meterage
            upload.meterage_override_linear_m = None
            upload.save(
                update_fields=[
                    "meterage_override_sqm",
                    "meterage_override_linear_m",
                    "updated_at",
                ]
            )

        record_event(
            action="order.declared_size_meterage_applied",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=order,
            metadata={
                "order_public_id": str(order.public_id),
                "customer_public_id": str(order.customer.public_id),
                "upload_count": len(uploads),
                "source": source,
            },
        )
        return self.compute_and_persist_order_pricing(
            order=order,
            actor=actor,
            source=source,
        )

    def apply_gang_sheet_self_service_pricing(
        self,
        *,
        order: Order,
        actor,
        source: str,
    ) -> Order:
        """Fige le métrage depuis la géométrie Gang Sheet puis calcule le prix.

        Réservé aux commandes comptant CB portail (paiement immédiat sans
        attente du retour atelier).
        """
        from apps.gang_sheets.models import GangSheet

        if order.billing_mode != Order.BillingMode.IMMEDIATE:
            raise ValidationError(
                "Le tarif automatique Gang Sheet s’applique aux commandes comptant CB."
            )
        if not order.uses_atelier_pricing():
            raise ValidationError(
                "Le calcul automatique s'applique aux commandes atelier (encours ou comptant CB)."
            )

        sheets = list(
            GangSheet.objects.filter(
                order_id=order.pk,
                status=GangSheet.Status.VALIDATED,
            ).order_by("created_at")
        )
        if not sheets:
            raise ValidationError(
                "Aucune Gang Sheet validée liée à cette commande : impossible de calculer le prix."
            )

        total_sqm = sum((sheet.surface_sqm for sheet in sheets), Decimal("0.00")).quantize(
            FOURPLACES,
            rounding=ROUND_HALF_UP,
        )
        if total_sqm <= 0:
            raise ValidationError("La surface de la Gang Sheet est invalide.")

        uploads = list(order.uploads.all().order_by("sort_order", "created_at"))
        if not uploads:
            raise ValidationError("Aucun fichier à tarifer.")

        if len(uploads) == 1:
            qty = Decimal(max(int(uploads[0].quantity or 1), 1))
            shares = [(total_sqm * qty).quantize(FOURPLACES, rounding=ROUND_HALF_UP)]
        else:
            share = (total_sqm / Decimal(len(uploads))).quantize(
                FOURPLACES,
                rounding=ROUND_HALF_UP,
            )
            shares = []
            for upload in uploads:
                qty = Decimal(max(int(upload.quantity or 1), 1))
                shares.append((share * qty).quantize(FOURPLACES, rounding=ROUND_HALF_UP))

        for upload, share in zip(uploads, shares, strict=True):
            upload.meterage_override_sqm = max(share, Decimal("0.0001"))
            upload.meterage_override_linear_m = None
            upload.save(
                update_fields=[
                    "meterage_override_sqm",
                    "meterage_override_linear_m",
                    "updated_at",
                ]
            )

        record_event(
            action="order.gang_sheet_meterage_applied",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=order,
            metadata={
                "order_public_id": str(order.public_id),
                "customer_public_id": str(order.customer.public_id),
                "surface_sqm": f"{total_sqm:.4f}",
                "billable_sqm": f"{sum(shares, Decimal('0.00')):.4f}",
                "sheet_count": len(sheets),
                "upload_quantities": [int(u.quantity or 1) for u in uploads],
                "source": source,
            },
        )
        return self.compute_and_persist_order_pricing(
            order=order,
            actor=actor,
            source=source,
        )

    def open_balance_for_customer_excluding_order(self, *, customer, exclude_order: Order | None):
        qs = Order.objects.filter(
            customer=customer,
            billing_mode=Order.BillingMode.DEFERRED,
            pricing_status=Order.PricingStatus.PRICED,
            billing_statement__isnull=True,
        ).exclude(status=Order.Status.DRAFT)
        if exclude_order is not None:
            qs = qs.exclude(pk=exclude_order.pk)
        agg = qs.aggregate(s=Sum("total_amount"))
        total = agg["s"] or Decimal("0.00")
        return total.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    def evaluate_credit_hold(self, *, order: Order, priced_total: Decimal) -> str:
        if order.billing_mode != Order.BillingMode.DEFERRED:
            return Order.CreditHoldStatus.NONE
        profile = CustomerBillingProfile.objects.filter(customer=order.customer).first()
        if profile is None or profile.credit_limit_eur is None:
            return Order.CreditHoldStatus.CLEAR
        other = self.open_balance_for_customer_excluding_order(
            customer=order.customer,
            exclude_order=order,
        )
        projected = (other + priced_total).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        limit = profile.credit_limit_eur
        if projected > limit:
            if profile.enforce_credit_block:
                return Order.CreditHoldStatus.BLOCKED
            return Order.CreditHoldStatus.WARNING
        return Order.CreditHoldStatus.CLEAR

    def _month_bounds(self, month) -> tuple[object, object, datetime, datetime]:
        month_start = month.replace(day=1)
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)
        current_tz = timezone.get_current_timezone()
        starts_at = timezone.make_aware(datetime.combine(month_start, time.min), current_tz)
        ends_at = timezone.make_aware(datetime.combine(next_month, time.min), current_tz)
        return month_start, next_month, starts_at, ends_at

    def _base_unit_price_for_repricing(self, *, order: Order, dtf_lines: list[OrderLine]):
        if order.volume_discount_base_unit_price_eur is not None:
            return order.volume_discount_base_unit_price_eur.quantize(
                TWOPLACES,
                rounding=ROUND_HALF_UP,
            )
        if not dtf_lines:
            raise ValidationError("Une commande tarifée ne contient aucune ligne DTF.")
        current_unit_price = dtf_lines[0].unit_price
        current_discount = order.volume_discount_percent or ZERO_AMOUNT
        if current_discount > 0 and current_discount < Decimal("100.00"):
            factor = (Decimal("100.00") - current_discount) / Decimal("100.00")
            return (current_unit_price / factor).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        return current_unit_price.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    def _recalculate_customer_credit_holds(self, *, customer: Customer) -> str:
        open_orders = Order.objects.select_for_update().filter(
            customer=customer,
            billing_mode=Order.BillingMode.DEFERRED,
            pricing_status=Order.PricingStatus.PRICED,
            billing_statement__isnull=True,
            status=Order.Status.SUBMITTED,
        )
        profile = CustomerBillingProfile.objects.filter(customer=customer).first()
        if profile is None or profile.credit_limit_eur is None:
            hold_status = Order.CreditHoldStatus.CLEAR
        else:
            open_total = open_orders.aggregate(total=Sum("total_amount"))["total"] or ZERO_AMOUNT
            if open_total > profile.credit_limit_eur:
                hold_status = (
                    Order.CreditHoldStatus.BLOCKED
                    if profile.enforce_credit_block
                    else Order.CreditHoldStatus.WARNING
                )
            else:
                hold_status = Order.CreditHoldStatus.CLEAR
        open_orders.exclude(credit_hold_status=hold_status).update(
            credit_hold_status=hold_status,
            updated_at=timezone.now(),
        )
        return hold_status

    @transaction.atomic
    def reprice_deferred_month(
        self,
        *,
        customer: Customer,
        month,
        actor,
        source: str,
    ) -> dict[str, object]:
        """Applique le meilleur palier atteint à tout le DTF non relevé du mois.

        Le verrou client sérialise les tarifications concurrentes. Les lignes de
        préparation et le port restent inchangés ; seules les lignes DTF sont
        recalculées depuis leur prix brut figé.
        """
        customer = Customer.objects.select_for_update().get(pk=customer.pk)
        month_start, _next_month, starts_at, ends_at = self._month_bounds(month)
        monthly_orders = list(
            Order.objects.select_for_update()
            .filter(
                customer=customer,
                billing_mode=Order.BillingMode.DEFERRED,
                pricing_status=Order.PricingStatus.PRICED,
                billing_statement__isnull=True,
                status=Order.Status.SUBMITTED,
                created_at__gte=starts_at,
                created_at__lt=ends_at,
            )
            .prefetch_related("items", "uploads")
            .order_by("created_at", "pk")
        )
        if not monthly_orders:
            return {
                "repriced_count": 0,
                "monthly_volume_linear_m": ZERO_AMOUNT,
                "discount_percent": ZERO_AMOUNT,
                "threshold_linear_m": None,
                "month": month_start,
            }

        dtf_type = CatalogService.ServiceType.DTF_TRANSFER
        total_sqm = sum(
            (
                line.quantity
                for monthly_order in monthly_orders
                for line in monthly_order.items.all()
                if line.service_type == dtf_type
            ),
            ZERO_AMOUNT,
        )
        laize_m = Decimal(int(getattr(settings, "DTF_LAIZE_CM", 55))) / Decimal("100")
        if laize_m <= 0:
            raise ValidationError("DTF_LAIZE_CM doit être strictement positif.")
        monthly_volume = (total_sqm / laize_m).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
        tier = (
            CustomerVolumeDiscountTier.objects.active()
            .filter(
                customer=customer,
                minimum_monthly_linear_m__lte=monthly_volume,
            )
            .order_by("-minimum_monthly_linear_m", "-created_at")
            .first()
        )
        discount_percent = tier.discount_percent if tier is not None else ZERO_AMOUNT
        discount_percent = discount_percent.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        factor = (Decimal("100.00") - discount_percent) / Decimal("100.00")
        actor_or_none = actor if getattr(actor, "is_authenticated", False) else None
        repriced_count = 0

        for monthly_order in monthly_orders:
            all_lines = list(monthly_order.items.all())
            dtf_lines = [line for line in all_lines if line.service_type == dtf_type]
            uploads = list(monthly_order.uploads.all())
            if len(dtf_lines) != len(uploads):
                raise ValidationError(
                    "Le nombre de lignes DTF ne correspond pas au nombre de fichiers tarifés."
                )
            base_unit_price = self._base_unit_price_for_repricing(
                order=monthly_order,
                dtf_lines=dtf_lines,
            )
            effective_unit_price = (base_unit_price * factor).quantize(
                TWOPLACES,
                rounding=ROUND_HALF_UP,
            )
            gross_dtf_amount = ZERO_AMOUNT
            discounted_dtf_amount = ZERO_AMOUNT

            for line, upload in zip(dtf_lines, uploads, strict=True):
                gross_line_total = (line.quantity * base_unit_price).quantize(
                    TWOPLACES,
                    rounding=ROUND_HALF_UP,
                )
                discounted_line_total = (gross_line_total * factor).quantize(
                    TWOPLACES,
                    rounding=ROUND_HALF_UP,
                )
                gross_dtf_amount += gross_line_total
                discounted_dtf_amount += discounted_line_total
                line.unit_price = effective_unit_price
                line.line_total = discounted_line_total
                line.save(update_fields=["unit_price", "line_total", "updated_at"])
                upload.unit_price_eur = effective_unit_price
                upload.line_total_eur = discounted_line_total
                upload.save(update_fields=["unit_price_eur", "line_total_eur", "updated_at"])

            subtotal = sum((line.line_total for line in all_lines), ZERO_AMOUNT).quantize(
                TWOPLACES,
                rounding=ROUND_HALF_UP,
            )
            totals = self.compose_order_totals(
                subtotal_ht=subtotal,
                shipping_ht=monthly_order.shipping_amount,
                billing_mode=monthly_order.billing_mode,
            )
            discount_amount = (gross_dtf_amount - discounted_dtf_amount).quantize(
                TWOPLACES,
                rounding=ROUND_HALF_UP,
            )
            before = {
                "total": monthly_order.total_amount,
                "discount_percent": monthly_order.volume_discount_percent,
                "discount_amount": monthly_order.volume_discount_amount,
                "threshold": monthly_order.volume_discount_threshold_linear_m,
                "monthly_volume": monthly_order.monthly_volume_linear_m,
            }
            monthly_order.subtotal_amount = totals["subtotal_amount"]
            monthly_order.tax_rate = totals["tax_rate"]
            monthly_order.tax_amount = totals["tax_amount"]
            monthly_order.total_amount = totals["total_amount"]
            monthly_order.volume_discount_month = month_start
            monthly_order.monthly_volume_linear_m = monthly_volume
            monthly_order.volume_discount_threshold_linear_m = (
                tier.minimum_monthly_linear_m if tier is not None else None
            )
            monthly_order.volume_discount_percent = discount_percent
            monthly_order.volume_discount_amount = discount_amount
            monthly_order.volume_discount_base_unit_price_eur = base_unit_price
            monthly_order.save(
                update_fields=[
                    "subtotal_amount",
                    "tax_rate",
                    "tax_amount",
                    "total_amount",
                    "volume_discount_month",
                    "monthly_volume_linear_m",
                    "volume_discount_threshold_linear_m",
                    "volume_discount_percent",
                    "volume_discount_amount",
                    "volume_discount_base_unit_price_eur",
                    "updated_at",
                ]
            )
            changed = (
                before["total"] != monthly_order.total_amount
                or before["discount_percent"] != discount_percent
                or before["threshold"] != monthly_order.volume_discount_threshold_linear_m
                or before["monthly_volume"] != monthly_volume
            )
            if changed:
                repriced_count += 1
                record_event(
                    action="order.monthly_volume_discount_repriced",
                    actor=actor_or_none,
                    target=monthly_order,
                    metadata={
                        "order_public_id": str(monthly_order.public_id),
                        "customer_public_id": str(customer.public_id),
                        "month": month_start.isoformat(),
                        "monthly_volume_linear_m": f"{monthly_volume:.4f}",
                        "threshold_linear_m": (
                            f"{tier.minimum_monthly_linear_m:.4f}" if tier is not None else None
                        ),
                        "discount_percent": f"{discount_percent:.2f}",
                        "discount_amount": f"{discount_amount:.2f}",
                        "total_before": f"{before['total']:.2f}",
                        "total_after": f"{monthly_order.total_amount:.2f}",
                        "source": source,
                    },
                )

        credit_hold_status = self._recalculate_customer_credit_holds(customer=customer)
        record_event(
            action="customer.monthly_volume_discount_applied",
            actor=actor_or_none,
            target=customer,
            metadata={
                "customer_public_id": str(customer.public_id),
                "month": month_start.isoformat(),
                "eligible_order_count": len(monthly_orders),
                "repriced_order_count": repriced_count,
                "monthly_volume_linear_m": f"{monthly_volume:.4f}",
                "threshold_linear_m": (
                    f"{tier.minimum_monthly_linear_m:.4f}" if tier is not None else None
                ),
                "discount_percent": f"{discount_percent:.2f}",
                "credit_hold_status": credit_hold_status,
                "source": source,
            },
        )
        if tier is not None and month_start == timezone.localdate().replace(day=1):
            from apps.notifications.services.transactional import (
                schedule_volume_discount_tier_reached_email,
            )

            total_discount_amount = sum(
                (monthly_order.volume_discount_amount for monthly_order in monthly_orders),
                ZERO_AMOUNT,
            ).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
            schedule_volume_discount_tier_reached_email(
                customer=customer,
                month=month_start,
                threshold_linear_m=tier.minimum_monthly_linear_m,
                monthly_volume_linear_m=monthly_volume,
                discount_percent=discount_percent,
                discount_amount=total_discount_amount,
                actor=actor,
                source=source,
            )
        return {
            "repriced_count": repriced_count,
            "monthly_volume_linear_m": monthly_volume,
            "discount_percent": discount_percent,
            "threshold_linear_m": (tier.minimum_monthly_linear_m if tier is not None else None),
            "month": month_start,
        }

    def invalidate_deferred_pricing_after_meterage_change(
        self,
        *,
        order: Order,
        actor,
        source: str,
    ) -> None:
        """Efface lignes et montants persistés pour permettre une nouvelle
        saisie métrage puis « Calculer le prix ».
        """
        if order.billing_statement_id is not None:
            raise ValidationError(
                "La tarification est figée car la commande appartient à un "
                "récapitulatif de facturation."
            )
        if not order.uses_atelier_pricing():
            return
        if order.pricing_status not in (
            Order.PricingStatus.PRICED,
            Order.PricingStatus.FAILED,
        ):
            return
        with transaction.atomic():
            locked = Order.objects.select_for_update().get(pk=order.pk)
            if locked.billing_statement_id is not None:
                raise ValidationError(
                    "La tarification est figée car la commande appartient à un "
                    "récapitulatif de facturation."
                )
            if locked.pricing_status not in (
                Order.PricingStatus.PRICED,
                Order.PricingStatus.FAILED,
            ):
                return
            locked.items.all().delete()
            locked.uploads.update(
                meterage_sqm=None,
                unit_price_eur=None,
                line_total_eur=None,
            )
            locked.subtotal_amount = ZERO_AMOUNT
            locked.shipping_amount = ZERO_AMOUNT
            locked.tax_rate = ZERO_AMOUNT
            locked.tax_amount = ZERO_AMOUNT
            locked.total_amount = ZERO_AMOUNT
            locked.pricing_status = Order.PricingStatus.PENDING
            locked.credit_hold_status = Order.CreditHoldStatus.NONE
            locked.volume_discount_month = None
            locked.monthly_volume_linear_m = None
            locked.volume_discount_threshold_linear_m = None
            locked.volume_discount_percent = ZERO_AMOUNT
            locked.volume_discount_amount = ZERO_AMOUNT
            locked.volume_discount_base_unit_price_eur = None
            locked.save(
                update_fields=[
                    "subtotal_amount",
                    "shipping_amount",
                    "tax_rate",
                    "tax_amount",
                    "total_amount",
                    "pricing_status",
                    "credit_hold_status",
                    "volume_discount_month",
                    "monthly_volume_linear_m",
                    "volume_discount_threshold_linear_m",
                    "volume_discount_percent",
                    "volume_discount_amount",
                    "volume_discount_base_unit_price_eur",
                    "updated_at",
                ]
            )
        if order.billing_mode == Order.BillingMode.DEFERRED:
            self.reprice_deferred_month(
                customer=order.customer,
                month=timezone.localtime(order.created_at).date(),
                actor=actor,
                source=f"{source}.meterage_invalidated",
            )
        pricing_actor = (
            actor if actor is not None and getattr(actor, "is_authenticated", False) else None
        )
        record_event(
            action="order.pricing_invalidated_meterage_change",
            actor=pricing_actor,
            target=order,
            metadata={
                "order_public_id": str(order.public_id),
                "source": source,
            },
        )

    @transaction.atomic
    def compute_and_persist_order_pricing(
        self,
        *,
        order: Order,
        actor,
        source: str,
    ) -> Order:
        Customer.objects.select_for_update().get(pk=order.customer_id)
        order = Order.objects.select_for_update().select_related("customer").get(pk=order.pk)
        if order.billing_statement_id is not None:
            raise ValidationError(
                "La tarification est figée car la commande appartient à un "
                "récapitulatif de facturation."
            )
        from apps.billing.services.production_payment_gate import order_has_captured_payment

        if order.billing_mode == Order.BillingMode.IMMEDIATE and order_has_captured_payment(order):
            raise ValidationError("Le tarif est figé après paiement.")
        if not order.uses_atelier_pricing():
            raise ValidationError(
                "Le calcul automatique s'applique aux commandes atelier (encours ou comptant CB)."
            )
        if order.status != Order.Status.SUBMITTED:
            raise ValidationError("La commande doit être soumise par le client avant tarification.")

        unit_price = self.resolve_unit_price_per_sqm(customer=order.customer)
        dtf_service = self.get_default_dtf_service()
        prep_service = self.get_default_file_preparation_service()
        prep_fee_per_file = self.resolve_file_preparation_fee_per_file(customer=order.customer)

        uploads = list(order.uploads.all().order_by("sort_order", "created_at"))
        if not uploads:
            raise ValidationError("Aucun fichier à tarifer.")

        priced_lines: list[tuple[object, Decimal, Decimal]] = []
        for upload in uploads:
            meterage = self.compute_meterage_sqm_for_upload(upload=upload)
            if meterage is None:
                raise ValidationError(
                    f"Dimensions manquantes pour le fichier « {upload.original_filename} » "
                    "(contrôle technique requis avant tarification)."
                )
            line_total = (meterage * unit_price).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
            priced_lines.append((upload, meterage, line_total))

        n_uploads = len(priced_lines)
        prep_line_total = (Decimal(n_uploads) * prep_fee_per_file).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )
        dtf_subtotal = sum((line[2] for line in priced_lines), Decimal("0.00")).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )
        volume_discount_month = None
        monthly_volume_linear_m = None
        volume_discount_threshold_linear_m = None
        volume_discount_percent = ZERO_AMOUNT
        volume_discount_amount = ZERO_AMOUNT
        effective_unit_price = unit_price
        if order.billing_mode == Order.BillingMode.IMMEDIATE and is_cash_volume_customer(
            order.customer
        ):
            total_sqm = sum((line[1] for line in priced_lines), Decimal("0.00"))
            additional_linear = linear_meters_from_sqm(total_sqm)
            month = timezone.localtime(order.created_at).date()
            _paid_volume, quote_volume, tier = quote_volume_and_tier(
                customer=order.customer,
                additional_linear_m=additional_linear,
                month=month,
                exclude_order_id=order.pk,
            )
            month_start, _next_month, _starts_at, _ends_at = self._month_bounds(month)
            volume_discount_month = month_start
            monthly_volume_linear_m = quote_volume
            if tier is not None:
                volume_discount_percent = tier.discount_percent.quantize(
                    TWOPLACES,
                    rounding=ROUND_HALF_UP,
                )
                volume_discount_threshold_linear_m = tier.minimum_monthly_linear_m
                factor = (Decimal("100.00") - volume_discount_percent) / Decimal("100.00")
                effective_unit_price = (unit_price * factor).quantize(
                    TWOPLACES,
                    rounding=ROUND_HALF_UP,
                )
                discounted_lines = []
                discounted_dtf = ZERO_AMOUNT
                for upload, meterage, line_total in priced_lines:
                    discounted_total = (line_total * factor).quantize(
                        TWOPLACES,
                        rounding=ROUND_HALF_UP,
                    )
                    discounted_dtf += discounted_total
                    discounted_lines.append((upload, meterage, discounted_total))
                volume_discount_amount = (dtf_subtotal - discounted_dtf).quantize(
                    TWOPLACES,
                    rounding=ROUND_HALF_UP,
                )
                priced_lines = discounted_lines
                dtf_subtotal = discounted_dtf
        subtotal = (dtf_subtotal + prep_line_total).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        shipping_ht = self.shipping_methods.resolve_shipping_amount_for_order(order)
        totals = self.compose_order_totals(
            subtotal_ht=subtotal,
            shipping_ht=shipping_ht,
            billing_mode=order.billing_mode,
        )
        credit_hold = self.evaluate_credit_hold(
            order=order,
            priced_total=totals["total_amount"],
        )

        with transaction.atomic():
            order_locked = Order.objects.select_for_update().get(pk=order.pk)
            if order_locked.billing_statement_id is not None:
                raise ValidationError(
                    "La tarification est figée car la commande appartient à un "
                    "récapitulatif de facturation."
                )
            order_locked.items.all().delete()

            for position, (upload, meterage, line_total) in enumerate(priced_lines, start=1):
                OrderLine.objects.create(
                    order=order_locked,
                    service=dtf_service,
                    position=position,
                    service_code=dtf_service.code,
                    service_name=dtf_service.name,
                    service_type=dtf_service.service_type,
                    unit=dtf_service.unit,
                    quantity=meterage,
                    unit_price=effective_unit_price,
                    line_total=line_total,
                )
                upload.meterage_sqm = meterage
                upload.unit_price_eur = effective_unit_price
                upload.line_total_eur = line_total
                upload.save(
                    update_fields=[
                        "meterage_sqm",
                        "unit_price_eur",
                        "line_total_eur",
                        "updated_at",
                    ]
                )

            prep_position = len(priced_lines) + 1
            OrderLine.objects.create(
                order=order_locked,
                service=prep_service,
                position=prep_position,
                service_code=prep_service.code,
                service_name=prep_service.name,
                service_type=prep_service.service_type,
                unit=prep_service.unit,
                quantity=Decimal(str(n_uploads)),
                unit_price=prep_fee_per_file,
                line_total=prep_line_total,
            )

            order_locked.subtotal_amount = totals["subtotal_amount"]
            order_locked.shipping_amount = totals["shipping_amount"]
            order_locked.tax_rate = totals["tax_rate"]
            order_locked.tax_amount = totals["tax_amount"]
            order_locked.total_amount = totals["total_amount"]
            order_locked.currency = dtf_service.currency
            order_locked.pricing_status = Order.PricingStatus.PRICED
            order_locked.credit_hold_status = credit_hold
            order_locked.volume_discount_month = volume_discount_month
            order_locked.monthly_volume_linear_m = monthly_volume_linear_m
            order_locked.volume_discount_threshold_linear_m = volume_discount_threshold_linear_m
            order_locked.volume_discount_percent = volume_discount_percent
            order_locked.volume_discount_amount = volume_discount_amount
            order_locked.volume_discount_base_unit_price_eur = unit_price
            order_locked.save(
                update_fields=[
                    "subtotal_amount",
                    "shipping_amount",
                    "tax_rate",
                    "tax_amount",
                    "total_amount",
                    "currency",
                    "pricing_status",
                    "credit_hold_status",
                    "volume_discount_month",
                    "monthly_volume_linear_m",
                    "volume_discount_threshold_linear_m",
                    "volume_discount_percent",
                    "volume_discount_amount",
                    "volume_discount_base_unit_price_eur",
                    "updated_at",
                ]
            )

        if order.billing_mode == Order.BillingMode.DEFERRED:
            self.reprice_deferred_month(
                customer=order.customer,
                month=timezone.localtime(order.created_at).date(),
                actor=actor,
                source=f"{source}.pricing_computed",
            )

        refreshed = Order.objects.get(pk=order.pk)

        pricing_actor = (
            actor if actor is not None and getattr(actor, "is_authenticated", False) else None
        )
        record_event(
            action="order.pricing_computed",
            actor=pricing_actor,
            target=order,
            metadata={
                "order_public_id": str(order.public_id),
                "customer_public_id": str(order.customer.public_id),
                "subtotal": f"{refreshed.subtotal_amount:.2f}",
                "shipping_amount": f"{refreshed.shipping_amount:.2f}",
                "shipping_method_code": order.shipping_method_code or "",
                "tax_rate": f"{refreshed.tax_rate:.4f}",
                "tax_amount": f"{refreshed.tax_amount:.2f}",
                "total": f"{refreshed.total_amount:.2f}",
                "dtf_gross_subtotal": f"{dtf_subtotal:.2f}",
                "monthly_volume_linear_m": (
                    f"{refreshed.monthly_volume_linear_m:.4f}"
                    if refreshed.monthly_volume_linear_m is not None
                    else None
                ),
                "volume_discount_percent": f"{refreshed.volume_discount_percent:.2f}",
                "volume_discount_amount": f"{refreshed.volume_discount_amount:.2f}",
                "file_preparation_line_total": f"{prep_line_total:.2f}",
                "file_preparation_fee_per_file": f"{prep_fee_per_file:.2f}",
                "credit_hold_status": refreshed.credit_hold_status,
                "source": source,
            },
        )

        if refreshed.billing_mode == Order.BillingMode.DEFERRED:
            from apps.notifications.services.transactional import schedule_order_priced_email

            schedule_order_priced_email(order_public_id=refreshed.public_id)
        elif refreshed.billing_mode == Order.BillingMode.IMMEDIATE:
            from apps.notifications.services.transactional import (
                schedule_order_awaiting_payment_email,
            )

            schedule_order_awaiting_payment_email(order_public_id=refreshed.public_id)
        return refreshed
