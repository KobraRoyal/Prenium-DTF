from django.urls import path

from .views import (
    ClientOrderDetailView,
    ClientOrderListCreateView,
    StaffOrderDetailView,
    StaffOrderListView,
)

app_name = "orders"

urlpatterns = [
    path(
        "api/client/customers/<uuid:customer_public_id>/orders/",
        ClientOrderListCreateView.as_view(),
        name="client-order-list-create",
    ),
    path(
        "api/client/customers/<uuid:customer_public_id>/orders/<uuid:order_public_id>/",
        ClientOrderDetailView.as_view(),
        name="client-order-detail",
    ),
    path("api/staff/orders/", StaffOrderListView.as_view(), name="staff-order-list"),
    path(
        "api/staff/orders/<uuid:order_public_id>/",
        StaffOrderDetailView.as_view(),
        name="staff-order-detail",
    ),
]
