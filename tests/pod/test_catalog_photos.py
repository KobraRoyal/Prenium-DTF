from __future__ import annotations

from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from tests.pod.test_catalog_and_warehouse import MANAGE, staff_client

pytestmark = pytest.mark.django_db


def _png_bytes(*, color=(20, 40, 60), size=(80, 80)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_blank_and_variant_photos_upload_and_serve():
    _actor, client = staff_client(email="staff-pod-photos@example.com", permissions=MANAGE)
    create = client.post(
        reverse("portal:staff-pod-blanks"),
        {"sku": "TEE-PHOTO", "name": "Tee photo", "brand": "Demo"},
    )
    assert create.status_code == 302
    from apps.pod.models import Blank

    blank = Blank.objects.get(sku="TEE-PHOTO")
    detail = reverse("portal:staff-pod-blank-detail", kwargs={"blank_public_id": blank.public_id})
    photo = SimpleUploadedFile("support.png", _png_bytes(), content_type="image/png")
    uploaded = client.post(detail, {"intent": "blank_photo", "photo": photo})
    assert uploaded.status_code == 302
    blank.refresh_from_db()
    assert blank.has_photo
    thumb = client.get(
        reverse("portal:staff-pod-blank-photo", kwargs={"blank_public_id": blank.public_id})
        + "?size=thumb"
    )
    assert thumb.status_code == 200
    assert thumb["Content-Type"] == "image/webp"

    client.post(
        detail,
        {
            "intent": "variant",
            "sku": "TEE-PHOTO-M-BLK",
            "size_label": "M",
            "color_name": "Noir",
            "color_hex": "#111111",
        },
    )
    variant = blank.variants.get(sku="TEE-PHOTO-M-BLK")
    variant_photo = SimpleUploadedFile(
        "variant.png", _png_bytes(color=(200, 20, 20)), content_type="image/png"
    )
    set_variant = client.post(
        detail,
        {
            "intent": "variant_photo",
            "variant_public_id": str(variant.public_id),
            "photo": variant_photo,
        },
    )
    assert set_variant.status_code == 302
    variant.refresh_from_db()
    assert variant.has_own_photo
    served = client.get(
        reverse(
            "portal:staff-pod-blank-variant-photo",
            kwargs={
                "blank_public_id": blank.public_id,
                "variant_public_id": variant.public_id,
            },
        )
        + "?size=thumb"
    )
    assert served.status_code == 200
    page = client.get(detail)
    assert page.status_code == 200
    body = page.content.decode()
    assert "photo propre" in body
    assert "staff-pod-blank-photo" in body or str(blank.public_id) in body


def test_shopify_cdn_thumb_filter():
    from apps.pod.services.catalog_images import shopify_cdn_resized

    url = "https://cdn.shopify.com/s/files/1/tee.jpg?v=1"
    resized = shopify_cdn_resized(url, width=80)
    assert "width=80" in resized
    assert "v=1" in resized
