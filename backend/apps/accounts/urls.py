from django.urls import path

from .views import ClientScopeView, CustomerOwnerView, ScopedCustomerView, StaffPortalView

app_name = "accounts"

urlpatterns = [
    path("api/client/me/", ClientScopeView.as_view(), name="client-me"),
    path(
        "api/client/customers/<uuid:customer_public_id>/",
        ScopedCustomerView.as_view(),
        name="client-customer-detail",
    ),
    path(
        "api/client/customers/<uuid:customer_public_id>/owner-zone/",
        CustomerOwnerView.as_view(),
        name="client-customer-owner-zone",
    ),
    path("api/staff/me/", StaffPortalView.as_view(), name="staff-me"),
]
