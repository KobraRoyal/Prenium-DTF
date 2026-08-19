from __future__ import annotations

import re
from collections.abc import Mapping

from django.db import transaction

from apps.auditlog.services import record_event
from apps.customers.models import VolumeDiscountDashboardCopy

COPY_FIELDS = (
    "start_immediate",
    "start_deferred",
    "warm_immediate",
    "warm_deferred",
    "hold_immediate",
    "hold_deferred",
    "hot_immediate",
    "hot_deferred",
    "max_immediate",
    "max_deferred",
)

TOKEN_KEYS = frozenset(
    {
        "remaining_m",
        "next_percent",
        "current_percent",
        "volume_m",
        "threshold_m",
    }
)

DEFAULT_NUDGE_COPY = {
    "start_immediate": "Le palier s’applique à cette commande, sans rétroactivité.",
    "start_deferred": "Le palier s’applique à tout le DTF du mois.",
    "warm_immediate": "Le palier s’accroche à la commande qui le franchit.",
    "warm_deferred": "Tout le DTF du mois suivra le palier.",
    "hold_immediate": "Le taux actuel est figé commande par commande.",
    "hold_deferred": "Le taux actuel s’applique déjà à tout le mois.",
    "hot_immediate": "Le prochain palier s’applique à la commande qui le franchit.",
    "hot_deferred": "Le prochain palier s’appliquera à tout le DTF du mois.",
    "max_immediate": "Meilleur taux du mois, commande par commande.",
    "max_deferred": "Meilleur taux du mois, sur tout le DTF encours.",
}

NUDGE_COPY_STAGES = (
    (
        "start",
        "Compteur à zéro",
        "Aucune planche comptée ce mois-ci.",
    ),
    (
        "warm",
        "En route",
        "Des mètres déjà au compteur, pas encore de palier.",
    ),
    (
        "hold",
        "Palier en poche",
        "Un taux est déjà gagné, le suivant attend.",
    ),
    (
        "hot",
        "Tout proche",
        "Plus de 75 % du prochain seuil.",
    ),
    (
        "max",
        "Palier max",
        "Meilleur taux du mois atteint.",
    ),
)

_TOKEN_RE = re.compile(r"\{([a-z_]+)\}")


def field_name_for(*, stage: str, audience: str) -> str:
    return f"{stage}_{audience}"


def interpolate_nudge_copy(template: str, tokens: Mapping[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in TOKEN_KEYS:
            return str(tokens.get(key, ""))
        return match.group(0)

    return _TOKEN_RE.sub(replace, template or "")


def resolve_nudge_template(*, stage: str, audience: str, stored: Mapping[str, str] | None) -> str:
    field = field_name_for(stage=stage, audience=audience)
    custom = str((stored or {}).get(field) or "").strip()
    if custom:
        return custom
    return DEFAULT_NUDGE_COPY[field]


def render_nudge_message(
    *,
    stage: str,
    audience: str,
    tokens: Mapping[str, str],
    stored: Mapping[str, str] | None = None,
) -> str:
    template = resolve_nudge_template(stage=stage, audience=audience, stored=stored)
    return interpolate_nudge_copy(template, tokens).strip()


class VolumeDiscountDashboardCopyService:
    """Lecture et mise à jour auditées des messages dashboard (singleton)."""

    def stored_messages(self) -> dict[str, str]:
        row = VolumeDiscountDashboardCopy.objects.filter(singleton=True).first()
        if row is None:
            return {}
        return {field: getattr(row, field).strip() for field in COPY_FIELDS}

    def render_message(self, *, stage: str, audience: str, tokens: Mapping[str, str]) -> str:
        return render_nudge_message(
            stage=stage,
            audience=audience,
            tokens=tokens,
            stored=self.stored_messages(),
        )

    @transaction.atomic
    def update(self, *, cleaned_data: dict, actor, source: str) -> VolumeDiscountDashboardCopy:
        row, _created = VolumeDiscountDashboardCopy.objects.select_for_update().get_or_create(
            singleton=True
        )
        before = {field: getattr(row, field) for field in COPY_FIELDS}
        for field in COPY_FIELDS:
            setattr(row, field, str(cleaned_data.get(field) or "").strip())
        row.save(update_fields=[*COPY_FIELDS, "updated_at"])
        changes = {
            field: {"before": before[field], "after": getattr(row, field)}
            for field in COPY_FIELDS
            if before[field] != getattr(row, field)
        }
        record_event(
            action="customer.volume_discount_dashboard_copy_updated",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=row,
            metadata={"source": source, "changes": changes},
        )
        return row

    @transaction.atomic
    def restore_defaults(self, *, actor, source: str) -> VolumeDiscountDashboardCopy:
        empty = dict.fromkeys(COPY_FIELDS, "")
        return self.update(cleaned_data=empty, actor=actor, source=source)
