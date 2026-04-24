from django.urls import include, path

from .admin import restricted_admin_site

urlpatterns = [
    path("admin/", restricted_admin_site.urls),
    path("", include("apps.core.urls")),
    path("", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("", include(("apps.billing.urls", "billing"), namespace="billing")),
    path("", include(("apps.catalog.urls", "catalog"), namespace="catalog")),
    path("", include(("apps.orders.urls", "orders"), namespace="orders")),
    path("", include(("apps.portal.urls", "portal"), namespace="portal")),
    path("", include(("apps.prospects.urls", "prospects"), namespace="prospects")),
    path("", include(("apps.production.urls", "production"), namespace="production")),
    path("", include(("apps.shipping.urls", "shipping"), namespace="shipping")),
    path("", include(("apps.uploads.urls", "uploads"), namespace="uploads")),
]
