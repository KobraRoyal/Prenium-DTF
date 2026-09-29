from types import SimpleNamespace
from uuid import uuid4

import pytest
from apps.pod.services.variant_config_contract import VariantConfigPayload
from apps.portal import views_staff_pod_catalog
from django.template.loader import render_to_string
from django.test import RequestFactory


def test_payload_keeps_one_drive_file_id_per_mapping_row():
    request = RequestFactory().post(
        "/staff/pod/variant/drawer/",
        {
            "mode": "pod",
            "blank_variant_public_id": str(uuid4()),
            "slot_placement": ["front", "back"],
            "slot_technique_public_id": [str(uuid4()), str(uuid4())],
            "slot_source_drive_file_id": ["drive-front", "drive-back"],
            "slot_source_asset_version_public_id": ["", ""],
        },
    )

    payload = views_staff_pod_catalog.StaffPodVariantConfigDrawerView._payload_from_post(request)

    assert [slot.source_drive_file_id for slot in payload.slots] == [
        "drive-front",
        "drive-back",
    ]


@pytest.mark.parametrize(
    ("submitted_file_id", "expected_file_id"),
    [("allowed-drive-file", "allowed-drive-file"), ("foreign-drive-file", "")],
)
def test_draft_context_keeps_only_drive_option_returned_by_service(
    monkeypatch, submitted_file_id, expected_file_id
):
    technique_id = str(uuid4())
    config = SimpleNamespace(mode="unmanaged", finished_sku="", staff_locked=False)
    context = {
        "config": config,
        "slot_rows": [
            {
                "placement": "front",
                "technique": SimpleNamespace(public_id=technique_id),
                "is_required": True,
                "asset_options": [],
                "drive_options": [SimpleNamespace(file_id="allowed-drive-file")],
            }
        ],
    }
    service = SimpleNamespace(
        drawer_context=lambda **_kwargs: context,
        configuration_status=lambda _config: "needs_config",
    )
    monkeypatch.setattr(views_staff_pod_catalog, "variant_config_service", service)
    payload = VariantConfigPayload.from_mapping(
        {
            "mode": "pod",
            "blank_variant_public_id": str(uuid4()),
            "slots": [
                {
                    "placement": "front",
                    "technique_public_id": technique_id,
                    "source_drive_file_id": submitted_file_id,
                }
            ],
        }
    )

    result = views_staff_pod_catalog.StaffPodVariantConfigDrawerView()._draft_context(
        request=SimpleNamespace(user=object()),
        variant=object(),
        payload=payload,
    )

    assert result["slot_rows"][0]["source_drive_file_id"] == expected_file_id


def test_drive_picker_renders_explicit_empty_state_and_legacy_choice():
    technique_id = uuid4()
    context = {
        "config": SimpleNamespace(
            mode="pod",
            blank_variant_id=1,
            blank_variant=SimpleNamespace(blank=SimpleNamespace(name="T-shirt")),
        ),
        "variant": SimpleNamespace(public_id=uuid4()),
        "drive_source_configured": True,
        "drive_source_error": "",
        "drive_source_folder_url": "https://drive.google.com/drive/folders/drive_hd_folder_123",
        "mapping_rows": [
            {
                "placement": "front",
                "placement_label": "Face",
                "technique": SimpleNamespace(
                    public_id=technique_id,
                    name="DTF",
                    export_extension=".png",
                ),
                "mapping_key": f"front:{technique_id}",
                "is_required": True,
                "print_reference": "",
                "source_drive_file_id": "",
                "source_asset_version_public_id": "",
                "drive_options": [],
                "asset_options": [],
            }
        ],
        "mapping_zones": [],
        "slot_rows": [object()],
    }

    rendered = render_to_string("portal/staff/pod/_mapping_marques.html", context)

    assert "Le dossier Drive HD source est vide" in rendered
    assert "Ouvrir le dossier HD Drive" in rendered
    assert "https://drive.google.com/drive/folders/drive_hd_folder_123" in rendered
    assert "sourceKind: ''" in rendered
    assert "Google Drive — dossier HD source" in rendered
    assert "Archive locale — option historique" in rendered
    assert 'name="slot_source_drive_file_id"' in rendered
    assert 'name="slot_source_asset_version_public_id"' in rendered
    assert "sourceKind === 'drive' ? driveFileId : ''" in rendered
    assert "sourceKind === 'local' ? assetVersionId : ''" in rendered
