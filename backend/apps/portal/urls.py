from django.urls import path

from .views_auth import PortalLoginView, PortalLogoutView
from .views_checkout import (
    ClientCheckoutSubmitView,
    ClientCheckoutSummaryPartialView,
    ClientCheckoutUploadPartialView,
    ClientCheckoutView,
)
from .views_client import (
    ClientDashboardView,
    ClientOrderDetailView,
    ClientOrderListView,
    ClientOrderPanelBillingView,
    ClientOrderPanelInspectionView,
    ClientOrderPanelProductionView,
    ClientOrderPanelShippingView,
    ClientOrderPanelUploadsView,
)
from .views_staff import (
    StaffDashboardView,
    StaffOrderDetailView,
    StaffOrderListView,
    StaffOrderPriceView,
)
from .views_staff_billing import StaffInvoiceMarkPaidView, StaffOrderPanelBillingView
from .views_staff_production import StaffOrderPanelProductionView, StaffOrderPanelScanView
from .views_staff_shipping import StaffOrderPanelShippingSyncView, StaffOrderPanelShippingView
from .views_staff_uploads import (
    StaffOrderPanelDriveSyncView,
    StaffOrderPanelInspectionView,
    StaffOrderPanelUploadsView,
)

app_name = "portal"

urlpatterns = [
    path("login/", PortalLoginView.as_view(), name="login"),
    path("logout/", PortalLogoutView.as_view(), name="logout"),
    path("client/", ClientDashboardView.as_view(), name="client-dashboard"),
    path(
        "client/customers/<uuid:customer_public_id>/orders/",
        ClientOrderListView.as_view(),
        name="client-order-list",
    ),
    path(
        "client/customers/<uuid:customer_public_id>/orders/<uuid:order_public_id>/",
        ClientOrderDetailView.as_view(),
        name="client-order-detail",
    ),
    path(
        "client/customers/<uuid:customer_public_id>/orders/<uuid:order_public_id>/panels/uploads/",
        ClientOrderPanelUploadsView.as_view(),
        name="client-order-panel-uploads",
    ),
    path(
        "client/customers/<uuid:customer_public_id>/orders/<uuid:order_public_id>/panels/inspection/",
        ClientOrderPanelInspectionView.as_view(),
        name="client-order-panel-inspection",
    ),
    path(
        "client/customers/<uuid:customer_public_id>/orders/<uuid:order_public_id>/panels/production/",
        ClientOrderPanelProductionView.as_view(),
        name="client-order-panel-production",
    ),
    path(
        "client/customers/<uuid:customer_public_id>/orders/<uuid:order_public_id>/panels/shipping/",
        ClientOrderPanelShippingView.as_view(),
        name="client-order-panel-shipping",
    ),
    path(
        "client/customers/<uuid:customer_public_id>/orders/<uuid:order_public_id>/panels/billing/",
        ClientOrderPanelBillingView.as_view(),
        name="client-order-panel-billing",
    ),
    path(
        "client/customers/<uuid:customer_public_id>/checkout/",
        ClientCheckoutView.as_view(),
        name="client-checkout",
    ),
    path(
        "client/customers/<uuid:customer_public_id>/checkout/upload/",
        ClientCheckoutUploadPartialView.as_view(),
        name="client-checkout-upload",
    ),
    path(
        "client/customers/<uuid:customer_public_id>/checkout/summary/",
        ClientCheckoutSummaryPartialView.as_view(),
        name="client-checkout-summary",
    ),
    path(
        "client/customers/<uuid:customer_public_id>/checkout/submit/",
        ClientCheckoutSubmitView.as_view(),
        name="client-checkout-submit",
    ),
    path("staff/", StaffDashboardView.as_view(), name="staff-dashboard"),
    path("staff/orders/", StaffOrderListView.as_view(), name="staff-order-list"),
    path(
        "staff/orders/<uuid:order_public_id>/",
        StaffOrderDetailView.as_view(),
        name="staff-order-detail",
    ),
    path(
        "staff/orders/<uuid:order_public_id>/price/",
        StaffOrderPriceView.as_view(),
        name="staff-order-price",
    ),
    path(
        "staff/orders/<uuid:order_public_id>/panels/uploads/",
        StaffOrderPanelUploadsView.as_view(),
        name="staff-order-panel-uploads",
    ),
    path(
        "staff/orders/<uuid:order_public_id>/panels/inspection/",
        StaffOrderPanelInspectionView.as_view(),
        name="staff-order-panel-inspection",
    ),
    path(
        "staff/orders/<uuid:order_public_id>/panels/drive-sync/",
        StaffOrderPanelDriveSyncView.as_view(),
        name="staff-order-panel-drive-sync",
    ),
    path(
        "staff/orders/<uuid:order_public_id>/panels/production/",
        StaffOrderPanelProductionView.as_view(),
        name="staff-order-panel-production",
    ),
    path(
        "staff/orders/<uuid:order_public_id>/panels/shipping/sync/",
        StaffOrderPanelShippingSyncView.as_view(),
        name="staff-order-panel-shipping-sync",
    ),
    path(
        "staff/orders/<uuid:order_public_id>/panels/shipping/",
        StaffOrderPanelShippingView.as_view(),
        name="staff-order-panel-shipping",
    ),
    path(
        "staff/orders/<uuid:order_public_id>/panels/scan/",
        StaffOrderPanelScanView.as_view(),
        name="staff-order-panel-scan",
    ),
    path(
        "staff/orders/<uuid:order_public_id>/panels/billing/",
        StaffOrderPanelBillingView.as_view(),
        name="staff-order-panel-billing",
    ),
    path(
        "staff/orders/<uuid:order_public_id>/invoice/mark-paid/",
        StaffInvoiceMarkPaidView.as_view(),
        name="staff-order-invoice-mark-paid",
    ),
]
