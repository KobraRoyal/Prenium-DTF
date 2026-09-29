from pathlib import Path

import pytest
from django.urls import reverse

from apps.inventory.models import StockBalance, StockMovement, StorageLocation
from apps.pod.models import Blank, PodRipWorkItem, ShopifyProduct
from tests.pod.test_catalog_and_warehouse import MANAGE, pod_demo, staff_client

TEMPLATES = Path(__file__).resolve().parents[4] / "backend/templates/portal/staff/pod"


def test_blank_defines_possibilities_not_hd_recipe_or_new_required_marks():
    source = (TEMPLATES / "_blank_marking_options.html").read_text()
    assert "Zones et techniques possibles" in source
    assert "Toutes ses variantes en héritent automatiquement" in source
    assert 'name="zone_public_ids"' in source
    assert 'name="technique_public_ids"' in source
    assert "Deux listes indépendantes" in source
    assert 'name="is_required"' not in source
    assert 'name="slot_source_asset_version_public_id"' not in source
    assert 'name="capability_public_id"' not in source


def test_every_pod_page_uses_the_shared_workspace_and_navigation():
    pages = (
        "hub",
        "settings",
        "blanks",
        "blank_detail",
        "techniques",
        "warehouse",
        "location_detail",
        "shops",
        "catalogue",
        "catalogue_product",
        "stock",
        "rip_lots",
        "rip_lot_detail",
        "pose_dtf",
        "qc",
    )
    for page in pages:
        source = (TEMPLATES / f"{page}.html").read_text()
        assert "pod-page" in source, page
        assert "_pod_context_nav.html" in source, page
        assert "page_head.html" in source, page
    for page in ("blanks", "techniques", "warehouse", "blank_detail", "location_detail"):
        source = (TEMPLATES / f"{page}.html").read_text()
        assert "pod-editor" in source, page
        assert "_editor_actions.html" in source, page
        assert "data-inline-required" in source, page
        assert "data-submit-loading" in source, page


@pytest.mark.django_db
def test_all_pod_main_and_reference_pages_render_without_writes(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, client = staff_client(
        email="crud-render@example.com", permissions=(*MANAGE, "view_customer")
    )
    pod_demo.ensure_ready(actor=actor)
    blank = Blank.objects.first()
    product = ShopifyProduct.objects.first()
    location = StorageLocation.objects.first()
    urls = [
        reverse(f"portal:staff-pod-{name}")
        for name in (
            "hub",
            "settings",
            "techniques",
            "blanks",
            "warehouse",
            "shops",
            "catalog",
            "stock",
            "rip-lots",
            "pose-dtf",
            "qc",
        )
    ]
    urls.extend(
        (
            reverse("portal:staff-pod-blank-detail", kwargs={"blank_public_id": blank.public_id}),
            reverse(
                "portal:staff-pod-catalog-product", kwargs={"product_public_id": product.public_id}
            ),
            reverse(
                "portal:staff-pod-location-detail",
                kwargs={"location_public_id": location.public_id},
            ),
        )
    )
    counts = [
        model.objects.count() for model in (Blank, StockBalance, StockMovement, PodRipWorkItem)
    ]
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, url
        assert "pod-page" in response.content.decode(), url
    assert counts == [
        model.objects.count() for model in (Blank, StockBalance, StockMovement, PodRipWorkItem)
    ]


@pytest.mark.django_db
def test_unknown_operational_intents_are_rejected_without_mutations():
    _actor, client = staff_client(email="crud-intent@example.com", permissions=MANAGE)
    for route in ("stock", "rip-lots", "pose-dtf"):
        response = client.post(
            reverse(f"portal:staff-pod-{route}"),
            {
                "intent": "unsupported-action",
                "quantity": "1",
            },
        )
        assert response.status_code == 400, route
        assert "Action non enregistrée" in response.content.decode()
    assert not StockMovement.objects.exists()
    assert not PodRipWorkItem.objects.exists()


@pytest.mark.django_db
def test_catalog_search_keeps_matching_products_and_pagination(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, client = staff_client(
        email="crud-search@example.com", permissions=(*MANAGE, "view_customer")
    )
    pod_demo.ensure_ready(actor=actor)
    response = client.get(reverse("portal:staff-pod-catalog"), {"q": "TEE-BLK-M"})
    assert response.status_code == 200
    assert response.context["page_obj"].paginator.count == 1
    assert response.context["search_query"] == "TEE-BLK-M"
    response = client.get(reverse("portal:staff-pod-catalog"), {"q": "absent-sku"})
    assert response.context["page_obj"].paginator.count == 0
    assert "Aucun produit ne correspond" in response.content.decode()


@pytest.mark.django_db
def test_shop_connection_error_never_echoes_submitted_secret():
    _actor, client = staff_client(email="crud-secret@example.com", permissions=MANAGE)
    response = client.post(
        reverse("portal:staff-pod-shops"),
        {
            "intent": "save_token",
            "shop_domain": "invalid domain !",
            "access_token": "never-echo-this-secret",
            "name": "Nom conservé",
        },
    )
    assert response.status_code == 400
    assert "never-echo-this-secret" not in response.content.decode()
    assert "access_token" not in response.context["form_data"]
    assert response.context["form_data"]["name"] == "Nom conservé"
