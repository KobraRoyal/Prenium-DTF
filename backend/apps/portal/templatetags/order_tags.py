from django import template
from django.urls import reverse

register = template.Library()

_STAFF_COPY = (
    "Workflow commande",
    "Préparation des fichiers et contrôle, pilotage atelier, puis expédition "
    "et facturation. Chaque zone regroupe les écrans utiles à l’étape.",
)

_CLIENT_COPY = (
    "Tunnel de commande",
    "Naviguez entre les étapes et suivez le statut en temps réel.",
)

_STAFF_GROUP_LABELS = ("Préparation", "Atelier", "Clôture")
_CLIENT_GROUP_LABELS = ("Préparation", "Atelier", "Clôture")


def _mark_tab_groups(tabs: list[dict]) -> None:
    prev = None
    for tab in tabs:
        g = tab.get("group")
        tab["group_start"] = prev is None or g != prev
        prev = g


def _build_tab_groups(tabs: list[dict], group_labels: tuple[str, ...]) -> list[dict]:
    buckets: dict[int, list] = {1: [], 2: [], 3: []}
    for t in tabs:
        g = int(t.get("group") or 1)
        if g in buckets:
            buckets[g].append(t)
    out = []
    for idx, label in enumerate(group_labels, start=1):
        if buckets.get(idx):
            out.append({"label": label, "tabs": buckets[idx]})
    return out


@register.inclusion_tag("components/order/order_tabs.html", takes_context=True)
def order_htmx_tabs(context, variant):
    variant = (variant or "staff").lower()
    order = context["order"]
    request = context.get("request")

    if variant == "staff":
        title, subtitle = _STAFF_COPY
        panel_id = "staff-order-panel"
        oid = order.public_id
        tabs = [
            {
                "label": "Fichiers",
                "url": reverse(
                    "portal:staff-order-panel-uploads",
                    kwargs={"order_public_id": oid},
                ),
                "icon": "uploads",
                "group": 1,
                "permission": "uploads.view_orderupload",
            },
            {
                "label": "Contrôle",
                "url": reverse(
                    "portal:staff-order-panel-inspection",
                    kwargs={"order_public_id": oid},
                ),
                "icon": "inspection",
                "group": 1,
                "permission": "uploads.view_orderuploadinspection",
            },
            {
                "label": "Drive",
                "url": reverse(
                    "portal:staff-order-panel-drive-sync",
                    kwargs={"order_public_id": oid},
                ),
                "icon": "drive",
                "group": 1,
                "permission": "uploads.view_orderuploaddrivesync",
            },
            {
                "label": "Production",
                "url": reverse(
                    "portal:staff-order-panel-production",
                    kwargs={"order_public_id": oid},
                ),
                "icon": "production",
                "group": 2,
                "permission": "production.view_productionjob",
            },
            {
                "label": "Scan atelier",
                "url": reverse(
                    "portal:staff-order-panel-scan",
                    kwargs={"order_public_id": oid},
                ),
                "icon": "scan",
                "group": 2,
                "permission": "production.scan_productionjob",
            },
            {
                "label": "Expédition",
                "url": reverse(
                    "portal:staff-order-panel-shipping",
                    kwargs={"order_public_id": oid},
                ),
                "icon": "shipping",
                "group": 3,
                "permission": "shipping.view_shipment",
            },
            {
                "label": "Facturation",
                "url": reverse(
                    "portal:staff-order-panel-billing",
                    kwargs={"order_public_id": oid},
                ),
                "icon": "billing",
                "group": 3,
                "permission": "billing.view_invoice",
            },
        ]
        if request is not None:
            tabs = [tab for tab in tabs if request.user.has_perm(tab["permission"])]
        _mark_tab_groups(tabs)
        tab_groups = _build_tab_groups(tabs, _STAFF_GROUP_LABELS)
    elif variant == "client":
        title, subtitle = _CLIENT_COPY
        panel_id = "client-order-panel"
        customer = context["customer"]
        cid = customer.public_id
        oid = order.public_id
        tabs = [
            {
                "label": "Fichiers",
                "url": reverse(
                    "portal:client-order-panel-uploads",
                    kwargs={
                        "customer_public_id": cid,
                        "order_public_id": oid,
                    },
                ),
                "icon": "uploads",
                "group": 1,
            },
            {
                "label": "Contrôle",
                "url": reverse(
                    "portal:client-order-panel-inspection",
                    kwargs={
                        "customer_public_id": cid,
                        "order_public_id": oid,
                    },
                ),
                "icon": "inspection",
                "group": 1,
            },
            {
                "label": "Production",
                "url": reverse(
                    "portal:client-order-panel-production",
                    kwargs={
                        "customer_public_id": cid,
                        "order_public_id": oid,
                    },
                ),
                "icon": "production",
                "group": 2,
            },
            {
                "label": "Expédition",
                "url": reverse(
                    "portal:client-order-panel-shipping",
                    kwargs={
                        "customer_public_id": cid,
                        "order_public_id": oid,
                    },
                ),
                "icon": "shipping",
                "group": 3,
            },
            {
                "label": "Facturation",
                "url": reverse(
                    "portal:client-order-panel-billing",
                    kwargs={
                        "customer_public_id": cid,
                        "order_public_id": oid,
                    },
                ),
                "icon": "billing",
                "group": 3,
            },
        ]
        _mark_tab_groups(tabs)
        tab_groups = _build_tab_groups(tabs, _CLIENT_GROUP_LABELS)
    else:
        raise ValueError("variant must be 'staff' or 'client'")

    flat_tabs = [t for g in tab_groups for t in g["tabs"]]
    for i, tab in enumerate(flat_tabs):
        tab["active"] = i == 0

    return {
        "title": title,
        "subtitle": subtitle,
        "tabs": flat_tabs,
        "tab_groups": tab_groups,
        "panel_id": panel_id,
        "hx_target": f"#{panel_id}",
        "initial_url": flat_tabs[0]["url"] if flat_tabs else None,
        "empty_message": (
            "Aucun panneau disponible avec vos permissions actuelles." if not flat_tabs else None
        ),
    }
