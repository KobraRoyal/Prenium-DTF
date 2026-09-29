from __future__ import annotations

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.inventory.models import (
    ProductLocationRule,
    SkuKind,
    StockBalance,
    StockOwnerKind,
    StorageLocation,
    WarehouseZone,
)
from apps.inventory.services import WarehouseLayoutService
from apps.pod.models import (
    Blank,
    MarkingZone,
    PodRipWorkItem,
    PrintTechnique,
    ShopifyProduct,
    ShopifyStore,
    ShopifyVariant,
)
from apps.pod.services import BlankCatalogService, PrintTechniqueService
from apps.pod.services.ops_demo import PodOpsBootstrapService
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db

catalog = PrintTechniqueService()
blanks = BlankCatalogService()
warehouse = WarehouseLayoutService()
pod_demo = PodOpsBootstrapService()


def grant(user, *codenames):
    user.user_permissions.add(
        *(Permission.objects.get(codename=codename) for codename in codenames)
    )


def staff_user(*, email: str, permissions: tuple[str, ...]):
    user = get_user_model().objects.create_user(email=email, password="pass", is_staff=True)
    grant(user, "access_staff_portal", *permissions)
    return user


def staff_client(*, email: str, permissions: tuple[str, ...]):
    user = staff_user(email=email, permissions=permissions)
    client = Client()
    assert client.login(email=email, password="pass")
    return user, client


VIEW = ("access_pod_atelier",)
MANAGE = ("access_pod_atelier", "manage_pod_catalog", "operate_pod_production", "manage_warehouse")


def test_client_cannot_open_pod_hub():
    user = get_user_model().objects.create_user(email="client-pod@example.com", password="pass")
    customer = Customer.objects.create(name="Client POD")
    CustomerMembership.objects.create(customer=customer, user=user)
    client = Client()
    assert client.login(email=user.email, password="pass")
    response = client.get(reverse("portal:staff-pod-hub"))
    assert response.status_code == 403


def test_staff_without_pod_perm_is_denied():
    _user, client = staff_client(email="staff-no-pod@example.com", permissions=())
    response = client.get(reverse("portal:staff-pod-hub"))
    assert response.status_code == 403
    assert AuditLogEntry.objects.filter(action="pod.atelier.permission_rejected").exists()


def test_hub_get_is_read_only_even_for_manager():
    _user, client = staff_client(email="staff-pod-hub@example.com", permissions=MANAGE)
    response = client.get(reverse("portal:staff-pod-hub"))
    assert response.status_code == 200
    assert PrintTechnique.objects.count() == 0
    assert WarehouseZone.objects.count() == 0
    assert Blank.objects.count() == 0
    assert ShopifyStore.objects.count() == 0
    assert ShopifyProduct.objects.count() == 0
    assert ShopifyVariant.objects.count() == 0
    assert PodRipWorkItem.objects.count() == 0
    assert StockBalance.objects.count() == 0
    content = response.content.decode()
    assert "À produire" in content
    assert "Pose" in content
    assert "Suivi" in content
    assert "Lots RIP" not in content.split('class="pod-workspace-nav__pages"', 1)[1].split("</div>", 1)[0]
    assert "Réglages POD" in content
    assert 'aria-label="Production POD"' in content
    assert reverse("portal:staff-pod-settings") in content
    assert "Aucune action de production en attente" in content
    assert 'id="pod-pick-scan"' not in content


def test_pod_catalog_stock_and_rip_gets_do_not_bootstrap_rows():
    _actor, client = staff_client(email="staff-pod-all-gets@example.com", permissions=MANAGE)
    for name in (
        "portal:staff-pod-techniques",
        "portal:staff-pod-warehouse",
        "portal:staff-pod-stock",
        "portal:staff-pod-rip-lots",
        "portal:staff-pod-catalog",
    ):
        assert client.get(reverse(name)).status_code == 200
    assert PrintTechnique.objects.count() == 0
    assert WarehouseZone.objects.count() == 0


@pytest.mark.parametrize("directory", ["02_../../outside", "02_rip/other", "02_rip\\other"])
def test_technique_rejects_non_flat_rip_directory(directory):
    actor, _client = staff_client(
        email=f"staff-rip-dir-{abs(hash(directory))}@example.com", permissions=MANAGE
    )
    with pytest.raises(ValidationError, match="répertoire RIP"):
        catalog.create_technique(
            actor=actor,
            source="test",
            data={"code": "bad", "name": "Bad", "rip_directory": directory},
        )
    assert not PrintTechnique.objects.filter(code="bad").exists()


def test_demo_bootstrap_requires_explicit_service_call():
    from apps.pod.services.variant_config import VariantConfigService

    actor, client = staff_client(email="staff-pod-boot@example.com", permissions=MANAGE)
    grant(actor, "view_customer")
    response = client.get(reverse("portal:staff-pod-hub"))
    assert response.status_code == 200
    assert not Blank.objects.exists()
    assert not PodRipWorkItem.objects.exists()

    pod_demo.ensure_ready(actor=actor)

    assert Blank.objects.filter(sku="TEE-POD").exists()
    assert StorageLocation.objects.filter(code="A-01-01-A").exists()
    variant = ShopifyVariant.objects.get(sku="TEE-BLK-M")
    config = VariantConfigService().get_or_create_config(variant)
    assert VariantConfigService().configuration_status(config) == "pod"
    assert blanks.list_blanks(actor=actor).count() >= 1
    assert warehouse.list_zones(actor=actor).first().locations.count() >= 1
    assert PodRipWorkItem.objects.filter(shopify_order_number="SO-SEED-QUEUE").exists()
    assert PodRipWorkItem.objects.filter(shopify_order_number="SO-SEED-PICK").exists()
    assert PodRipWorkItem.objects.filter(shopify_order_number="SO-SEED-POSE").exists()
    assert PodRipWorkItem.objects.filter(shopify_order_number="SO-SEED-QC").exists()


def test_hub_updates_queued_quantity_and_lists_orders():
    actor, client = staff_client(email="staff-pod-qty@example.com", permissions=MANAGE)
    grant(actor, "view_customer")
    pod_demo.ensure_ready(actor=actor)
    client.get(reverse("portal:staff-pod-hub"))
    item = PodRipWorkItem.objects.get(shopify_order_number="SO-SEED-QUEUE")
    response = client.post(
        reverse("portal:staff-pod-hub"),
        {
            "intent": "set_quantity",
            "work_item_public_id": str(item.public_id),
            "quantity": "3",
        },
    )
    assert response.status_code == 302
    item.refresh_from_db()
    assert item.quantity == 3
    page = client.get(reverse("portal:staff-pod-hub"))
    body = page.content.decode()
    assert "SO-SEED-QUEUE" in body
    assert "Nouvelles pièces à préparer" in body
    assert "T-shirt POD démo" in body
    assert "Devant" in body
    assert "pod-board-form" in body
    assert "1 · Picking" in body
    assert "2 · Lot DTF" in body
    assert "Tout cocher" in body


def test_hub_prepare_requires_selection():
    actor, client = staff_client(email="staff-pod-prep-sel@example.com", permissions=MANAGE)
    grant(actor, "view_customer")
    pod_demo.ensure_ready(actor=actor)
    client.get(reverse("portal:staff-pod-hub"))
    assert PodRipWorkItem.objects.filter(shopify_order_number="SO-SEED-QUEUE").exists()
    response = client.post(reverse("portal:staff-pod-hub"), {"intent": "prepare"})
    assert response.status_code == 400
    body = response.content.decode()
    assert "Sélectionnez au moins une commande" in body


def test_pick_session_pdf_keeps_later_orders_for_the_next_session():
    import pymupdf
    from apps.pod.models import PodPickSession

    actor, client = staff_client(email="staff-pod-pick@example.com", permissions=MANAGE)
    grant(actor, "view_customer")
    pod_demo.ensure_ready(actor=actor, customer=Customer.objects.create(name="Client démo picking"))
    client.get(reverse("portal:staff-pod-hub"))
    item = PodRipWorkItem.objects.get(shopify_order_number="SO-SEED-QUEUE")
    created = client.post(
        reverse("portal:staff-pod-hub"),
        {"intent": "print_session", "work_item_public_ids": [str(item.public_id)]},
    )
    assert created.status_code == 302
    session = (
        PodPickSession.objects.filter(lines__work_item=item, lines__voided_at__isnull=True)
        .distinct()
        .get()
    )
    picking = client.get(
        reverse(
            "portal:staff-pod-pick-session-pdf",
            kwargs={"session_public_id": session.public_id, "document_kind": "picking"},
        )
    )
    labels = client.get(
        reverse(
            "portal:staff-pod-pick-session-pdf",
            kwargs={"session_public_id": session.public_id, "document_kind": "etiquettes"},
        )
    )
    picking_pdf = pymupdf.open(stream=b"".join(picking.streaming_content), filetype="pdf")
    labels_pdf = pymupdf.open(stream=b"".join(labels.streaming_content), filetype="pdf")
    assert abs(picking_pdf[0].rect.width - 595) < 2
    assert abs(labels_pdf[0].rect.width - 100 * 72 / 25.4) < 2
    assert abs(labels_pdf[0].rect.height - 50 * 72 / 25.4) < 2
    active_lines = list(session.lines.filter(voided_at__isnull=True))
    assert len(labels_pdf) == len(active_lines)
    picking_text = "\n".join(page.get_text() for page in picking_pdf)
    assert "PICKING POD" in picking_text
    assert "emplacement(s)" in picking_text
    for line, label_page in zip(active_lines, labels_pdf, strict=True):
        label_text = label_page.get_text()
        assert line.scan_identifier in picking_text
        assert line.scan_identifier in label_text
        assert line.shopify_order_number in label_text
        assert line.location_code in label_text
        assert "POD / PIÈCE" in label_text
    page = client.get(reverse("portal:staff-pod-hub"))
    body = page.content.decode()
    assert "PICK-" in body
    assert "Zebra" in body
    assert 'id="pod-pick-workflow"' in body
    assert 'id="pod-pick-scan"' in body
    assert "à préparer" in body
    # CTA « Reprendre » seulement si sessions absentes ; ici le poste est déjà affiché.
    assert "Sortie de stock" in body
    again = client.post(
        reverse("portal:staff-pod-hub"),
        {"intent": "print_session", "work_item_public_ids": [str(item.public_id)]},
    )
    assert again.status_code == 400


def test_pick_sheet_paginates_without_losing_piece_identifiers():
    from datetime import datetime, timezone
    from types import SimpleNamespace

    import pymupdf
    from apps.pod.services.pick_sheet import write_picking_list_pdf

    lines = [
        SimpleNamespace(
            location_code="A-01",
            blank_sku="TEE-BLACK-M",
            blank_name="T-shirt premium",
            size_label="M",
            color_name="Noir",
            shopify_order_number=f"SO-{index:04d}",
            sequence=index,
            scan_identifier=f"POD-{index:010d}",
            shopify_sku="TEE-PERSONNALISE",
            markings="Devant - impression DTF",
        )
        for index in range(1, 36)
    ]
    session = SimpleNamespace(
        code="PICK-TEST-001",
        created_at=datetime.now(timezone.utc),
        lines=SimpleNamespace(filter=lambda **kwargs: lines),
    )
    document = pymupdf.open(stream=write_picking_list_pdf(session), filetype="pdf")
    assert len(document) > 1
    all_text = "\n".join(page.get_text() for page in document)
    for line in lines:
        assert all_text.count(line.scan_identifier) == 1
    for page in document:
        assert "PICKING POD" in page.get_text()
        assert "Page " in page.get_text()
        for word in page.get_text("words"):
            assert word[0] >= 0 and word[2] <= page.rect.width
            assert word[1] >= 0 and word[3] <= page.rect.height


def test_staff_cannot_create_technique_without_manage_perm():
    _user, client = staff_client(email="staff-pod-ro@example.com", permissions=VIEW)
    response = client.post(
        reverse("portal:staff-pod-techniques"),
        {"code": "emb", "name": "Broderie", "rip_directory": "02_embroidery"},
    )
    assert response.status_code == 403


def test_create_blank_variant_capability_and_default_bin():
    actor, client = staff_client(email="staff-pod-rw@example.com", permissions=MANAGE)
    catalog.ensure_dtf_technique(actor=actor)
    warehouse.ensure_default_layout(actor=actor)
    create_blank = client.post(
        reverse("portal:staff-pod-blanks"),
        {"sku": "tee-200", "name": "T-shirt 185g", "brand": "Stanley"},
    )
    assert create_blank.status_code == 302
    blank_public_id = blanks.list_blanks(actor=actor).get(sku="TEE-200").public_id
    detail = reverse("portal:staff-pod-blank-detail", kwargs={"blank_public_id": blank_public_id})
    variant_response = client.post(
        detail,
        {
            "intent": "variant",
            "sku": "tee-200-m-blk",
            "size_label": "M",
            "color_name": "Noir",
            "color_hex": "#111111",
        },
    )
    assert variant_response.status_code == 302
    dtf = PrintTechnique.objects.get(code="dtf")
    cap_response = client.post(
        detail,
        {
            "intent": "marking_options",
            "zone_public_ids": [str(MarkingZone.objects.get(code="front").public_id)],
            "technique_public_ids": [str(dtf.public_id)],
        },
    )
    assert cap_response.status_code == 302
    location_response = client.post(
        reverse("portal:staff-pod-warehouse"),
        {
            "zone_public_id": str(warehouse.list_zones(actor=actor).get(code="blanks").public_id),
            "code": "a-03-02-b",
            "label": "Vierges allée A",
        },
    )
    assert location_response.status_code == 302
    location = StorageLocation.objects.get(code="A-03-02-B")
    variant = blanks.list_blanks(actor=actor).get(sku="TEE-200").variants.get()
    rule_response = client.post(
        detail,
        {
            "intent": "default_location",
            "variant_public_id": str(variant.public_id),
            "location_public_id": str(location.public_id),
        },
    )
    assert rule_response.status_code == 302
    rule = ProductLocationRule.objects.get(blank_variant=variant)
    assert rule.sku_kind == SkuKind.BLANK
    assert rule.owner_kind == StockOwnerKind.ATELIER
    assert rule.location_id == location.pk
    loc_page = client.get(
        reverse(
            "portal:staff-pod-location-detail",
            kwargs={"location_public_id": location.public_id},
        )
    )
    assert loc_page.status_code == 200
    assert b"TEE-200-M-BLK" in loc_page.content
    assert b"Bin vide" in loc_page.content


def test_service_rejects_foreign_customer_actor_without_staff():
    user = get_user_model().objects.create_user(email="member@example.com", password="pass")
    customer = Customer.objects.create(name="Autre")
    CustomerMembership.objects.create(customer=customer, user=user)
    with pytest.raises(PermissionDenied):
        catalog.list_techniques(actor=user)


def test_invalid_location_code_is_rejected():
    actor = staff_user(email="staff-pod-code@example.com", permissions=MANAGE)
    warehouse.ensure_default_layout(actor=actor)
    zone = warehouse.list_zones(actor=actor).get(code="blanks")
    with pytest.raises(Exception, match="emplacement"):
        warehouse.create_location(
            actor=actor,
            source="test",
            data={"zone_public_id": zone.public_id, "code": "bad code"},
        )


def test_urls_use_public_id_not_pk():
    path = reverse(
        "portal:staff-pod-blank-detail",
        kwargs={"blank_public_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert path.endswith("/00000000-0000-0000-0000-000000000001/")
    assert "/blanks/1/" not in path
