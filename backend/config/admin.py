from django.contrib import admin


class RestrictedAdminSite(admin.AdminSite):
    site_header = "Prenium DTF Administration"
    site_title = "Prenium DTF Admin"
    index_title = "Technical administration"

    def has_permission(self, request) -> bool:
        return bool(
            request.user.is_active and request.user.is_authenticated and request.user.is_superuser
        )


admin.site.__class__ = RestrictedAdminSite
restricted_admin_site = admin.site
