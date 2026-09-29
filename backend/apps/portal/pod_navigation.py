"""Shared navigation vocabulary for POD production and configuration screens."""

from django.urls import reverse

PRODUCTION_ENTRIES = (
    ("Suivi", "Suivi", "staff-pod-suivi", ()),
    ("À produire", "À produire", "staff-pod-hub", ("staff-pod-pick-session-pdf",)),
    ("Pose", "Pose", "staff-pod-pose-dtf", ()),
    ("Contrôle qualité", "Qualité", "staff-pod-qc", ()),
)
SETTINGS_ENTRIES = (
    ("Vue d’ensemble", "Vue d’ensemble", "staff-pod-settings", (), None),
    ("Boutiques", "Boutiques", "staff-pod-shops", (), "pod.manage_pod_catalog"),
    (
        "Catalogue & mapping",
        "Catalogue",
        "staff-pod-catalog",
        ("staff-pod-catalog-product", "staff-pod-variant-config"),
        "pod.manage_pod_catalog",
    ),
    (
        "Supports",
        "Supports",
        "staff-pod-blanks",
        ("staff-pod-blank-detail", "staff-pod-blank-photo", "staff-pod-blank-variant-photo"),
        "pod.manage_pod_catalog",
    ),
    ("Techniques", "Techniques", "staff-pod-techniques", (), "pod.manage_pod_catalog"),
    (
        "Emplacements",
        "Emplacements",
        "staff-pod-warehouse",
        ("staff-pod-location-detail",),
        "inventory.manage_warehouse",
    ),
    (
        "Lots RIP (diagnostic)",
        "Lots RIP",
        "staff-pod-rip-lots",
        ("staff-pod-rip-lot-detail", "staff-pod-unit-document"),
        "pod.operate_pod_production",
    ),
)


def navigation_for(user, url_name: str) -> dict:
    can_settings = user.has_perm("pod.manage_pod_catalog") or user.has_perm(
        "inventory.manage_warehouse"
    )
    settings_routes = {route for entry in SETTINGS_ENTRIES for route in (entry[2], *entry[3])}
    in_settings = url_name in settings_routes
    entries = []
    for entry in SETTINGS_ENTRIES if in_settings else PRODUCTION_ENTRIES:
        label, short_label, route, aliases = entry[:4]
        if len(entry) == 5 and entry[4] and not user.has_perm(entry[4]):
            continue
        entries.append(
            {
                "label": label,
                "short_label": short_label,
                "url": reverse(f"portal:{route}"),
                "active": url_name in (route, *aliases),
            }
        )
    return {
        "entries": entries,
        "in_settings": in_settings,
        "can_settings": can_settings,
        "can_stock": user.has_perm("inventory.manage_warehouse"),
        "stock_active": url_name == "staff-pod-stock",
    }
