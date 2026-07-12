from django.urls import path

from .views import (
    ClientB2BOrderProjectCancelView,
    ClientB2BOrderProjectDetailView,
    ClientB2BOrderProjectItemAnalysisConfirmView,
    ClientB2BOrderProjectItemAssetDownloadView,
    ClientB2BOrderProjectItemAssetReplaceView,
    ClientB2BOrderProjectItemAssetView,
    ClientB2BOrderProjectItemCreateView,
    ClientB2BOrderProjectItemDetailView,
    ClientB2BOrderProjectItemDuplicateView,
    ClientB2BOrderProjectItemReorderView,
    ClientB2BOrderProjectListCreateView,
    ClientB2BOrderProjectSubmitView,
    StaffB2BOrderProjectDetailView,
    StaffB2BOrderProjectItemAssetDownloadView,
    StaffB2BOrderProjectListView,
)

app_name = "b2b_order_projects"

client_base = "api/client/customers/<uuid:customer_public_id>/order-projects/"

urlpatterns = [
    path(client_base, ClientB2BOrderProjectListCreateView.as_view(), name="client-list-create"),
    path(
        f"{client_base}<uuid:project_public_id>/",
        ClientB2BOrderProjectDetailView.as_view(),
        name="client-detail",
    ),
    path(
        f"{client_base}<uuid:project_public_id>/items/",
        ClientB2BOrderProjectItemCreateView.as_view(),
        name="client-item-create",
    ),
    path(
        f"{client_base}<uuid:project_public_id>/items/<uuid:item_public_id>/",
        ClientB2BOrderProjectItemDetailView.as_view(),
        name="client-item-detail",
    ),
    path(
        f"{client_base}<uuid:project_public_id>/items/<uuid:item_public_id>/duplicate/",
        ClientB2BOrderProjectItemDuplicateView.as_view(),
        name="client-item-duplicate",
    ),
    path(
        f"{client_base}<uuid:project_public_id>/items/<uuid:item_public_id>/confirm-analysis/",
        ClientB2BOrderProjectItemAnalysisConfirmView.as_view(),
        name="client-item-confirm-analysis",
    ),
    path(
        f"{client_base}<uuid:project_public_id>/items/<uuid:item_public_id>/asset/",
        ClientB2BOrderProjectItemAssetView.as_view(),
        name="client-item-asset",
    ),
    path(
        f"{client_base}<uuid:project_public_id>/items/<uuid:item_public_id>/asset/replace/",
        ClientB2BOrderProjectItemAssetReplaceView.as_view(),
        name="client-item-asset-replace",
    ),
    path(
        f"{client_base}<uuid:project_public_id>/items/<uuid:item_public_id>/asset/download/",
        ClientB2BOrderProjectItemAssetDownloadView.as_view(),
        name="client-item-asset-download",
    ),
    path(
        f"{client_base}<uuid:project_public_id>/items/reorder/",
        ClientB2BOrderProjectItemReorderView.as_view(),
        name="client-item-reorder",
    ),
    path(
        f"{client_base}<uuid:project_public_id>/submit/",
        ClientB2BOrderProjectSubmitView.as_view(),
        name="client-submit",
    ),
    path(
        f"{client_base}<uuid:project_public_id>/cancel/",
        ClientB2BOrderProjectCancelView.as_view(),
        name="client-cancel",
    ),
    path("api/staff/order-projects/", StaffB2BOrderProjectListView.as_view(), name="staff-list"),
    path(
        "api/staff/order-projects/<uuid:project_public_id>/",
        StaffB2BOrderProjectDetailView.as_view(),
        name="staff-detail",
    ),
    path(
        "api/staff/order-projects/<uuid:project_public_id>/items/<uuid:item_public_id>/asset/download/",
        StaffB2BOrderProjectItemAssetDownloadView.as_view(),
        name="staff-item-asset-download",
    ),
]
