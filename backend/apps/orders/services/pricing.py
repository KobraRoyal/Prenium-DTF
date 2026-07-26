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
            else str(
                getattr(customer, "default_billing_mode", Order.BillingMode.DEFERRED)
            )
            .strip()
            .lower()
        )
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
        }

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
        if not order.uses_atelier_pricing():
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
            locked.shipping_amount = ZERO_AMOUNT
            locked.tax_rate = ZERO_AMOUNT
            locked.tax_amount = ZERO_AMOUNT
            locked.total_amount = ZERO_AMOUNT
            locked.pricing_status = Order.PricingStatus.PENDING
            locked.credit_hold_status = Order.CreditHoldStatus.NONE
            locked.save(
                update_fields=[
                    "subtotal_amount",
                    "shipping_amount",
                    "tax_rate",
                    "tax_amount",
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

            order_locked.subtotal_amount = totals["subtotal_amount"]
            order_locked.shipping_amount = totals["shipping_amount"]
            order_locked.tax_rate = totals["tax_rate"]
            order_locked.tax_amount = totals["tax_amount"]
            order_locked.total_amount = totals["total_amount"]
            order_locked.currency = dtf_service.currency
            order_locked.pricing_status = Order.PricingStatus.PRICED
            order_locked.credit_hold_status = credit_hold
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
                "subtotal": f"{totals['subtotal_amount']:.2f}",
                "shipping_amount": f"{totals['shipping_amount']:.2f}",
                "shipping_method_code": order.shipping_method_code or "",
                "tax_rate": f"{totals['tax_rate']:.4f}",
                "tax_amount": f"{totals['tax_amount']:.2f}",
                "total": f"{totals['total_amount']:.2f}",
                "dtf_subtotal": f"{dtf_subtotal:.2f}",
                "file_preparation_line_total": f"{prep_line_total:.2f}",
                "file_preparation_fee_per_file": f"{prep_fee_per_file:.2f}",
                "credit_hold_status": credit_hold,
                "source": source,
            },
        )

        refreshed = Order.objects.get(pk=order.pk)
        if refreshed.billing_mode == Order.BillingMode.DEFERRED:
            from apps.notifications.services.transactional import schedule_order_priced_email

            schedule_order_priced_email(order_public_id=refreshed.public_id)
        elif refreshed.billing_mode == Order.BillingMode.IMMEDIATE:
            from apps.notifications.services.transactional import (
                schedule_order_awaiting_payment_email,
            )

            schedule_order_awaiting_payment_email(order_public_id=refreshed.public_id)
        return refreshed
