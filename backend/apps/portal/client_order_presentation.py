from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClientOrderStatusBanner:
    tone: str
    message: str
    show_pay_cta: bool


def client_order_status_banner(
    *,
    awaits_client_payment: bool,
    query_params: Mapping[str, str],
) -> ClientOrderStatusBanner | None:
    paid = query_params.get("paid") == "1"
    cancelled = query_params.get("cancelled") == "1"
    checkout_success = query_params.get("checkout") == "success"

    if paid:
        return ClientOrderStatusBanner(
            tone="success",
            message="Paiement confirmé. Le justificatif est dans Règlement.",
            show_pay_cta=False,
        )
    if cancelled:
        return ClientOrderStatusBanner(
            tone="warning",
            message="Paiement non finalisé.",
            show_pay_cta=True,
        )
    if checkout_success and awaits_client_payment:
        return ClientOrderStatusBanner(
            tone="warning",
            message="Commande enregistrée — paiement non finalisé.",
            show_pay_cta=True,
        )
    if checkout_success:
        return ClientOrderStatusBanner(
            tone="success",
            message="Commande transmise.",
            show_pay_cta=False,
        )
    if awaits_client_payment:
        return ClientOrderStatusBanner(
            tone="warning",
            message="Cette commande attend votre paiement.",
            show_pay_cta=True,
        )
    return None
