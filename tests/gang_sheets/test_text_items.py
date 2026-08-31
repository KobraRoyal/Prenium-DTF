from __future__ import annotations

from decimal import Decimal

import pymupdf
import pytest
from apps.customers.models import CustomerMembership
from apps.gang_sheets.models import GangSheet, GangSheetItem, GangSheetSourceAsset
from apps.gang_sheets.services import GangSheetDomainError, GangSheetRenderService, GangSheetService
from apps.gang_sheets.services.hybrid_pdf import GangSheetHybridPdfComposer
from apps.gang_sheets.services.text_items import (
    DEFAULT_TEXT_CONTENT,
    fitted_box_mm,
    fitted_height_mm,
    normalize_text_content,
    rasterize_text_item,
    usable_text_max_width_mm,
    wrap_text_to_width,
)
from django.urls import reverse

from .helpers import attach_png_asset, create_customer_scope

pytestmark = pytest.mark.django_db


def test_normalize_text_content_rejects_blank_and_control_characters():
    assert normalize_text_content("  Prénom  \nNom  ") == "Prénom\nNom"
    with pytest.raises(Exception) as error:
        normalize_text_content("   ")
    assert error.value.code == "TEXT_REQUIRED"


def test_normalize_text_content_allows_twenty_hard_line_breaks():
    text = "\n".join(f"L{index}" for index in range(1, 21))
    assert normalize_text_content(text) == text
    with pytest.raises(Exception) as error:
        normalize_text_content(f"{text}\nL21")
    assert error.value.code == "TEXT_TOO_LONG"


def test_add_text_item_creates_printable_occurrence_without_asset():
    user, customer, _project = create_customer_scope(email="text-add@example.com")
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Planche texte")

    item = service.add_text_item(sheet=sheet, actor=user)

    item.refresh_from_db()
    assert item.kind == GangSheetItem.Kind.TEXT
    assert item.asset_version_id is None
    assert item.text_content == DEFAULT_TEXT_CONTENT
    assert item.text_font == "sans"
    assert item.text_color == "#1A1815"
    assert item.text_align == "center"
    assert item.width_mm > 0
    assert item.height_mm > 0
    assert item.width_mm < Decimal("80.00")
    assert item.text_size_mm == Decimal("12.00")
    serialized = service.serialize_sheet(sheet, preview_url_resolver=lambda _version: "/preview")
    assert serialized["items"][0]["kind"] == "text"
    assert serialized["items"][0]["preview_url"] == ""
    assert serialized["items"][0]["asset_version_public_id"] is None
    assert serialized["items"][0]["text_size_mm"] == 12.0
    assert serialized["text_fonts"][0]["id"] == "sans"
    assert {font["id"] for font in serialized["text_fonts"]} >= {
        "sans",
        "serif",
        "mono",
        "inter",
        "montserrat",
        "oswald",
        "playfair",
    }


def test_fitted_box_shrinks_to_content_and_wraps_at_max_width():
    short_w, short_h = fitted_box_mm(content="Ok", max_width_mm=500, font="sans", size_mm=12)
    newline_w, newline_h = fitted_box_mm(
        content="Ok\nOk",
        max_width_mm=500,
        font="sans",
        size_mm=12,
    )
    capped_w, capped_h = fitted_box_mm(
        content="x" * 80,
        max_width_mm=40,
        font="sans",
        size_mm=12,
    )
    unconstrained_w, unconstrained_h = fitted_box_mm(
        content="x" * 80,
        max_width_mm=500,
        font="sans",
        size_mm=12,
    )
    font = pymupdf.Font("helv")
    lines = wrap_text_to_width("A\nB\nC", font=font, fontsize=12, max_width_pt=1000)

    assert short_w < Decimal("80.00")
    assert short_w >= Decimal("5.00")
    assert newline_w == short_w
    assert newline_h > short_h
    assert capped_w <= Decimal("40.00")
    assert capped_w < unconstrained_w
    assert capped_h > unconstrained_h
    assert lines == ["A", "B", "C"]


def test_fitted_height_grows_with_lines_and_wrapping():
    one_line = fitted_height_mm(content="Prenium", width_mm=80, font="sans", bold=False)
    four_lines = fitted_height_mm(
        content="Ligne 1\nLigne 2\nLigne 3\nLigne 4",
        width_mm=80,
        font="sans",
        bold=False,
    )
    wrapped = fitted_height_mm(content="x" * 80, width_mm=40, font="sans", bold=False)
    short = fitted_height_mm(content="Ok", width_mm=40, font="sans", bold=False)

    assert four_lines > one_line
    assert wrapped > short
    assert one_line >= 5


def test_fitted_height_grows_with_explicit_size_and_custom_font():
    small = fitted_height_mm(content="Prenium", width_mm=80, font="sans", size_mm=8)
    large = fitted_height_mm(content="Prenium", width_mm=80, font="sans", size_mm=24)
    inter = fitted_height_mm(content="Prenium", width_mm=80, font="inter", size_mm=12)

    assert large > small
    assert inter > 5


def test_save_layout_persists_font_and_size():
    user, customer, _project = create_customer_scope(email="text-size@example.com")
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Taille")
    item = service.add_text_item(sheet=sheet, actor=user, content="Studio", size_mm=10)
    sheet.refresh_from_db()
    expected_width, expected_height = fitted_box_mm(
        content="Studio",
        max_width_mm=usable_text_max_width_mm(
            sheet_width_mm=sheet.width_mm,
            margin_mm=sheet.margin_mm,
            x_mm=Decimal("20"),
        ),
        font="oswald",
        bold=True,
        size_mm=20,
    )

    service.save_layout(
        sheet=sheet,
        expected_revision=sheet.revision,
        payload=[
            {
                "public_id": str(item.public_id),
                "x_mm": "20",
                "y_mm": "15",
                "width_mm": "80",
                "height_mm": "5",
                "rotation": 0,
                "layout_group_id": None,
                "text_content": "Studio",
                "text_font": "oswald",
                "text_size_mm": "20",
                "text_color": "#1A1815",
                "text_align": "center",
                "text_bold": True,
            }
        ],
        actor=user,
    )

    item.refresh_from_db()
    assert item.text_font == "oswald"
    assert item.text_size_mm == Decimal("20.00")
    assert item.text_bold is True
    assert item.width_mm == expected_width
    assert item.height_mm == expected_height


def test_save_layout_ignores_payload_box_and_fits_the_text():
    user, customer, _project = create_customer_scope(email="text-fit@example.com")
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Hauteur auto")
    item = service.add_text_item(sheet=sheet, actor=user, content="Prenium")
    sheet.refresh_from_db()
    expected_width, expected_height = fitted_box_mm(
        content="Ligne 1\nLigne 2\nLigne 3\nLigne 4",
        max_width_mm=usable_text_max_width_mm(
            sheet_width_mm=sheet.width_mm,
            margin_mm=sheet.margin_mm,
            x_mm=Decimal("20"),
        ),
        font="sans",
        bold=False,
    )

    service.save_layout(
        sheet=sheet,
        expected_revision=sheet.revision,
        payload=[
            {
                "public_id": str(item.public_id),
                "x_mm": "20",
                "y_mm": "15",
                "width_mm": "90",
                "height_mm": "5",
                "rotation": 0,
                "layout_group_id": None,
                "text_content": "Ligne 1\nLigne 2\nLigne 3\nLigne 4",
                "text_font": "sans",
                "text_color": "#1A1815",
                "text_align": "center",
                "text_bold": False,
            }
        ],
        actor=user,
    )

    item.refresh_from_db()
    assert item.width_mm == expected_width
    assert item.height_mm == expected_height
    assert item.width_mm != Decimal("90.00")
    assert item.height_mm > 5
    sheet.refresh_from_db()
    assert sheet.height_mm >= item.y_mm + item.height_mm


def test_text_item_can_be_duplicated_and_saved_with_layout():
    user, customer, _project = create_customer_scope(email="text-dup@example.com")
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Texte duplicable")
    item = service.add_text_item(sheet=sheet, actor=user, content="Studio DTF")
    clone = service.duplicate_occurrence(sheet=sheet, item_public_id=item.public_id, actor=user)

    assert clone.kind == GangSheetItem.Kind.TEXT
    assert clone.text_content == "Studio DTF"
    assert clone.asset_version_id is None

    sheet.refresh_from_db()
    locked, issues = service.save_layout(
        sheet=sheet,
        expected_revision=sheet.revision,
        payload=[
            {
                "public_id": str(item.public_id),
                "x_mm": "20",
                "y_mm": "15",
                "width_mm": "90",
                "height_mm": "28",
                "rotation": 0,
                "layout_group_id": None,
                "text_content": "Prenium",
                "text_font": "serif",
                "text_color": "#A33B45",
                "text_align": "left",
                "text_bold": True,
            },
            {
                "public_id": str(clone.public_id),
                "x_mm": "120",
                "y_mm": "15",
                "width_mm": "80",
                "height_mm": "24",
                "rotation": 0,
                "layout_group_id": None,
                "text_content": clone.text_content,
                "text_font": clone.text_font,
                "text_color": clone.text_color,
                "text_align": clone.text_align,
                "text_bold": clone.text_bold,
            },
        ],
        actor=user,
    )

    item.refresh_from_db()
    assert item.text_content == "Prenium"
    assert item.text_font == "serif"
    assert item.text_color == "#A33B45"
    assert item.text_align == "left"
    assert item.text_bold is True
    assert issues == []
    serialized = service.serialize_sheet(locked, preview_url_resolver=lambda _version: "")
    assert serialized["items"][0]["text_content"] in {"Prenium", "Studio DTF"}


def test_save_layout_rejects_unknown_font_and_keeps_visuals_untouched():
    user, customer, project = create_customer_scope(email="text-invalid@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Mixte")
    visual = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )
    text = service.add_text_item(sheet=sheet, actor=user, content="OK")
    sheet.refresh_from_db()

    with pytest.raises(GangSheetDomainError) as error:
        service.save_layout(
            sheet=sheet,
            expected_revision=sheet.revision,
            payload=[
                {
                    "public_id": str(visual.public_id),
                    "x_mm": visual.x_mm,
                    "y_mm": visual.y_mm,
                    "width_mm": visual.width_mm,
                    "height_mm": visual.height_mm,
                    "rotation": visual.rotation,
                    "layout_group_id": None,
                },
                {
                    "public_id": str(text.public_id),
                    "x_mm": text.x_mm,
                    "y_mm": text.y_mm,
                    "width_mm": text.width_mm,
                    "height_mm": text.height_mm,
                    "rotation": text.rotation,
                    "layout_group_id": None,
                    "text_content": "OK",
                    "text_font": "comic-sans",
                    "text_color": "#000000",
                    "text_align": "center",
                    "text_bold": False,
                },
            ],
            actor=user,
        )

    assert error.value.code == "INVALID_TEXT_FONT"
    text.refresh_from_db()
    assert text.text_font == "sans"


def test_hybrid_pdf_draws_text_as_vector_without_raster_image():
    user, customer, _project = create_customer_scope(email="text-pdf@example.com")
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="PDF texte")
    item = service.add_text_item(
        sheet=sheet, actor=user, content="VECTOR TEXT", font="inter", size_mm=16
    )
    content = GangSheetHybridPdfComposer().compose(sheet=sheet, items=[item])

    with pymupdf.open(stream=content, filetype="pdf") as document:
        page = document[0]
        extracted = " ".join(page.get_text().split())
        assert "VECTOR TEXT" in extracted
        font_blob = " ".join(str(font).lower() for font in page.get_fonts(full=True))
        assert "inter" in font_blob
        assert page.get_images(full=True) == []


def test_request_render_locks_mixed_text_and_visual_items():
    user, customer, project = create_customer_scope(email="text-render-lock@example.com")
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Mixte")
    asset, version = attach_png_asset(customer=customer, project=project, user=user)
    GangSheetSourceAsset.objects.create(
        customer=customer,
        sheet=sheet,
        asset=asset,
        added_by=user,
        width_mm="100.00",
        height_mm="50.00",
    )
    service.add_occurrence(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        actor=user,
    )
    service.add_text_item(sheet=sheet, actor=user, content="Atelier")

    service.request_render(sheet=sheet, actor=user)

    sheet.refresh_from_db()
    assert sheet.status == GangSheet.Status.RENDERING


def test_render_accepts_text_only_sheet():
    user, customer, _project = create_customer_scope(email="text-render@example.com")
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Rendu texte")
    service.add_text_item(sheet=sheet, actor=user, content="Atelier")
    sheet.refresh_from_db()
    sheet.status = GangSheet.Status.RENDERING
    sheet.save(update_fields=["status", "updated_at"])

    rendered = GangSheetRenderService().render(sheet_public_id=sheet.public_id)

    assert rendered.status == GangSheet.Status.READY
    assert rendered.preview_file.name.endswith(".png")
    rendered.final_file.open("rb")
    try:
        assert rendered.final_file.read(5) == b"%PDF-"
    finally:
        rendered.final_file.close()


def test_owner_can_add_text_via_portal_and_readonly_is_blocked(client):
    owner, customer, _project = create_customer_scope(email="text-owner@example.com")
    readonly, _other, _other_project = create_customer_scope(
        email="text-readonly@example.com",
        role=CustomerMembership.Role.READONLY,
    )
    CustomerMembership.objects.create(
        customer=customer, user=readonly, role=CustomerMembership.Role.READONLY
    )
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=owner, name="Portail texte")
    url = reverse(
        "portal:client-gang-sheet-item-add",
        kwargs={"customer_public_id": customer.public_id, "sheet_public_id": sheet.public_id},
    )

    client.force_login(readonly)
    denied = client.post(url, {"kind": "text", "text_content": "Interdit"})
    assert denied.status_code == 403

    client.force_login(owner)
    created = client.post(url, {"kind": "text", "text_content": "Prénom"})
    assert created.status_code == 201
    payload = created.json()
    assert payload["ok"] is True
    assert payload["kind"] == "text"
    assert sheet.items.filter(kind=GangSheetItem.Kind.TEXT, text_content="Prénom").exists()

    editor = client.get(
        reverse(
            "portal:client-gang-sheet-editor",
            kwargs={"customer_public_id": customer.public_id, "sheet_public_id": sheet.public_id},
        )
    )
    assert editor.status_code == 200
    body = editor.content.decode()
    assert "data-add-text" in body
    assert '"kind": "text"' in body
    assert "text_content" in body


def test_text_item_is_isolated_across_customers(client):
    owner_a, customer_a, _project_a = create_customer_scope(email="text-a@example.com")
    owner_b, customer_b, _project_b = create_customer_scope(email="text-b@example.com")
    service = GangSheetService()
    sheet_a = service.create_sheet(customer=customer_a, actor=owner_a, name="A")
    sheet_b = service.create_sheet(customer=customer_b, actor=owner_b, name="B")

    client.force_login(owner_a)
    response = client.post(
        reverse(
            "portal:client-gang-sheet-item-add",
            kwargs={
                "customer_public_id": customer_a.public_id,
                "sheet_public_id": sheet_b.public_id,
            },
        ),
        {"kind": "text"},
    )
    assert response.status_code == 404
    assert sheet_a.items.count() == 0
    assert sheet_b.items.count() == 0


def test_usable_text_max_width_follows_the_visible_axis_when_rotated():
    horizontal = usable_text_max_width_mm(
        sheet_width_mm=550,
        margin_mm=5,
        x_mm=500,
        sheet_height_mm=200,
        y_mm=10,
        rotation=0,
    )
    vertical = usable_text_max_width_mm(
        sheet_width_mm=550,
        margin_mm=5,
        x_mm=500,
        sheet_height_mm=200,
        y_mm=10,
        rotation=90,
    )
    assert horizontal == Decimal("45.00")
    assert vertical == Decimal("185.00")


def test_save_layout_rotated_text_does_not_wrap_on_the_hidden_axis():
    user, customer, _project = create_customer_scope(email="text-rotate-save@example.com")
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Rotation")
    item = service.add_text_item(sheet=sheet, actor=user, content="Prenium")
    sheet.refresh_from_db()
    expected_width, expected_height = fitted_box_mm(
        content="Prenium",
        max_width_mm=usable_text_max_width_mm(
            sheet_width_mm=sheet.width_mm,
            margin_mm=sheet.margin_mm,
            x_mm=Decimal("480"),
            sheet_height_mm=sheet.height_mm,
            y_mm=Decimal("10"),
            rotation=90,
        ),
        font="sans",
        size_mm=12,
    )

    service.save_layout(
        sheet=sheet,
        expected_revision=sheet.revision,
        payload=[
            {
                "public_id": str(item.public_id),
                "x_mm": "480",
                "y_mm": "10",
                "width_mm": "8",
                "height_mm": "8",
                "rotation": 90,
                "layout_group_id": None,
                "text_content": "Prenium",
                "text_font": "sans",
                "text_size_mm": "12",
                "text_color": "#1A1815",
                "text_align": "center",
                "text_bold": False,
            }
        ],
        actor=user,
    )

    item.refresh_from_db()
    assert item.rotation == 90
    assert item.width_mm == expected_width
    assert item.height_mm == expected_height
    assert item.width_mm > Decimal("40.00")


def test_rasterize_text_stays_unrotated_so_preview_can_rotate_once():
    user, customer, _project = create_customer_scope(email="text-rotate-raster@example.com")
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Raster rotation")
    item = service.add_text_item(sheet=sheet, actor=user, content="HELLO", size_mm=16)
    item.rotation = 90
    item.save(update_fields=["rotation", "updated_at"])

    image = rasterize_text_item(item=item, target_width=160, target_height=40)
    try:
        assert image.size[0] > image.size[1]
    finally:
        image.close()


def test_hybrid_pdf_keeps_rotated_text_readable():
    user, customer, _project = create_customer_scope(email="text-rotate-pdf@example.com")
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="PDF rotation")
    item = service.add_text_item(sheet=sheet, actor=user, content="SPIN", size_mm=12)
    item.x_mm = Decimal("40")
    item.y_mm = Decimal("8")
    item.rotation = 90
    item.save(update_fields=["x_mm", "y_mm", "rotation", "updated_at"])
    content = GangSheetHybridPdfComposer().compose(sheet=sheet, items=[item])

    with pymupdf.open(stream=content, filetype="pdf") as document:
        extracted = " ".join(document[0].get_text().split())
        assert "SPIN" in extracted
        assert document[0].get_images(full=True) == []
