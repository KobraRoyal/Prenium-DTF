from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError

from apps.customers.models import Customer
from apps.orders.services.business_days import add_business_days
from apps.shipping.models import ZERO_AMOUNT, ShippingMethod

TWOPLACES = Decimal("0.01")

# Alignement intention logistique compte → option commerciale catalogue.
DEFAULT_SHIPPING_MODE_TO_METHOD_CODE = {
    Customer.DefaultShippingMode.PICKUP: "pickup",
    Customer.DefaultShippingMode.CARRIER: "standard",
    Customer.DefaultShippingMode.DIRECT: "standard",
}

DELIVERY_ESTIMATE_DAYS_BY_METHOD_CODE = {
    "standard": 3,
    "express": 1,
}

# Anciens libellés catalogue, remplacés sans écraser un délai ou un nom saisi à la main.
_LEGACY_ETA_LABELS = {
    "pickup": frozenset(
        {
            "",
            "Dès disponibilité atelier",
            "Traitement en 1–2 jours",
            "Traitement de la commande en 1–2 jours.",
        }
    ),
    "standard": frozenset(
        {
            "",
            "48–72 h après expédition",
            "Délai de traitement : 2–3 jours",
            "Traitement de la commande en 2–3 jours. Livraison via Chronopost 13.",
        }
    ),
    "express": frozenset(
        {
            "",
            "24 h après expédition",
            "Traitement en 1–2 jours",
            "Traitement de la commande en 1–2 jours. Livraison via Chronopost 13.",
        }
    ),
}
_LEGACY_METHOD_NAMES = {
    "standard": frozenset({"Livraison standard"}),
    "express": frozenset({"Livraison express"}),
}
_SHIPPING_MODE_DISPLAY_NAMES = {
    "livraison standard": "Standard",
    "standard": "Standard",
    "livraison express": "Express",
    "express": "Express",
    "retrait atelier": "Retrait atelier",
    "retrait": "Retrait atelier",
    "pickup": "Retrait atelier",
}

DEFAULT_METHOD_SEED = (
    {
        "code": "pickup",
        "name": "Retrait atelier",
        "description": "Retrait sur place — aucun frais d’expédition.",
        "base_price": Decimal("0.00"),
        "is_pickup": True,
        "eta_label": "1–2 jours",
        "display_order": 10,
    },
    {
        "code": "standard",
        "name": "Standard",
        "description": "Expédition transporteur en délai standard.",
        "base_price": Decimal("8.00"),
        "is_pickup": False,
        "eta_label": "2–3 jours · Chronopost 13",
        "display_order": 20,
    },
    {
        "code": "express",
        "name": "Express",
        "description": "Expédition prioritaire.",
        "base_price": Decimal("18.00"),
        "is_pickup": False,
        "eta_label": "1–2 jours · Chronopost 13",
        "display_order": 30,
    },
)


def present_shipping_mode_name(value: str) -> str:
    """Nom court du mode d’expédition, y compris pour un libellé déjà figé."""
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    return _SHIPPING_MODE_DISPLAY_NAMES.get(cleaned.casefold(), cleaned)


def shipping_choice_label(method) -> str:
    """Libellé d’option : mode, puis délai de traitement."""
    eta = str(getattr(method, "eta_label", "") or "").strip()
    name = present_shipping_mode_name(getattr(method, "name", ""))
    if eta:
        return f"{name} — {eta}"
    return name


def order_uses_pickup(order) -> bool:
    """Return whether an order snapshot points to a workshop pickup method."""
    code = str(getattr(order, "shipping_method_code", "") or "").strip().lower()
    if not code:
        return False
    if code == "pickup":
        return True
    return ShippingMethod.objects.filter(code=code, is_pickup=True).exists()


class ShippingMethodService:
    """Catalogue et résolution des options de livraison client."""

    def list_active_methods(self):
        return list(ShippingMethod.objects.active().order_by("display_order", "name"))

    def ensure_default_methods(self) -> list[ShippingMethod]:
        """Crée les options V1 si absentes (idempotent)."""
        created: list[ShippingMethod] = []
        for payload in DEFAULT_METHOD_SEED:
            method, was_created = ShippingMethod.objects.get_or_create(
                code=payload["code"],
                defaults={
                    "name": payload["name"],
                    "description": payload["description"],
                    "base_price": payload["base_price"],
                    "is_pickup": payload["is_pickup"],
                    "eta_label": payload["eta_label"],
                    "display_order": payload["display_order"],
                    "is_active": True,
                    "currency": "EUR",
                },
            )
            if was_created:
                created.append(method)
                continue
            update_fields: list[str] = []
            legacy_eta = _LEGACY_ETA_LABELS.get(payload["code"])
            if (
                legacy_eta is not None
                and method.eta_label in legacy_eta
                and method.eta_label != payload["eta_label"]
            ):
                method.eta_label = payload["eta_label"]
                update_fields.append("eta_label")
            legacy_names = _LEGACY_METHOD_NAMES.get(payload["code"])
            if legacy_names and method.name in legacy_names and method.name != payload["name"]:
                method.name = payload["name"]
                update_fields.append("name")
            if update_fields:
                update_fields.append("updated_at")
                method.save(update_fields=update_fields)
        return created

    def get_active_by_code(self, code: str | None) -> ShippingMethod | None:
        normalized = str(code or "").strip().lower()
        if not normalized:
            return None
        return ShippingMethod.objects.active().filter(code=normalized).first()

    def require_active_by_code(self, code: str | None) -> ShippingMethod:
        method = self.get_active_by_code(code)
        if method is None:
            raise ValidationError(
                "Choisissez un mode d’expédition valide (retrait atelier, standard ou express)."
            )
        return method

    def checkout_ui_context(self, *, customer, order=None, widget: str = "radios") -> dict:
        """Contexte UI choix livraison (checkout classique / partials)."""
        self.ensure_default_methods()
        locks_pickup = self.customer_locks_shipping_to_pickup(customer)
        if locks_pickup:
            return {
                "shipping_methods": self.list_active_methods(),
                "selected_shipping_method_code": "pickup",
                "show_shipping_choice": False,
                "shipping_choice_widget": "hidden",
                "shipping_locked_to_pickup": True,
            }
        if order is not None and getattr(order, "shipping_method_code", ""):
            selected = order.shipping_method_code
        else:
            selected = self.resolve_default_code_for_customer(customer)
        return {
            "shipping_methods": self.list_active_methods(),
            "selected_shipping_method_code": selected,
            "show_shipping_choice": True,
            "shipping_choice_widget": widget,
            "shipping_locked_to_pickup": False,
        }

    def customer_locks_shipping_to_pickup(self, customer) -> bool:
        """Compte configuré en retrait atelier : pas de choix livraison commande."""
        preferred = getattr(customer, "default_shipping_method", None)
        if preferred is not None and preferred.is_active and preferred.is_pickup:
            return True
        mode = getattr(customer, "default_shipping_mode", None)
        return mode == Customer.DefaultShippingMode.PICKUP

    def resolve_default_code_for_customer(self, customer) -> str:
        if self.customer_locks_shipping_to_pickup(customer):
            self.ensure_default_methods()
            return "pickup"
        preferred = getattr(customer, "default_shipping_method", None)
        if preferred is not None and preferred.is_active:
            return preferred.code
        mode = getattr(
            customer,
            "default_shipping_mode",
            Customer.DefaultShippingMode.PICKUP,
        )
        return DEFAULT_SHIPPING_MODE_TO_METHOD_CODE.get(mode, "pickup")

    def resolve_method_for_customer(
        self,
        *,
        customer,
        shipping_method_code: str | None = None,
    ) -> ShippingMethod:
        self.ensure_default_methods()
        if self.customer_locks_shipping_to_pickup(customer):
            return self.require_active_by_code("pickup")
        if shipping_method_code:
            return self.require_active_by_code(shipping_method_code)
        return self.require_active_by_code(self.resolve_default_code_for_customer(customer))

    def snapshot_dict(self, method: ShippingMethod) -> dict[str, object]:
        amount = method.resolved_price.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        return {
            "shipping_method_code": method.code,
            "shipping_method_name": present_shipping_mode_name(method.name),
            "shipping_amount": amount,
            "shipping_is_pickup": bool(method.is_pickup),
            "currency": method.currency or "EUR",
        }

    def apply_snapshot_to_order(self, *, order, method: ShippingMethod) -> None:
        snap = self.snapshot_dict(method)
        order.shipping_method_code = str(snap["shipping_method_code"])
        order.shipping_method_name = str(snap["shipping_method_name"])
        order.shipping_amount = snap["shipping_amount"]  # type: ignore[assignment]
        # Montant figé au choix ; recalculé à la tarification via resolve_shipping_amount.

    def resolve_shipping_amount_for_order(self, order) -> Decimal:
        """Montant port HT à partir du snapshot commande.

        Sans code (commandes legacy) → 0 € pour ne pas régresser les totaux existants.
        Si le catalogue a changé, le snapshot `shipping_amount` déjà présent n’est
        pas réutilisé aveuglément : on re-résout via le code actif, sauf méthode
        désactivée auquel cas on conserve le montant snapshot.
        """
        code = str(getattr(order, "shipping_method_code", "") or "").strip()
        if not code:
            return ZERO_AMOUNT
        method = self.get_active_by_code(code)
        if method is not None:
            return method.resolved_price.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        existing = getattr(order, "shipping_amount", None)
        if existing is not None:
            return Decimal(existing).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        return ZERO_AMOUNT

    def estimated_delivery_date(self, *, order, declared_on: date) -> date | None:
        """Return the client promise date for catalog delivery methods.

        The button labels state the processing time: standard 2–3 days, express
        and workshop pickup 1–2 days. Standard and express add Chronopost 13
        delivery. The stored date uses the outer bound of the carrier promise
        and intentionally leaves custom methods unset.
        """
        days = DELIVERY_ESTIMATE_DAYS_BY_METHOD_CODE.get(
            str(getattr(order, "shipping_method_code", "") or "").strip().lower()
        )
        return add_business_days(declared_on, days) if days else None
