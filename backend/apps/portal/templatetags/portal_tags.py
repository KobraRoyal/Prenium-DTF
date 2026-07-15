from django import template
from django.urls import reverse

from apps.accounts.services.access import AccessScopeService
from apps.core.public_refs import short_public_ref
from apps.orders.references import order_client_reference, project_client_reference

register = template.Library()
access_scope_service = AccessScopeService()

STATUS_LABELS = {
    "draft": "Brouillon",
    "submitted": "Soumise",
    "immediate": "Paiement immédiat",
    "deferred": "Facturation différée",
    "pending": "En attente",
    "priced": "Prix calculé",
    "failed": "Échec calcul",
    "none": "N/A",
    "clear": "Encours OK",
    "approved": "Approuvee",
    "captured": "Capturee",
    "cancelled": "Annulee",
    "queued": "En file atelier",
    "in_progress": "En production",
    "ready_to_ship": "Prete a expedier",
    "completed": "Terminee",
    "blocked": "Bloquee",
    "resolve": "Lecture OF",
    "transition": "Transition OF",
    "created": "Creee",
    "issued": "Emise",
    "void": "Annulee",
    "ok": "Valide",
    "warning": "A verifier",
    "error": "Erreur",
    "synced": "Synchronise",
}


@register.simple_tag(takes_context=True)
def brand_home_url(context) -> str:
    user = context["request"].user
    url_name = access_scope_service.resolve_brand_home_url_name(user)
    return reverse(url_name)


@register.filter
def badge_tone(status):
    status = str(status)
    positive = {
        "ok",
        "synced",
        "created",
        "completed",
        "ready_to_ship",
        "submitted",
        "priced",
        "clear",
        "ready_to_submit",
        "confirmed",
        "converted",
    }
    warning = {
        "warning",
        "pending",
        "queued",
        "in_progress",
        "incomplete",
        "analyzing",
        "action_required",
        "changes_requested",
        "price_confirmation_required",
        "under_review",
    }
    negative = {"error", "failed", "blocked", "draft"}
    if status in positive:
        return "is-success"
    if status in warning:
        return "is-warning"
    if status in negative:
        return "is-danger"
    return "is-neutral"


@register.filter
def human_status(status):
    value = str(status)
    return STATUS_LABELS.get(value, value.replace("_", " ").capitalize())


@register.filter
def short_ref(value):
    return short_public_ref(value)


@register.filter
def order_client_ref(order):
    return order_client_reference(order)


@register.filter
def project_client_ref(project):
    return project_client_reference(project)


CLIENT_ORDER_PANEL_LABELS = {
    "uploads": "Visuels",
    "production": "Avancement",
    "shipping": "Expédition",
    "billing": "Facture",
}


@register.filter
def client_order_panel_label(panel_slug):
    return CLIENT_ORDER_PANEL_LABELS.get(str(panel_slug or "").strip(), "Détail")


@register.inclusion_tag("components/portal/client_refs.html")
def client_order_refs(order, variant="row"):
    return {
        "ids_value": short_public_ref(order.public_id),
        "client_value": order_client_reference(order),
        "variant": variant,
        "mono_ids": True,
    }


@register.inclusion_tag("components/portal/client_refs.html")
def client_project_refs(project, variant="row"):
    return {
        "ids_value": project.project_number,
        "client_value": project_client_reference(project),
        "variant": variant,
        "mono_ids": False,
    }

