from decimal import Decimal

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import CustomerMembership
from apps.gang_sheets.models import GangSheet, GangSheetSourceAsset
from apps.gang_sheets.services import GangSheetDomainError, GangSheetService
from apps.uploads.models import AssetAnalysis
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from .helpers import attach_png_asset, create_customer_scope

pytestmark = pytest.mark.django_db


@pytest.fixture
def composition():
    user, customer, project = create_customer_scope(email="preflight@example.com")
    asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Qualité")
    source = GangSheetSourceAsset.objects.create(
        customer=customer,
        sheet=sheet,
        asset=asset,
        added_by=user,
        width_mm="25.4",
        height_mm="12.7",
    )
    item = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )
    analysis = AssetAnalysis.objects.create(
        customer=customer,
        version=version,
        image_width=300,
        image_height=150,
    )
    sheet.refresh_from_db()
    return service, sheet, item, source, analysis, user


def state(service, sheet):
    sheet.refresh_from_db()
    return service.serialize_sheet(sheet, preview_url_resolver=lambda version: "/preview/")


def mark_ready(sheet):
    sheet.status = GangSheet.Status.READY
    sheet.final_file = SimpleUploadedFile("ready.pdf", b"%PDF-1.4\n%%EOF")
    sheet.save(update_fields=["status", "final_file", "updated_at"])


def acknowledgement(preflight):
    return {
        "expected_revision": preflight["revision"],
        "preflight_fingerprint": preflight["fingerprint"],
        "acknowledge_quality": True,
    }


def test_raster_dpi_uses_cropped_native_pixels_and_is_rotation_invariant(composition):
    service, sheet, item, source, _analysis, _user = composition
    assert state(service, sheet)["items"][0]["quality"]["effective_dpi"] == 300
    source.crop_width = Decimal("0.5")
    source.save()
    for rotation in (0, 90, 180, 270):
        item.rotation = rotation
        item.save()
        quality = state(service, sheet)["items"][0]["quality"]
        assert quality["effective_dpi"] == 150
        assert quality["source_width_px"] == 150
        assert quality["source_ratio"] == 1
    item.width_mm /= 2
    item.save()
    assert state(service, sheet)["items"][0]["quality"]["effective_dpi"] == 300


@pytest.mark.parametrize("vector,display", [(True, "Vectoriel"), (False, "Non déterminé")])
def test_pdf_never_uses_preview_pixels_as_a_global_dpi(composition, vector, display):
    service, sheet, _item, _source, analysis, _user = composition
    version = analysis.version
    version.mime_type = "application/pdf"
    version.save()
    analysis.metadata = {"is_pure_vector": vector, "placement_effective_dpi": 72}
    if vector:
        analysis.warnings = [
            "Document vectoriel ou sans image embarquée : résolution non applicable."
        ]
    analysis.save()
    result = state(service, sheet)
    quality = result["items"][0]["quality"]
    assert quality["effective_dpi"] is None
    assert quality["resolution_display"] == display
    assert not result["preflight"]["requires_acknowledgement"]


def test_warnings_require_current_explicit_ack_and_are_audited(composition):
    service, sheet, _item, _source, analysis, user = composition
    analysis.warnings = ["Fond blanc probable détecté."]
    analysis.save()
    mark_ready(sheet)
    preflight = state(service, sheet)["preflight"]
    with pytest.raises(GangSheetDomainError, match="Actualisez"):
        service.validate_sheet(sheet=sheet, actor=user)
    payload = acknowledgement(preflight)
    with pytest.raises(GangSheetDomainError, match="avertissements"):
        service.validate_sheet(sheet=sheet, actor=user, **{**payload, "acknowledge_quality": False})
    assert not AuditLogEntry.objects.filter(action="gang_sheet.preflight_accepted").exists()
    service.validate_sheet(sheet=sheet, actor=user, **payload)
    assert state(service, sheet)["status"] == "validated"
    event = AuditLogEntry.objects.get(action="gang_sheet.preflight_accepted")
    assert event.metadata["fingerprint"] == preflight["fingerprint"]
    assert event.metadata["warning_codes"] == ["source_warning"]


@pytest.mark.parametrize("change", ["analysis", "crop", "layout", "revision"])
def test_old_acceptance_cannot_confirm_a_changed_composition(composition, change):
    service, sheet, item, source, analysis, user = composition
    analysis.warnings = ["À contrôler"]
    analysis.save()
    mark_ready(sheet)
    payload = acknowledgement(state(service, sheet)["preflight"])
    if change == "analysis":
        analysis.warnings.append("Nouvel avertissement")
        analysis.save()
    elif change == "crop":
        source.crop_width = Decimal("0.5")
        source.save()
    elif change == "layout":
        item.width_mm += 1
        item.save()
    else:
        sheet.revision += 1
        sheet.save()
    with pytest.raises(GangSheetDomainError) as error:
        service.validate_sheet(sheet=sheet, actor=user, **payload)
    assert error.value.code == "STALE_PREFLIGHT"
    assert state(service, sheet)["status"] == "ready"


def test_source_pending_cannot_be_confirmed(composition):
    service, sheet, _item, _source, analysis, user = composition
    version = analysis.version
    version.analysis_status = "processing"
    version.save()
    mark_ready(sheet)
    with pytest.raises(GangSheetDomainError) as error:
        service.validate_sheet(sheet=sheet, actor=user)
    assert error.value.code == "PREFLIGHT_BLOCKED"


def test_stale_revision_is_rejected_even_without_quality_warnings(composition):
    service, sheet, _item, _source, _analysis, user = composition
    mark_ready(sheet)
    with pytest.raises(GangSheetDomainError) as error:
        service.validate_sheet(sheet=sheet, actor=user, expected_revision=sheet.revision - 1)
    assert error.value.code == "STALE_PREFLIGHT"


def test_incoherent_cross_customer_item_never_exposes_source_quality(composition):
    service, sheet, item, _source, _analysis, user = composition
    outsider, customer_b, project_b = create_customer_scope(email="private-preflight@example.com")
    _asset, version_b = attach_png_asset(customer=customer_b, project=project_b, user=outsider)
    AssetAnalysis.objects.create(
        customer=customer_b,
        version=version_b,
        warnings=["PRIVATE_OTHER_CUSTOMER"],
    )
    type(item).objects.filter(pk=item.pk).update(customer=customer_b, asset_version=version_b)
    result = state(service, sheet)
    assert "PRIVATE_OTHER_CUSTOMER" not in str(result)
    assert result["items"] == []
    assert result["preflight"]["blocking"][0]["code"] == "source_unavailable"
    mark_ready(sheet)
    with pytest.raises(GangSheetDomainError) as error:
        service.validate_sheet(sheet=sheet, actor=user)
    assert error.value.code == "PREFLIGHT_BLOCKED"


@pytest.mark.parametrize("mime", ["image/vnd.adobe.photoshop", "image/webp", "image/bmp"])
def test_reencoded_rasters_do_not_claim_a_production_dpi(composition, mime):
    service, sheet, _item, _source, analysis, _user = composition
    version = analysis.version
    version.mime_type = mime
    version.save()
    assert state(service, sheet)["items"][0]["quality"]["effective_dpi"] is None


def test_validate_endpoint_enforces_ack_and_existing_customer_permissions(composition, client):
    service, sheet, _item, _source, analysis, user = composition
    analysis.warnings = ["Fond blanc probable détecté."]
    analysis.save()
    mark_ready(sheet)
    preflight = state(service, sheet)["preflight"]
    url = reverse(
        "portal:client-gang-sheet-workflow-action",
        kwargs={
            "customer_public_id": sheet.customer.public_id,
            "sheet_public_id": sheet.public_id,
            "action": "validate",
        },
    )
    client.force_login(user)
    payload = {**acknowledgement(preflight), "acknowledge_quality": "false"}
    assert client.post(url, payload).status_code == 400
    outsider, _customer, _project = create_customer_scope(email="outsider-preflight@example.com")
    client.force_login(outsider)
    assert client.post(url, payload).status_code in (403, 404)
    CustomerMembership.objects.filter(user=user, customer=sheet.customer).update(
        role=CustomerMembership.Role.READONLY
    )
    client.force_login(user)
    payload["acknowledge_quality"] = "true"
    assert client.post(url, payload).status_code == 403
    CustomerMembership.objects.filter(user=user, customer=sheet.customer).update(
        role=CustomerMembership.Role.OWNER
    )
    assert client.post(url, payload).status_code == 200
