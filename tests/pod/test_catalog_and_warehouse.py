from __future__ import annotations

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.inventory.models import ProductLocationRule, SkuKind, StockOwnerKind, StorageLocation
from apps.inventory.services import WarehouseLayoutService
from apps.pod.models import BlankPlacementCapability, PrintTechnique
from apps.pod.services import BlankCatalogService, PrintTechniqueService
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db

catalog = PrintTechniqueService()
blanks = BlankCatalogService()
warehouse = WarehouseLayoutService()


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
MANAGE = ("access_pod_atelier", "manage_pod_catalog", "manage_warehouse")


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


def test_hub_seeds_dtf_and_warehouse_zones():
    _user, client = staff_client(email="staff-pod-hub@example.com", permissions=VIEW)
    response = client.get(reverse("portal:staff-pod-hub"))
    assert response.status_code == 200
    assert PrintTechnique.objects.filter(code="dtf").exists()
    content = response.content.decode()
    assert "Supports vierges" in content
    assert "Entrepôt" in content
    assert warehouse.list_zones(actor=_user).count() == 5


def test_staff_cannot_create_technique_without_manage_perm():
    _user, client = staff_client(email="staff-pod-ro@example.com", permissions=VIEW)
    response = client.post(
        reverse("portal:staff-pod-techniques"),
        {"code": "emb", "name": "Broderie", "rip_directory": "02_embroidery"},
    )
    assert response.status_code == 403


def test_create_blank_variant_capability_and_default_bin():
    actor, client = staff_client(email="staff-pod-rw@example.com", permissions=MANAGE)
    client.get(reverse("portal:staff-pod-hub"))
    create_blank = client.post(
        reverse("portal:staff-pod-blanks"),
        {"sku": "tee-200", "name": "T-shirt 185g", "brand": "Stanley"},
    )
    assert create_blank.status_code == 302
    blank_public_id = blanks.list_blanks(actor=actor).get().public_id
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
            "intent": "capability",
            "placement": BlankPlacementCapability.Placement.FRONT,
            "technique_public_id": str(dtf.public_id),
            "is_required": "on",
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
    variant = blanks.list_blanks(actor=actor).get().variants.get()
    rule_response = client.post(
        detail,
        {
            "intent": "default_location",
            "variant_public_id": str(variant.public_id),
            "location_public_id": str(location.public_id),
        },
    )
    assert rule_response.status_code == 302
    rule = ProductLocationRule.objects.get()
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
