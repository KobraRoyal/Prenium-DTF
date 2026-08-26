from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist

from apps.core.public_refs import short_public_ref


def _source_project(order):
    try:
        return order.source_b2b_order_project
    except ObjectDoesNotExist:
        return None


def order_business_number(order) -> str:
    """N° métier visible (CMD-YYYY-NNNNNN), jamais l’UUID."""
    project = _source_project(order)
    if project is None:
        return ""
    return str(project.project_number or "").strip()


def order_uuid_short(order) -> str:
    """Identifiant technique court dérivé du public_id (vues Atelier uniquement)."""
    return short_public_ref(getattr(order, "public_id", None))


def order_client_reference(order) -> str:
    """Libellé saisi par le client (nom de préparation ou 1re ligne de note)."""
    project = _source_project(order)
    if project is not None:
        if project.name.strip():
            return project.name.strip()
        if project.customer_reference.strip():
            return project.customer_reference.strip()

    note = (order.customer_note or "").strip()
    if note:
        return note.splitlines()[0].strip()
    return ""


def project_client_reference(project) -> str:
    if project.name.strip():
        return project.name.strip()
    if project.customer_reference.strip():
        return project.customer_reference.strip()
    return ""
