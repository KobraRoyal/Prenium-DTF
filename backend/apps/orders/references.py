from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist


def order_client_reference(order) -> str:
    """Libellé saisi par le client (nom de préparation ou 1re ligne de note)."""
    try:
        project = order.source_b2b_order_project
    except ObjectDoesNotExist:
        project = None

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
