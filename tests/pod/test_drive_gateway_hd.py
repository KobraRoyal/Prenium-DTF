import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from apps.uploads.services.drive import (
    DriveRemoteFile,
    GoogleDriveGateway,
    GoogleDriveSyncError,
)


def _gateway(*, response=None, error=None):
    gateway = object.__new__(GoogleDriveGateway)
    gateway.shared_drive_id = "shared-drive"
    gateway.root_folder_id = "root-folder"
    gateway.service = MagicMock()
    request = gateway.service.files.return_value.list.return_value
    if error is not None:
        request.execute.side_effect = error
    else:
        request.execute.return_value = response or {}
    return gateway


def test_list_binary_files_returns_typed_page_and_forwards_pagination():
    gateway = _gateway(
        response={
            "nextPageToken": "next-page",
            "files": [
                {
                    "id": "file-1",
                    "name": "print.pdf",
                    "mimeType": "application/pdf",
                    "size": "1234",
                    "webViewLink": "https://drive.test/file-1",
                    "md5Checksum": "abc123",
                    "parents": ["parent-1"],
                    "driveId": "shared-drive",
                }
            ],
        }
    )

    files, next_page_token = gateway.list_binary_files(
        parent_id="parent-1",
        page_token="current-page",
        page_size=25,
    )

    assert files == [
        DriveRemoteFile(
            file_id="file-1",
            name="print.pdf",
            mime_type="application/pdf",
            size=1234,
            web_view_link="https://drive.test/file-1",
            md5_checksum="abc123",
            parents=("parent-1",),
            drive_id="shared-drive",
        )
    ]
    assert next_page_token == "next-page"
    kwargs = gateway.service.files.return_value.list.call_args.kwargs
    assert kwargs["corpora"] == "drive"
    assert kwargs["driveId"] == "shared-drive"
    assert kwargs["includeItemsFromAllDrives"] is True
    assert kwargs["supportsAllDrives"] is True
    assert kwargs["pageToken"] == "current-page"
    assert kwargs["pageSize"] == 25
    assert "nextPageToken" in kwargs["fields"]
    assert "md5Checksum" in kwargs["fields"]


def test_list_binary_files_escapes_search_and_parent_query_literals():
    gateway = _gateway()

    gateway.list_binary_files(parent_id="parent\\'one", search="client\\'s file")

    query = gateway.service.files.return_value.list.call_args.kwargs["q"]
    assert "'parent\\\\\\'one' in parents" in query
    assert "name contains 'client\\\\\\'s file'" in query
    assert "application/vnd.google-apps.folder" in query
    assert "application/vnd.google-apps.shortcut" in query


def test_list_binary_files_supports_explicit_name_contains_alias():
    gateway = _gateway()

    gateway.list_binary_files(parent_id="confirmed-source", name_contains="order-123")

    query = gateway.service.files.return_value.list.call_args.kwargs["q"]
    assert "'confirmed-source' in parents" in query
    assert "name contains 'order-123'" in query


def test_list_binary_files_rejects_non_binary_or_wrong_scope_results():
    gateway = _gateway(
        response={
            "files": [
                {
                    "id": "folder",
                    "name": "Folder",
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": ["parent-1"],
                    "driveId": "shared-drive",
                },
                {
                    "id": "shortcut",
                    "name": "Shortcut",
                    "mimeType": "application/vnd.google-apps.shortcut",
                    "parents": ["parent-1"],
                    "driveId": "shared-drive",
                },
                {
                    "id": "doc",
                    "name": "Native Doc",
                    "mimeType": "application/vnd.google-apps.document",
                    "parents": ["parent-1"],
                    "driveId": "shared-drive",
                },
                {
                    "id": "wrong-parent",
                    "name": "Wrong parent.pdf",
                    "mimeType": "application/pdf",
                    "parents": ["another-parent"],
                    "driveId": "shared-drive",
                },
                {
                    "id": "wrong-drive",
                    "name": "Wrong drive.pdf",
                    "mimeType": "application/pdf",
                    "parents": ["parent-1"],
                    "driveId": "another-drive",
                },
                {
                    "id": "valid",
                    "name": "Valid.pdf",
                    "mimeType": "application/pdf",
                    "parents": ["parent-1"],
                    "driveId": "shared-drive",
                },
            ]
        }
    )

    files, next_page_token = gateway.list_binary_files(parent_id="parent-1")

    assert [item.file_id for item in files] == ["valid"]
    assert next_page_token is None


@pytest.mark.parametrize("page_size", [0, 101, True, 1.5])
def test_list_binary_files_validates_page_size(page_size):
    gateway = _gateway()

    with pytest.raises(ValueError, match="page_size"):
        gateway.list_binary_files(parent_id="parent-1", page_size=page_size)

    gateway.service.files.return_value.list.assert_not_called()


def test_list_binary_files_wraps_drive_errors():
    gateway = _gateway(error=RuntimeError("HTTP 503"))

    with pytest.raises(GoogleDriveSyncError, match="list Drive binary files"):
        gateway.list_binary_files(parent_id="parent-1")


def test_get_file_metadata_requests_extended_fields_without_changing_result_shape():
    gateway = _gateway()
    metadata = {
        "id": "file-1",
        "name": "print.pdf",
        "mimeType": "application/pdf",
        "size": "12",
        "webViewLink": "https://drive.test/file-1",
        "md5Checksum": "checksum",
        "version": "17",
        "parents": ["parent-1"],
        "driveId": "shared-drive",
        "trashed": False,
    }
    gateway.service.files.return_value.get.return_value.execute.return_value = metadata

    assert gateway.get_file_metadata("file-1") == metadata
    kwargs = gateway.service.files.return_value.get.call_args.kwargs
    assert kwargs["fileId"] == "file-1"
    assert kwargs["supportsAllDrives"] is True
    assert "size" in kwargs["fields"]
    assert "webViewLink" in kwargs["fields"]
    assert "md5Checksum" in kwargs["fields"]
    assert "version" in kwargs["fields"]
    assert "driveId" in kwargs["fields"]


def test_copy_file_uses_shared_drive_copy_contract():
    gateway = _gateway()
    gateway.find_file_by_name = MagicMock(return_value=None)
    gateway.service.files.return_value.copy.return_value.execute.return_value = {
        "id": "copy-1",
        "name": "target.pdf",
        "parents": ["target-folder"],
    }

    copied = gateway.copy_file(
        source_file_id="source-1",
        target_folder_id="target-folder",
        target_name="target.pdf",
    )

    assert copied == DriveRemoteFile(
        file_id="copy-1",
        name="target.pdf",
        parents=("target-folder",),
    )
    gateway.service.files.return_value.copy.assert_called_once_with(
        fileId="source-1",
        body={"name": "target.pdf", "parents": ["target-folder"]},
        fields="id,name,parents",
        supportsAllDrives=True,
    )


def test_copy_file_is_idempotent_when_target_name_already_exists():
    gateway = _gateway()
    existing = DriveRemoteFile(file_id="existing-1", name="target.pdf")
    gateway.find_file_by_name = MagicMock(return_value=existing)
    gateway.get_file_metadata = MagicMock(
        side_effect=[
            {"id": "source-1", "md5Checksum": "same-checksum"},
            {
                "id": "existing-1",
                "md5Checksum": "same-checksum",
                "parents": ["target-folder"],
                "driveId": "shared-drive",
            },
        ]
    )

    copied = gateway.copy_file(
        source_file_id="source-1",
        target_folder_id="target-folder",
        target_name="target.pdf",
    )

    assert copied is existing
    gateway.service.files.return_value.copy.assert_not_called()


def test_copy_file_rejects_same_name_from_another_source():
    gateway = _gateway()
    gateway.find_file_by_name = MagicMock(
        return_value=DriveRemoteFile(file_id="existing-1", name="target.pdf")
    )
    gateway.get_file_metadata = MagicMock(
        side_effect=[
            {"id": "source-1", "md5Checksum": "source-checksum"},
            {
                "id": "existing-1",
                "md5Checksum": "different-checksum",
                "parents": ["target-folder"],
                "driveId": "shared-drive",
            },
        ]
    )
    with pytest.raises(GoogleDriveSyncError, match="target name collision"):
        gateway.copy_file(
            source_file_id="source-1",
            target_folder_id="target-folder",
            target_name="target.pdf",
        )

    gateway.service.files.return_value.copy.assert_not_called()


def test_copy_file_recovers_when_concurrent_copy_created_the_target():
    gateway = _gateway()
    existing = DriveRemoteFile(file_id="existing-1", name="target.pdf")
    gateway.find_file_by_name = MagicMock(side_effect=[None, existing])
    gateway.get_file_metadata = MagicMock(
        side_effect=[
            {"id": "source-1", "md5Checksum": "same-checksum"},
            {
                "id": "existing-1",
                "md5Checksum": "same-checksum",
                "parents": ["target-folder"],
                "driveId": "shared-drive",
            },
        ]
    )
    gateway.service.files.return_value.copy.return_value.execute.side_effect = RuntimeError(
        "HTTP 409"
    )

    copied = gateway.copy_file(
        source_file_id="source-1",
        target_folder_id="target-folder",
        target_name="target.pdf",
    )

    assert copied is existing


def test_copy_file_wraps_drive_errors_when_no_idempotent_target_exists():
    gateway = _gateway()
    gateway.find_file_by_name = MagicMock(return_value=None)
    gateway.service.files.return_value.copy.return_value.execute.side_effect = RuntimeError(
        "HTTP 503"
    )

    with pytest.raises(GoogleDriveSyncError, match="copy Drive file 'target.pdf'"):
        gateway.copy_file(
            source_file_id="source-1",
            target_folder_id="target-folder",
            target_name="target.pdf",
        )


def test_download_file_returns_rewound_anonymous_temporary_file(monkeypatch):
    gateway = _gateway()
    gateway.get_file_metadata = MagicMock(return_value={"size": "7"})
    downloader = MagicMock()

    class FakeMediaIoBaseDownload:
        def __init__(self, handle, request, chunksize):
            assert request is gateway.service.files.return_value.get_media.return_value
            assert chunksize == 8
            self.handle = handle

        def next_chunk(self):
            self.handle.write(b"payload")
            return None, True

    monkeypatch.setitem(
        sys.modules,
        "googleapiclient.http",
        SimpleNamespace(MediaIoBaseDownload=FakeMediaIoBaseDownload),
    )

    temporary_file = gateway.download_file(file_id="file-1", max_bytes=10, chunk_size=8)
    try:
        assert temporary_file.read() == b"payload"
        gateway.service.files.return_value.get_media.assert_called_once_with(
            fileId="file-1",
            supportsAllDrives=True,
        )
        downloader.assert_not_called()
    finally:
        temporary_file.close()


def test_download_file_rejects_declared_oversize_before_get_media():
    gateway = _gateway()
    gateway.get_file_metadata = MagicMock(return_value={"size": "11"})

    with pytest.raises(GoogleDriveSyncError, match="exceeds the allowed size"):
        gateway.download_file(file_id="file-1", max_bytes=10)

    gateway.service.files.return_value.get_media.assert_not_called()


def test_download_file_closes_temporary_file_when_stream_exceeds_limit(monkeypatch):
    gateway = _gateway()
    gateway.get_file_metadata = MagicMock(return_value={})
    temporary_file = MagicMock()
    temporary_file.tell.return_value = 11

    class FakeMediaIoBaseDownload:
        def __init__(self, handle, request, chunksize):
            self.handle = handle

        def next_chunk(self):
            return None, True

    monkeypatch.setattr(
        "apps.uploads.services.drive.tempfile.TemporaryFile",
        lambda **_: temporary_file,
    )
    monkeypatch.setitem(
        sys.modules,
        "googleapiclient.http",
        SimpleNamespace(MediaIoBaseDownload=FakeMediaIoBaseDownload),
    )

    with pytest.raises(GoogleDriveSyncError, match="exceeds the allowed size"):
        gateway.download_file(file_id="file-1", max_bytes=10)

    temporary_file.close.assert_called_once_with()
