#!/usr/bin/env python3
"""Serve an isolated, synthetic IDS Hub demo for marketing screenshots.

This command intentionally uses ``config.settings.test`` and creates both its
SQLite database and media tree in one ``TemporaryDirectory``.  Nothing is read
from the normal development database or media volume.  The temporary data is
removed when the process stops.

Typical use from the repository root::

    docker compose run --rm -p 127.0.0.1:8765:8765 \
      web python /app/scripts/capture_marketing_demo.py

The command prints a small JSON manifest containing the synthetic credentials
and the two authenticated page paths to capture.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from io import BytesIO
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
DEMO_EMAIL = "demo.capture@atelier.invalid"
DEMO_PASSWORD = "demo-capture-only"


def _configure_django(workspace: Path) -> None:
    """Configure Django before importing any project model or service."""
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
    os.environ["B2B_DTF_ORDER_PROJECT_ENABLED"] = "True"
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))

    import django
    from django.conf import settings

    # Resolve the test settings first, then replace every persistent path before
    # Django opens a connection or storage backend.
    _ = settings.DATABASES
    settings.DATABASES["default"]["NAME"] = workspace / "demo.sqlite3"
    settings.MEDIA_ROOT = workspace / "media"
    settings.STATIC_ROOT = workspace / "static"
    settings.DEBUG = False
    settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
    settings.SESSION_COOKIE_SECURE = False
    settings.CSRF_COOKIE_SECURE = False
    settings.GOOGLE_DRIVE_SYNC_ENABLED = False
    settings.WEB_PUSH_ENABLED = False
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.INTERNAL_NOTIFICATION_EMAILS = []
    django.setup()


def _font(size: int, *, bold: bool = False):
    from PIL import ImageFont

    filename = "montserrat-700.ttf" if bold else "montserrat-400.ttf"
    path = BACKEND_ROOT / "static_src" / "fonts" / "gang-sheet" / filename
    return ImageFont.truetype(str(path), size=size)


def _floraison_png() -> bytes:
    """Create a transparent, original floral print fixture with Pillow."""
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (1500, 1050), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    ink = (31, 49, 44, 255)
    coral = (232, 105, 91, 255)
    pink = (245, 177, 174, 255)
    green = (86, 132, 102, 255)
    cream = (249, 231, 191, 255)

    draw.rounded_rectangle((80, 90, 1420, 960), radius=90, fill=(255, 250, 241, 242))
    for cx, cy, scale, color in (
        (260, 285, 1.0, coral),
        (1230, 300, 0.8, pink),
        (1160, 770, 1.1, coral),
        (335, 790, 0.75, cream),
    ):
        radius = int(92 * scale)
        for dx, dy in ((0, -radius), (radius, 0), (0, radius), (-radius, 0)):
            draw.ellipse(
                (cx + dx - radius, cy + dy - radius, cx + dx + radius, cy + dy + radius),
                fill=color,
            )
        draw.ellipse((cx - 54, cy - 54, cx + 54, cy + 54), fill=cream)
    draw.arc((170, 185, 1320, 930), 195, 345, fill=green, width=26)
    draw.arc((250, 100, 1220, 885), 15, 160, fill=green, width=22)
    draw.text((750, 420), "FLORAISON", font=_font(116, bold=True), fill=ink, anchor="mm")
    draw.text((750, 555), "COLLECTION 2026", font=_font(43), fill=green, anchor="mm")
    draw.line((530, 630, 970, 630), fill=coral, width=12)

    output = BytesIO()
    image.save(output, format="PNG", dpi=(300, 300), optimize=True)
    image.close()
    return output.getvalue()


def _atelier_logo_png() -> bytes:
    """Create a transparent, original atelier mark fixture with Pillow."""
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (1200, 1200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    navy = (24, 38, 52, 255)
    apricot = (238, 151, 94, 255)
    draw.rounded_rectangle((90, 90, 1110, 1110), radius=220, fill=navy)
    draw.ellipse((285, 250, 915, 880), outline=apricot, width=44)
    draw.text((600, 505), "A", font=_font(390, bold=True), fill=(255, 250, 242, 255), anchor="mm")
    draw.text((600, 925), "ATELIER", font=_font(72, bold=True), fill=apricot, anchor="mm")

    output = BytesIO()
    image.save(output, format="PNG", dpi=(300, 300), optimize=True)
    image.close()
    return output.getvalue()


def _upload(name: str, content: bytes):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, content, content_type="image/png")


def _seed_demo() -> dict[str, str]:
    """Create one isolated tenant and two authentic application states."""
    from apps.b2b_order_projects.services import B2BOrderProjectService
    from apps.b2b_order_projects.services.configurator import B2BOrderProjectConfiguratorService
    from apps.customers.models import Customer, CustomerBillingProfile, CustomerMembership
    from apps.gang_sheets.services import GangSheetService
    from apps.uploads.services.asset_analysis import AssetAnalysisService
    from django.contrib.auth import get_user_model
    from django.urls import reverse

    user = get_user_model().objects.create_user(email=DEMO_EMAIL, password=DEMO_PASSWORD)
    customer = Customer.objects.create(
        name="Atelier Démonstration",
        billing_email=DEMO_EMAIL,
        b2b_order_projects_enabled=True,
        billing_address_line1="12 rue des Fleurs",
        billing_postal_code="75011",
        billing_city="Paris",
        billing_country="FR",
    )
    CustomerMembership.objects.create(
        customer=customer,
        user=user,
        role=CustomerMembership.Role.OWNER,
    )
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")

    floral = _floraison_png()
    logo = _atelier_logo_png()
    project_service = B2BOrderProjectService()
    configurator = B2BOrderProjectConfiguratorService()
    analyzer = AssetAnalysisService()
    project = project_service.create_project(
        customer=customer,
        actor=user,
        data={
            "name": "Collection Floraison",
            "customer_reference": "DEMO-FLORAISON",
            "customer_comment": "Série textile — lancement printemps",
        },
        source="marketing_demo",
    )
    order_assets = []
    for name, filename, content, quantity, support in (
        ("Collection Floraison", "collection-floraison.png", floral, 12, "#f4e7d4"),
        ("Logo atelier", "logo-atelier.png", logo, 24, "#1f3130"),
    ):
        item, version = configurator.add_visual(
            project=project,
            actor=user,
            data={"name": name, "quantity": quantity, "support_color_hex": support},
            uploaded_file=_upload(filename, content),
            source="marketing_demo",
        )
        analyzer.analyze(version_public_id=version.public_id, source="marketing_demo")
        order_assets.append((item, version))

    gang_service = GangSheetService()
    sheet = gang_service.create_sheet(
        customer=customer,
        actor=user,
        name="Collection Floraison · Gang Sheet",
        source="marketing_demo",
    )
    sheet_versions = []
    for filename, content in (
        ("collection-floraison.png", floral),
        ("logo-atelier.png", logo),
    ):
        _source_asset, version = gang_service.upload_source_asset(
            sheet=sheet,
            actor=user,
            uploaded_file=_upload(filename, content),
            source="marketing_demo",
        )
        analyzer.analyze(version_public_id=version.public_id, source="marketing_demo")
        sheet_versions.append(version)

    sheet.refresh_from_db()
    gang_service.auto_place_ready_sources(
        sheet=sheet,
        expected_revision=sheet.revision,
        actor=user,
        source="marketing_demo",
    )
    sheet.refresh_from_db()
    for version in sheet_versions:
        gang_service.add_occurrences(
            sheet=sheet,
            asset_version_public_id=version.public_id,
            quantity=2,
            actor=user,
            source="marketing_demo",
        )
        sheet.refresh_from_db()
    gang_service.auto_place(sheet=sheet, actor=user, source="marketing_demo")

    return {
        "login_path": reverse("portal:login"),
        "order_by_file_path": reverse(
            "portal:client-order-project-detail",
            kwargs={
                "customer_public_id": customer.public_id,
                "project_public_id": project.public_id,
            },
        ),
        "gang_sheet_studio_path": reverse(
            "portal:client-gang-sheet-editor",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0", help="Container bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.host not in {"0.0.0.0", "127.0.0.1", "localhost"}:
        parser.error("The demo server may only bind to a local/container interface.")
    if not 1024 <= args.port <= 65535:
        parser.error("Port must be between 1024 and 65535.")

    with tempfile.TemporaryDirectory(prefix="prenium-marketing-demo-") as temporary:
        workspace = Path(temporary)
        _configure_django(workspace)

        from django.core.management import call_command

        call_command("migrate", interactive=False, verbosity=0)
        manifest = _seed_demo()
        manifest.update(
            {
                "base_url": f"http://127.0.0.1:{args.port}",
                "email": DEMO_EMAIL,
                "password": DEMO_PASSWORD,
                "isolation": "temporary SQLite database and MEDIA_ROOT",
                "fixture_sha256": {
                    "collection-floraison.png": hashlib.sha256(_floraison_png()).hexdigest(),
                    "logo-atelier.png": hashlib.sha256(_atelier_logo_png()).hexdigest(),
                },
            }
        )
        print(json.dumps(manifest, ensure_ascii=False), flush=True)
        call_command(
            "runserver",
            f"{args.host}:{args.port}",
            use_reloader=False,
            use_ipv6=False,
            insecure_serving=True,
            verbosity=1,
        )


if __name__ == "__main__":
    main()
