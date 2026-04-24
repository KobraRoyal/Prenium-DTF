from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from apps.auditlog.services import record_event
from apps.catalog.models import CatalogService
from apps.customers.models import CustomerBillingProfile
from apps.orders.models import ZERO_AMOUNT, Order, OrderLine

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
    """

    def get_default_dtf_service(self) -> CatalogService:
        service = (
            CatalogService.objects.active()
            .filter(
                service_type=CatalogService.ServiceType.DTF_TRANSFER,
                unit=CatalogService.Unit.LINEAR_METER,
            )
            .order_by("display_order", "name")
            .first()
        )
        if service is None:
            raise ValidationError("Aucun service DTF au mètre actif dans le catalogue.")
        return service

    def get_default_file_preparation_service(self) -> CatalogService:
        service = (
            CatalogService.objects.active()
            .filter(
                service_type=CatalogService.ServiceType.FILE_PREPARATION,
                unit=CatalogService.Unit.FIXED,
            )
            .order_by("display_order", "name")
            .first()
        )
        if service is None:
            raise ValidationError(
                "Aucun service « Préparation fichier » (forfait) actif dans le catalogue."
            )
        return service

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
        return self.estimate_meterage_from_inspection(upload=upload)

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
        if order.billing_mode != Order.BillingMode.DEFERRED:
            return
        if order.pricing_status not in (
            Order.PricingStatus.PRICED,
            Order.PricingStatus.FAILED,
        ):
            return
        with transaction.atomic():
            locked = Order.objects.select_for_update().get(pk=order.pk)
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
            locked.total_amount = ZERO_AMOUNT
            locked.pricing_status = Order.PricingStatus.PENDING
            locked.credit_hold_status = Order.CreditHoldStatus.NONE
            locked.save(
                update_fields=[
                    "subtotal_amount",
                    "total_amount",
                    "pricing_status",
                    "credit_hold_status",
                    "updated_at",
                ]
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

    def compute_and_persist_order_pricing(
        self,
        *,
        order: Order,
        actor,
        source: str,
    ) -> Order:
        if order.billing_mode != Order.BillingMode.DEFERRED:
            raise ValidationError(
                "Le calcul automatique s'applique aux commandes en facturation différée."
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
        subtotal = (dtf_subtotal + prep_line_total).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        credit_hold = self.evaluate_credit_hold(order=order, priced_total=subtotal)

        with transaction.atomic():
            order_locked = Order.objects.select_for_update().get(pk=order.pk)
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
                    unit_price=unit_price,
                    line_total=line_total,
                )
                upload.meterage_sqm = meterage
                upload.unit_price_eur = unit_price
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

            order_locked.subtotal_amount = subtotal
            order_locked.total_amount = subtotal
            order_locked.currency = dtf_service.currency
            order_locked.pricing_status = Order.PricingStatus.PRICED
            order_locked.credit_hold_status = credit_hold
            order_locked.save(
                update_fields=[
                    "subtotal_amount",
                    "total_amount",
                    "currency",
                    "pricing_status",
                    "credit_hold_status",
                    "updated_at",
                ]
            )

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
                "subtotal": f"{subtotal:.2f}",
                "dtf_subtotal": f"{dtf_subtotal:.2f}",
                "file_preparation_line_total": f"{prep_line_total:.2f}",
                "file_preparation_fee_per_file": f"{prep_fee_per_file:.2f}",
                "credit_hold_status": credit_hold,
                "source": source,
            },
        )

        refreshed = Order.objects.get(pk=order.pk)
        from apps.notifications.services.transactional import schedule_order_priced_email

        schedule_order_priced_email(order_public_id=refreshed.public_id)
        return refreshed
