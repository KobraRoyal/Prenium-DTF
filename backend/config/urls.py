from django.conf import settings
from django.urls import include, path, re_path
from django.views.static import serve

from .admin import restricted_admin_site

urlpatterns = [
    path("admin/", restricted_admin_site.urls),
    path("", include("apps.core.urls")),
    path("", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("", include(("apps.billing.urls", "billing"), namespace="billing")),
    path(
        "",
        include(
            ("apps.b2b_order_projects.urls", "b2b_order_projects"),
            namespace="b2b_order_projects",
        ),
    ),
    path("", include(("apps.catalog.urls", "catalog"), namespace="catalog")),
    path("", include(("apps.orders.urls", "orders"), namespace="orders")),
    path("", include(("apps.portal.urls", "portal"), namespace="portal")),
    path("", include(("apps.prospects.urls", "prospects"), namespace="prospects")),
    path("", include(("apps.production.urls", "production"), namespace="production")),
    path("", include(("apps.shipping.urls", "shipping"), namespace="shipping")),
    path("", include(("apps.uploads.urls", "uploads"), namespace="uploads")),
]

handler404 = "django.views.defaults.page_not_found"

# Prod NAS: serve static from static_src when the shared volume is empty/out of sync.
# Prefer nginx alias when available; this is the Django fallback.
_static_root = settings.BASE_DIR / "static_src"
if _static_root.is_dir():
    urlpatterns += [
        re_path(
            r"^static/(?P<path>.*)$",
            serve,
            {"document_root": str(_static_root), "show_indexes": False},
        ),
    ]
