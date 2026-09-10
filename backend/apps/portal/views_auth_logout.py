from __future__ import annotations

from django.contrib.auth.views import LogoutView
from django.core.exceptions import PermissionDenied

from apps.portal.views_common import access_scope_service


class PortalLogoutView(LogoutView):
    """End a portal session and revoke Push secrets for the signed-in staff user."""

    next_page = "/login/"

    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated and access_scope_service.can_access_staff_portal(
            request.user
        ):
            from apps.notifications.services.workshop_push import (
                WorkshopNotificationService,
            )

            try:
                WorkshopNotificationService().unsubscribe_all(
                    actor=request.user,
                    source="portal_logout",
                )
            except PermissionDenied:
                # A partially provisioned staff account must still be able to log out.
                pass
        return super().post(request, *args, **kwargs)
