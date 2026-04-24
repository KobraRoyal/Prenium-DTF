from django import template

register = template.Library()

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
    }
    warning = {"warning", "pending", "queued", "in_progress"}
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
