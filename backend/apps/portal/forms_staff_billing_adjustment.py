"""Formulaire Atelier : ajustement facturation (encours uniquement)."""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal

from django import forms
from django.conf import settings

from apps.catalog.models import CatalogService
from apps.customers.services.volume_discounts import (
    dtf_laize_m,
    linear_meters_from_sqm,
    sqm_from_linear_meters,
)
from apps.shipping.services.methods import ShippingMethodService

TWOPLACES = Decimal("0.01")
FOURPLACES = Decimal("0.0001")


class StaffBillingAdjustmentForm(forms.Form):
    shipping_method_code = forms.ChoiceField(
        label="Mode de livraison",
        choices=[],
    )
    shipping_amount = forms.DecimalField(
        label="Frais de port HT",
        min_value=Decimal("0.00"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        help_text="Montant libre ; le catalogue préremplit selon le mode choisi.",
    )

    def __init__(self, *args, order, **kwargs):
        super().__init__(*args, **kwargs)
        self.order = order
        self.laize_m = dtf_laize_m()
        self.laize_cm = int(getattr(settings, "DTF_LAIZE_CM", 55))
        self.lines = list(order.items.all().order_by("position", "created_at"))
        dtf_type = CatalogService.ServiceType.DTF_TRANSFER
        self.dtf_lines = [line for line in self.lines if line.service_type == dtf_type]
        self.other_lines = [line for line in self.lines if line.service_type != dtf_type]
        self.group_dtf = bool(self.dtf_lines) and order.uses_atelier_pricing()
        shipping = ShippingMethodService()
        shipping.ensure_default_methods()
        methods = shipping.list_active_methods()
        self.shipping_methods = methods
        self.fields["shipping_method_code"].choices = [
            (method.code, method.name) for method in methods
        ]
        if not self.is_bound:
            self.fields["shipping_method_code"].initial = (
                order.shipping_method_code or (methods[0].code if methods else "")
            )
            self.fields["shipping_amount"].initial = order.shipping_amount
        self.catalog_shipping_amounts = {
            method.code: f"{method.resolved_price:.2f}" for method in methods
        }
        self.shipping_method_cards = [
            {
                "code": method.code,
                "name": method.name,
                "amount": method.resolved_price,
                "amount_display": f"{method.resolved_price:.2f}",
                "is_pickup": bool(method.is_pickup),
                "eta_label": getattr(method, "eta_label", "") or "",
            }
            for method in methods
        ]
        self.line_rows: list[dict] = []
        if self.group_dtf:
            self._build_grouped_dtf_row()
            for line in self.other_lines:
                self._append_line_row(line)
        else:
            for line in self.lines:
                self._append_line_row(line)
        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css} ui-input".strip()
        for row in self.line_rows:
            row["quantity"] = self[row["quantity_name"]]
            row["unit_price"] = self[row["unit_price_name"]]
            if row.get("is_dtf_group"):
                row["linear"] = self[row["linear_name"]]
                linear_val = row["linear"].value()
                if linear_val not in (None, ""):
                    row["linear_placeholder"] = self._format_qty_placeholder(float(linear_val))
            qty_val = row["quantity"].value()
            price_val = row["unit_price"].value()
            if qty_val not in (None, ""):
                row["qty_placeholder"] = self._format_qty_placeholder(float(qty_val))
            if price_val not in (None, ""):
                row["price_placeholder"] = self._format_money_placeholder(float(price_val))

    def _build_grouped_dtf_row(self) -> None:
        total_qty = sum((line.quantity for line in self.dtf_lines), Decimal("0")).quantize(
            FOURPLACES, rounding=ROUND_HALF_UP
        )
        prices = {line.unit_price for line in self.dtf_lines}
        unit_price = (
            next(iter(prices))
            if len(prices) == 1
            else (
                (sum((line.line_total for line in self.dtf_lines), Decimal("0")) / total_qty)
                if total_qty > 0
                else Decimal("0")
            ).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        )
        linear_m = (
            self.order.meterage_override_linear_m
            if self.order.meterage_override_linear_m is not None
            else linear_meters_from_sqm(total_qty)
        )
        visual_count = len(self.dtf_lines)
        linear_name = "dtf_group_linear_m"
        qty_name = "dtf_group_quantity"
        price_name = "dtf_group_unit_price"
        self.fields[linear_name] = forms.DecimalField(
            label="Métrage linéaire",
            min_value=Decimal("0.01"),
            max_digits=10,
            decimal_places=4,
            widget=forms.NumberInput(attrs={"step": "0.0001", "min": "0.01"}),
        )
        self.fields[qty_name] = forms.DecimalField(
            label="Quantité m²",
            min_value=Decimal("0.01"),
            max_digits=10,
            decimal_places=4,
            required=False,
            widget=forms.HiddenInput(),
        )
        self.fields[price_name] = forms.DecimalField(
            label="Prix unitaire HT",
            min_value=Decimal("0.00"),
            max_digits=10,
            decimal_places=2,
            widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        )
        if not self.is_bound:
            self.fields[linear_name].initial = linear_m
            self.fields[qty_name].initial = total_qty
            self.fields[price_name].initial = unit_price
        subtitle = f"{visual_count} visuel{'s' if visual_count > 1 else ''}"
        subtitle = f"{subtitle} · laize {self.laize_cm} cm"
        self.line_rows.append(
            {
                "line": None,
                "is_dtf_group": True,
                "label": "Impression DTF",
                "subtitle": subtitle,
                "dtf_line_public_ids": [str(line.public_id) for line in self.dtf_lines],
                "linear_name": linear_name,
                "quantity_name": qty_name,
                "unit_price_name": price_name,
                "linear_placeholder": self._format_qty_placeholder(float(linear_m)),
                "qty_placeholder": self._format_qty_placeholder(float(total_qty)),
                "price_placeholder": self._format_money_placeholder(float(unit_price)),
            }
        )

    def _append_line_row(self, line) -> None:
        qty_name = f"line_{line.public_id}_quantity"
        price_name = f"line_{line.public_id}_unit_price"
        self.fields[qty_name] = forms.DecimalField(
            label="Quantité",
            min_value=Decimal("0.01"),
            max_digits=10,
            decimal_places=4,
            widget=forms.NumberInput(attrs={"step": "0.0001", "min": "0.01"}),
        )
        self.fields[price_name] = forms.DecimalField(
            label="Prix unitaire HT",
            min_value=Decimal("0.00"),
            max_digits=10,
            decimal_places=2,
            widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        )
        if not self.is_bound:
            self.fields[qty_name].initial = line.quantity
            self.fields[price_name].initial = line.unit_price
        preparation = line.service_type == CatalogService.ServiceType.FILE_PREPARATION
        self.line_rows.append(
            {
                "line": line,
                "is_dtf_group": False,
                "label": "Préparation des fichiers" if preparation else line.service_name,
                "subtitle": "",
                "quantity_name": qty_name,
                "unit_price_name": price_name,
                "qty_placeholder": self._format_qty_placeholder(float(line.quantity)),
                "price_placeholder": self._format_money_placeholder(float(line.unit_price)),
            }
        )

    @property
    def catalog_shipping_amounts_json(self) -> str:
        return json.dumps(self.catalog_shipping_amounts)

    @property
    def alpine_lines_payload(self) -> list[dict]:
        payload = []
        for row in self.line_rows:
            price = row["unit_price"].value()
            price_num = float(price) if price not in (None, "") else 0.0
            if row.get("is_dtf_group"):
                linear = row["linear"].value()
                linear_num = float(linear) if linear not in (None, "") else 0.0
                qty_num = float(sqm_from_linear_meters(Decimal(str(linear_num))))
                payload.append(
                    {
                        "label": row.get("label") or "Impression DTF",
                        "qtyMode": "linear",
                        "linearM": linear_num,
                        "baselineLinearM": linear_num,
                        "qty": qty_num,
                        "baselineQty": qty_num,
                        "unitPrice": price_num,
                        "baselineUnitPrice": price_num,
                        "laizeM": float(self.laize_m),
                        "laizeCm": self.laize_cm,
                        "linearPlaceholder": self._format_qty_placeholder(linear_num),
                        "pricePlaceholder": self._format_money_placeholder(price_num),
                    }
                )
                continue
            qty = row["quantity"].value()
            qty_num = float(qty) if qty not in (None, "") else 0.0
            payload.append(
                {
                    "label": row.get("label")
                    or (row["line"].service_name if row.get("line") is not None else "Ligne"),
                    "qtyMode": "quantity",
                    "qty": qty_num,
                    "unitPrice": price_num,
                    "baselineQty": qty_num,
                    "baselineUnitPrice": price_num,
                    "qtyPlaceholder": self._format_qty_placeholder(qty_num),
                    "pricePlaceholder": self._format_money_placeholder(price_num),
                }
            )
        return payload

    @staticmethod
    def _format_qty_placeholder(value: float) -> str:
        text = f"{Decimal(str(value)):f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"

    @staticmethod
    def _format_money_placeholder(value: float) -> str:
        return f"{Decimal(str(value)).quantize(Decimal('0.01')):.2f}"

    @property
    def shipping_amount_placeholder(self) -> str:
        raw = self["shipping_amount"].value()
        if raw in (None, ""):
            raw = self.order.shipping_amount
        return self._format_money_placeholder(float(raw))

    def clean_shipping_method_code(self):
        code = self.cleaned_data["shipping_method_code"]
        method = ShippingMethodService().resolve_method_for_customer(
            customer=self.order.customer,
            shipping_method_code=code,
        )
        return method.code

    def clean(self):
        cleaned = super().clean()
        if self.group_dtf and "dtf_group_linear_m" in cleaned:
            linear = cleaned["dtf_group_linear_m"]
            cleaned["dtf_group_quantity"] = sqm_from_linear_meters(linear)
        return cleaned

    @staticmethod
    def _distribute_quantity(*, total: Decimal, weights: list[Decimal]) -> list[Decimal]:
        if not weights:
            return []
        weight_sum = sum(weights, Decimal("0"))
        if weight_sum <= 0:
            share = (total / Decimal(len(weights))).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
            parts = [share for _ in weights]
            parts[-1] = (total - sum(parts[:-1], Decimal("0"))).quantize(
                FOURPLACES, rounding=ROUND_HALF_UP
            )
            return parts
        parts: list[Decimal] = []
        allocated = Decimal("0")
        for index, weight in enumerate(weights):
            if index == len(weights) - 1:
                parts.append((total - allocated).quantize(FOURPLACES, rounding=ROUND_HALF_UP))
            else:
                part = (total * weight / weight_sum).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
                parts.append(part)
                allocated += part
        return parts

    def line_adjustments(self) -> list[dict]:
        cleaned = self.cleaned_data
        adjustments: list[dict] = []
        if self.group_dtf:
            total_qty = cleaned["dtf_group_quantity"]
            unit_price = cleaned["dtf_group_unit_price"]
            weights = [line.quantity for line in self.dtf_lines]
            quantities = self._distribute_quantity(total=total_qty, weights=weights)
            for line, quantity in zip(self.dtf_lines, quantities, strict=True):
                adjustments.append(
                    {
                        "line_public_id": str(line.public_id),
                        "quantity": quantity,
                        "unit_price": unit_price,
                    }
                )
            for line in self.other_lines:
                adjustments.append(
                    {
                        "line_public_id": str(line.public_id),
                        "quantity": cleaned[f"line_{line.public_id}_quantity"],
                        "unit_price": cleaned[f"line_{line.public_id}_unit_price"],
                    }
                )
            return adjustments
        return [
            {
                "line_public_id": str(row["line"].public_id),
                "quantity": cleaned[row["quantity_name"]],
                "unit_price": cleaned[row["unit_price_name"]],
            }
            for row in self.line_rows
        ]
