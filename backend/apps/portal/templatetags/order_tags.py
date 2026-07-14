from django import template
from django.urls import reverse

register = template.Library()


def _panel_url(request, slug: str) -> str | None:
    if request is None:
        return None
    query = request.GET.copy()
    query["panel"] = slug
    return f"{request.path}?{query.urlencode()}"


def _finalize_tab_state(
    tab_groups: list[dict], panel_id: str, request, *, default_panel: str | None = None
) -> list[dict]:
    flat_tabs = [t for g in tab_groups for t in g["tabs"]]
    requested_panel = request.GET.get("panel") if request is not None else None
    selected_panel = requested_panel or default_panel
    active_index = 0

    for index, tab in enumerate(flat_tabs):
        if tab.get("slug") == selected_panel:
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
        panel_id = "staff-order-panel"
        oid = order.public_id
        tabs = [
            {
                "slug": "inspection",
                "label": "Contrôle",
                "caption": "Valider les fichiers",
                "url": reverse(
                    "portal:staff-order-panel-inspection",
                    kwargs={"order_public_id": oid},
                ),
                "permission": "uploads.view_orderuploadinspection",
            },
            {
                "slug": "production",
                "label": "Production",
                "caption": "Fabriquer l'OF",
                "url": reverse(
                    "portal:staff-order-panel-production",
                    kwargs={"order_public_id": oid},
                ),
                "permission": "production.view_productionjob",
            },
            {
                "slug": "scan",
                "label": "Scan atelier",
                "caption": "Tracer l'avancement",
                "url": reverse(
                    "portal:staff-order-panel-scan",
                    kwargs={"order_public_id": oid},
                ),
                "permission": "production.scan_productionjob",
            },
            {
                "slug": "shipping",
                "label": "Expédition",
                "caption": "Créer et suivre l'envoi",
                "url": reverse(
                    "portal:staff-order-panel-shipping",
                    kwargs={"order_public_id": oid},
                ),
                "permission": "shipping.view_shipment",
            },
            {
                "slug": "billing",
                "label": "Facturation",
                "caption": "Clôturer la commande",
                "url": reverse(
                    "portal:staff-order-panel-billing",
                    kwargs={"order_public_id": oid},
                ),
                "permission": "billing.view_invoice",
            },
        ]
        focus = context.get("staff_order_focus") or {}
        if focus.get("has_drive_issues"):
            tabs.insert(
                1,
                {
                    "slug": "drive",
                    "label": "Incident Drive",
                    "caption": "Résoudre la synchronisation",
                    "url": reverse(
                        "portal:staff-order-panel-drive-sync",
                        kwargs={"order_public_id": oid},
                    ),
                    "permission": "uploads.view_orderuploaddrivesync",
                },
            )
        if request is not None:
            tabs = [tab for tab in tabs if request.user.has_perm(tab["permission"])]
        for step_number, tab in enumerate(tabs, start=1):
            tab["step_number"] = step_number
        tab_groups = [{"label": "", "tabs": tabs}]
        flat_tabs = _finalize_tab_state(
            tab_groups,
            panel_id,
            request,
            default_panel=focus.get("next_panel"),
        )
        active_tab = next((tab for tab in flat_tabs if tab["active"]), None)
    elif variant == "client":
        panel_id = "client-order-panel"
        customer = context["customer"]
        cid = customer.public_id
        oid = order.public_id
        membership = context.get("customer_membership")
        is_owner = membership is not None and membership.is_owner
        tabs = [
            {
                "slug": "uploads",
                "label": "Visuels",
                "url": reverse(
                    "portal:client-order-panel-uploads",
                    kwargs={
                        "customer_public_id": cid,
                        "order_public_id": oid,
                    },
                ),
                "group": 1,
            },
            {
                "slug": "production",
                "label": "Avancement",
                "url": reverse(
                    "portal:client-order-panel-production",
                    kwargs={
                        "customer_public_id": cid,
                        "order_public_id": oid,
                    },
                ),
                "group": 1,
            },
        ]
        if is_owner:
            tabs.extend(
                [
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
                        "group": 1,
                    },
                    {
                        "slug": "billing",
                        "label": "Facture",
                        "url": reverse(
                            "portal:client-order-panel-billing",
                            kwargs={
                                "customer_public_id": cid,
                                "order_public_id": oid,
                            },
                        ),
                        "group": 1,
                    },
                ]
            )
        tab_groups = [{"label": "", "tabs": tabs}]
        flat_tabs = _finalize_tab_state(tab_groups, panel_id, request)
        if (
            not is_owner
            and request is not None
            and request.GET.get("panel") in {"shipping", "billing"}
        ):
            for tab in flat_tabs:
                tab["active"] = tab.get("slug") == "uploads"
            if flat_tabs:
                active_tab = next((tab for tab in flat_tabs if tab["active"]), flat_tabs[0])
            else:
                active_tab = None
        else:
            active_tab = next((tab for tab in flat_tabs if tab["active"]), None)
    else:
        raise ValueError("variant must be 'staff' or 'client'")

    return {
        "compact": variant == "client",
        "tablist_label": "Étapes de la commande" if variant == "staff" else "Suivi commande",
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
