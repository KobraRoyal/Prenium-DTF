from django.urls import path

from .views import (
    ClientOrderUploadDetailView,
    ClientOrderUploadDownloadView,
    ClientOrderUploadInspectionDetailView,
    ClientOrderUploadListCreateView,
    StaffOrderUploadDetailView,
    StaffOrderUploadDownloadView,
    StaffOrderUploadDriveSyncDetailView,
    StaffOrderUploadInspectionDetailView,
    StaffOrderUploadListView,
)

app_name = "uploads"

urlpatterns = [
    path(
        "api/client/customers/<uuid:customer_public_id>/orders/<uuid:order_public_id>/files/",
        ClientOrderUploadListCreateView.as_view(),
        name="client-order-upload-list-create",
    ),
    path(
        "api/client/customers/<uuid:customer_public_id>/orders/<uuid:order_public_id>/files/<uuid:file_public_id>/",
        ClientOrderUploadDetailView.as_view(),
        name="client-order-upload-detail",
    ),
    path(
        "api/client/customers/<uuid:customer_public_id>/orders/<uuid:order_public_id>/files/<uuid:file_public_id>/download/",
        ClientOrderUploadDownloadView.as_view(),
        name="client-order-upload-download",
    ),
    path(
        "api/client/customers/<uuid:customer_public_id>/orders/<uuid:order_public_id>/files/<uuid:file_public_id>/control/",
        ClientOrderUploadInspectionDetailView.as_view(),
        name="client-order-upload-inspection-detail",
    ),
    path(
        "api/staff/orders/<uuid:order_public_id>/files/",
        StaffOrderUploadListView.as_view(),
        name="staff-order-upload-list",
    ),
    path(
        "api/staff/orders/<uuid:order_public_id>/files/<uuid:file_public_id>/",
        StaffOrderUploadDetailView.as_view(),
        name="staff-order-upload-detail",
    ),
    path(
        "api/staff/orders/<uuid:order_public_id>/files/<uuid:file_public_id>/download/",
        StaffOrderUploadDownloadView.as_view(),
        name="staff-order-upload-download",
    ),
    path(
        "api/staff/orders/<uuid:order_public_id>/files/<uuid:file_public_id>/control/",
        StaffOrderUploadInspectionDetailView.as_view(),
        name="staff-order-upload-inspection-detail",
    ),
    path(
        "api/staff/orders/<uuid:order_public_id>/files/<uuid:file_public_id>/drive-sync/",
        StaffOrderUploadDriveSyncDetailView.as_view(),
        name="staff-order-upload-drive-sync-detail",
    ),
]
