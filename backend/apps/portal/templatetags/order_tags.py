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


def _panel_url(request, slug: str) -> str | None:
    if request is None:
        return None
    query = request.GET.copy()
    query["panel"] = slug
    return f"{request.path}?{query.urlencode()}"


def _finalize_tab_state(tab_groups: list[dict], panel_id: str, request) -> list[dict]:
    flat_tabs = [t for g in tab_groups for t in g["tabs"]]
    requested_panel = request.GET.get("panel") if request is not None else None
    active_index = 0

    for index, tab in enumerate(flat_tabs):
        if tab.get("slug") == requested_panel:
            active_index = index
            break

    for group_index, group in enumerate(tab_groups, start=1):
        for tab_index, tab in enumerate(group["tabs"], start=1):
            tab["dom_id"] = f"{panel_id}-tab-{group_index}-{tab_index}"
            tab["push_url"] = _panel_url(request, tab["slug"])

    for index, tab in enumerate(flat_tabs):
        tab["active"] = index == active_index

    return flat_tabs


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
                "slug": "uploads",
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
                "slug": "inspection",
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
                "slug": "drive",
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
                "slug": "production",
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
                "slug": "scan",
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
                "slug": "shipping",
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
                "slug": "billing",
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
        flat_tabs = _finalize_tab_state(tab_groups, panel_id, request)
    elif variant == "client":
        title, subtitle = _CLIENT_COPY
        panel_id = "client-order-panel"
        customer = context["customer"]
        cid = customer.public_id
        oid = order.public_id
        tabs = [
            {
                "slug": "uploads",
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
                "slug": "inspection",
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
                "slug": "production",
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
                "slug": "shipping",
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
                "slug": "billing",
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
        flat_tabs = _finalize_tab_state(tab_groups, panel_id, request)
    else:
        raise ValueError("variant must be 'staff' or 'client'")

    active_tab = next((tab for tab in flat_tabs if tab["active"]), None)

    return {
        "title": title,
        "subtitle": subtitle,
        "tabs": flat_tabs,
        "tab_groups": tab_groups,
        "panel_id": panel_id,
        "hx_target": f"#{panel_id}",
        "initial_url": active_tab["url"] if active_tab else None,
        "active_tab_id": active_tab["dom_id"] if active_tab else None,
        "empty_message": (
            "Aucun panneau disponible avec vos permissions actuelles." if not flat_tabs else None
        ),
    }
