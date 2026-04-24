from django.urls import path

from .views import (
    BackendPayPalCaptureView,
    ClientInvoiceDetailView,
    ClientInvoiceDownloadView,
    ClientPayPalPaymentInitiateView,
    StaffBillingDetailView,
)

app_name = "billing"

urlpatterns = [
    path(
        "api/client/customers/<uuid:customer_public_id>/orders/<uuid:order_public_id>/payments/paypal/initiate/",
        ClientPayPalPaymentInitiateView.as_view(),
        name="client-paypal-payment-initiate",
    ),
    path(
        "api/client/customers/<uuid:customer_public_id>/orders/<uuid:order_public_id>/invoice/",
        ClientInvoiceDetailView.as_view(),
        name="client-invoice-detail",
    ),
    path(
        "api/client/customers/<uuid:customer_public_id>/orders/<uuid:order_public_id>/invoice/download/",
        ClientInvoiceDownloadView.as_view(),
        name="client-invoice-download",
    ),
    path(
        "api/staff/billing/orders/<uuid:order_public_id>/",
        StaffBillingDetailView.as_view(),
        name="staff-billing-detail",
    ),
    path(
        "api/backend/paypal/capture/",
        BackendPayPalCaptureView.as_view(),
        name="backend-paypal-capture",
    ),
]

