from django.urls import path

from .views import (
    StaffManufacturingOrderPdfView,
    StaffProductionJobDetailView,
    StaffProductionJobTransitionView,
    StaffProductionScanResolveView,
    StaffProductionScanTransitionView,
)

app_name = "production"

urlpatterns = [
    path(
        "api/staff/production/orders/<uuid:order_public_id>/manufacturing-order.pdf",
        StaffManufacturingOrderPdfView.as_view(),
        name="staff-manufacturing-order-pdf",
    ),
    path(
        "api/staff/production/orders/<uuid:order_public_id>/",
        StaffProductionJobDetailView.as_view(),
        name="staff-production-job-detail",
    ),
    path(
        "api/staff/production/orders/<uuid:order_public_id>/transition/",
        StaffProductionJobTransitionView.as_view(),
        name="staff-production-job-transition",
    ),
    path(
        "api/staff/production/scans/resolve/",
        StaffProductionScanResolveView.as_view(),
        name="staff-production-job-scan-resolve",
    ),
    path(
        "api/staff/production/scans/transition/",
        StaffProductionScanTransitionView.as_view(),
        name="staff-production-job-scan-transition",
    ),
]
