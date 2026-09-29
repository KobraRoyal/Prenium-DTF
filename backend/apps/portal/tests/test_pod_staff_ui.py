from pathlib import Path

import pytest
from django.urls import reverse

from tests.pod.test_catalog_and_warehouse import MANAGE, VIEW, pod_demo, staff_client

ROOT = Path(__file__).resolve().parents[4]
TEMPLATES = ROOT / "backend" / "templates" / "portal" / "staff" / "pod"
STAFF_CSS = ROOT / "backend" / "static_src" / "css" / "entries" / "portal-staff.css"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_pod_hub_mobile_and_drawer_accessibility_contracts():
    hub = _source(TEMPLATES / "hub.html")
    catalogue = _source(TEMPLATES / "catalogue.html")
    catalogue_product = _source(TEMPLATES / "catalogue_product.html")
    drawer_host = _source(TEMPLATES / "_variant_drawer_host.html")
    drawer = _source(TEMPLATES / "_variant_config_drawer.html")
    css = _source(STAFF_CSS)

    assert "pod-table-shell" in hub
    assert "rememberDrawerTrigger" in hub
    assert hub.index('x-data="{') < hub.index('class="pod-board')
    assert "p.showModal()" in drawer_host
    assert "_variant_drawer_host.html" in hub
    assert "_variant_drawer_host.html" in catalogue
    assert "_variant_drawer_host.html" in catalogue_product
    assert "rememberDrawerTrigger" in catalogue
    assert "rememberDrawerTrigger" in catalogue_product
    assert 'aria-haspopup="dialog"' in catalogue
    assert 'aria-haspopup="dialog"' in catalogue_product
    assert "trapDrawerFocus($event)" in drawer
    assert "lastDrawerTrigger.focus" in hub
    assert '@click.self="closeDrawer()"' in drawer_host
    assert 'aria-haspopup="dialog"' in hub
    assert 'aria-modal="true"' in drawer
    assert ".pod-board-surface .ui-table-shell" in css
    assert "pod-next-action" in hub
    assert 'id="pod-board-mapping"' in hub
    assert "?queue=blocked" in hub
    pick_workflow = _source(TEMPLATES / "_pick_workflow.html")
    assert 'id="pod-pick-workflow"' in pick_workflow
    assert "_pick_workflow.html" in hub
    assert hub.count("_pick_workflow.html") == 2  # avant file si reserved, sinon après
    assert 'id="pod-pick-scan"' in pick_workflow
    assert "pod-pick-session-rail" in pick_workflow
    assert "Valider sortie" in pick_workflow
    assert "Préparer lot DTF" in pick_workflow
    assert "_pod_operate_rail.html" in pick_workflow
    assert "Suivi impression" in pick_workflow
    assert "staff-pod-rip-lots" not in pick_workflow
    operate_rail = _source(TEMPLATES / "_pod_operate_rail.html")
    assert "confirm_dtf_print" in operate_rail
    assert ".pod-pick-scan-row" in css
    assert ".pod-qty-form" in css
    assert "pod-board-command__actions" in hub
    assert "pod-board-command--idle" in hub
    assert "pickable_count" in hub
    assert "à préparer" in hub
    assert ".pod-board-command--idle" in css
    assert ".pod-board-surface {" in css
    assert "grid-template-columns: minmax(0, 1fr) !important" in css
    assert "overscroll-behavior-inline: contain" in css
    assert "width: min(42rem, calc(100vw - 1rem))" in css
    assert "max-width: 42rem" in css


def test_pod_lots_page_routes_prepare_via_hub():
    lots = _source(TEMPLATES / "rip_lots.html")
    assert "Préparer depuis À produire" in lots
    assert "Préparer toute la file" not in lots
    assert "diagnostic" in lots.lower()
    assert "?enqueue=1" in lots


def test_pod_stock_tabs_expose_keyboard_loading_and_panel_contracts():
    stock = _source(TEMPLATES / "stock.html")

    assert 'role="tablist"' in stock
    assert '@keydown.right.prevent="moveTab($event, 1)"' in stock
    assert 'aria-controls="stock-panel-pick"' in stock
    assert 'role="tabpanel"' in stock
    assert ':aria-busy="submitting"' in stock
    assert ':disabled="submitting"' in stock


@pytest.mark.django_db
def test_operator_navigation_exposes_production_without_settings():
    _actor, client = staff_client(email="pod-nav-operator@example.com", permissions=VIEW)
    response = client.get(reverse("portal:staff-pod-hub"))
    assert response.status_code == 200
    body = response.content.decode()
    assert 'aria-label="Production POD"' in body
    assert "Réglages POD" not in body
    assert reverse("portal:staff-pod-catalog") not in body
    assert reverse("portal:staff-pod-stock") not in body
    rail = body.split('class="pod-workspace-nav__pages"', 1)[1].split("</div>", 1)[0]
    assert (
        rail.index("Suivi")
        < rail.index("À produire")
        < rail.index(">Pose<")
        < rail.index("Contrôle qualité")
    )
    assert "Lots RIP" not in rail
    assert reverse("portal:staff-pod-suivi") in body


@pytest.mark.django_db
def test_operator_mapping_blocker_does_not_offer_configuration():
    from django.utils import timezone

    from apps.pod.models import (
        IdsVariantConfig,
        PodPickSessionLine,
        PodRipWorkItem,
        PodUnit,
        ShopifyVariant,
    )

    actor, manager = staff_client(
        email="pod-nav-manager@example.com", permissions=(*MANAGE, "view_customer")
    )
    pod_demo.ensure_ready(actor=actor)
    # Isoler le cas mapping : neutraliser picking/pose/QC du seed pipeline.
    PodUnit.objects.all().delete()
    PodPickSessionLine.objects.filter(voided_at__isnull=True).update(voided_at=timezone.now())
    PodRipWorkItem.objects.exclude(shopify_order_number="SO-SEED-QUEUE").update(
        status=PodRipWorkItem.Status.CANCELLED
    )
    variant = ShopifyVariant.objects.get(sku="TEE-BLK-M")
    IdsVariantConfig.objects.update_or_create(
        variant=variant, defaults={"mode": IdsVariantConfig.Mode.UNMANAGED}
    )
    _operator, client = staff_client(email="pod-nav-blocked@example.com", permissions=VIEW)
    body = client.get(reverse("portal:staff-pod-hub")).content.decode()
    assert "Voir les blocages" in body
    assert "À traiter par un responsable" in body
    assert 'aria-label="Configurer le mapping' not in body


@pytest.mark.django_db
def test_nested_pod_settings_keep_one_active_navigation_destination():
    from apps.portal.pod_navigation import navigation_for

    actor, _client = staff_client(email="pod-nav-active@example.com", permissions=MANAGE)
    nav = navigation_for(actor, "staff-pod-catalog-product")
    assert nav["in_settings"]
    active = [entry for entry in nav["entries"] if entry["active"]]
    assert [entry["label"] for entry in active] == ["Catalogue & mapping"]
    assert all(entry["label"] != "Pose" for entry in nav["entries"])


@pytest.mark.django_db
def test_invalid_stock_pick_keeps_pick_tab_visible():
    _actor, client = staff_client(email="staff-pod-ui@example.com", permissions=MANAGE)

    response = client.post(
        reverse("portal:staff-pod-stock"),
        {"intent": "pick", "quantity": "not-a-number"},
    )

    assert response.status_code == 400
    body = response.content.decode()
    assert "Quantité invalide." in body
    assert "tab: 'pick'" in body
