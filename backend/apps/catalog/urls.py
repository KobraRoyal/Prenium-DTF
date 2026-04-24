from django.urls import path

from .views import ClientCatalogServiceListView, StaffCatalogServiceListView

app_name = "catalog"

urlpatterns = [
    path(
        "api/client/customers/<uuid:customer_public_id>/catalog/services/",
        ClientCatalogServiceListView.as_view(),
        name="client-service-list",
    ),
    path(
        "api/staff/catalog/services/",
        StaffCatalogServiceListView.as_view(),
        name="staff-service-list",
    ),
]

