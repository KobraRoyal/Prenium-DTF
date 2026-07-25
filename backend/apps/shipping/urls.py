from django.urls import path

from .views import (
    BackendSendcloudWebhookView,
    ClientShipmentDetailView,
    StaffShipmentCreateView,
    StaffShipmentDetailView,
    StaffShipmentLabelDownloadView,
    StaffShipmentSyncTrackingView,
)

app_name = "shipping"

urlpatterns = [
    path(
        "api/backend/sendcloud/webhook/",
        BackendSendcloudWebhookView.as_view(),
        name="backend-sendcloud-webhook",
    ),
    path(
        "api/client/customers/<uuid:customer_public_id>/orders/<uuid:order_public_id>/shipment/",
        ClientShipmentDetailView.as_view(),
        name="client-shipment-detail",
    ),
    path(
        "api/staff/shipping/orders/<uuid:order_public_id>/sync-tracking/",
        StaffShipmentSyncTrackingView.as_view(),
        name="staff-shipment-sync-tracking",
    ),
    path(
        "api/staff/shipping/orders/<uuid:order_public_id>/label/",
        StaffShipmentLabelDownloadView.as_view(),
        name="staff-shipment-label-download",
    ),
    path(
        "api/staff/shipping/orders/<uuid:order_public_id>/",
        StaffShipmentDetailView.as_view(),
        name="staff-shipment-detail",
    ),
    path(
        "api/staff/shipping/orders/<uuid:order_public_id>/create/",
        StaffShipmentCreateView.as_view(),
        name="staff-shipment-create",
    ),
]
