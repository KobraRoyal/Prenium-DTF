from __future__ import annotations

import hashlib
from io import BytesIO

from apps.b2b_order_projects.models import B2BOrderProject, B2BOrderProjectItem
from apps.customers.models import Customer, CustomerBillingProfile, CustomerMembership
from apps.gang_sheets.models import GangSheetDriveSync
from apps.uploads.models import Asset, AssetVersion
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image


def create_customer_scope(*, email: str, role=CustomerMembership.Role.OWNER):
    user = get_user_model().objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(name=email.split("@")[0], b2b_order_projects_enabled=True)
    CustomerMembership.objects.create(customer=customer, user=user, role=role)
    CustomerBillingProfile.objects.create(customer=customer, price_per_sqm_eur="25.00")
    project = B2BOrderProject.objects.create(
        customer=customer,
        created_by=user,
        project_number=f"GS-{customer.public_id.hex[:10]}",
        name="Projet Gang Sheet",
    )
    return user, customer, project


def attach_png_asset(
    *, customer, project, user, name="logo.png", width_mm="100.00", height_mm="50.00"
):
    output = BytesIO()
    Image.new("RGBA", (300, 150), (220, 48, 40, 220)).save(output, format="PNG", dpi=(300, 300))
    content = output.getvalue()
    asset = Asset.objects.create(customer=customer, created_by=user, name=name)
    version = AssetVersion.objects.create(
        customer=customer,
        asset=asset,
        uploaded_by=user,
        version_number=1,
        file=SimpleUploadedFile(name, content, content_type="image/png"),
        original_filename=name,
        mime_type="image/png",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        analysis_status=AssetVersion.AnalysisStatus.READY,
    )
    asset.current_version = version
    asset.save(update_fields=["current_version", "updated_at"])
    B2BOrderProjectItem.objects.create(
        customer=customer,
        project=project,
        asset=asset,
        name=name,
        width_mm=width_mm,
        height_mm=height_mm,
        quantity=1,
        sort_order=project.items.count() + 1,
    )
    return asset, version


def mark_gang_sheet_drive_synced(sheet):
    GangSheetDriveSync.objects.update_or_create(
        customer=sheet.customer,
        gang_sheet=sheet,
        defaults={
            "status": GangSheetDriveSync.Status.SYNCED,
            "revision": sheet.revision,
            "drive_filename": f"production-r{sheet.revision}.pdf",
            "drive_file_id": f"drive-file-r{sheet.revision}",
        },
    )
    sheet.refresh_from_db()
    return sheet
