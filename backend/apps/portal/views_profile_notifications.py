from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View

from apps.notifications.services.preferences import user_email_preference_service


class PortalEmailNotificationPreferenceView(LoginRequiredMixin, View):
    """Save the signed-in user's optional email mutes. No other account is addressable."""

    def post(self, request):
        space = request.POST.get("space", "client")
        if space not in {"client", "staff"}:
            space = "client"
        user_email_preference_service.replace_mutes(
            user=request.user,
            enabled_events=request.POST.getlist("enabled_events"),
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        profile_url = reverse("portal:profile")
        return redirect(f"{profile_url}?space={space}&notifications_saved=1#account-notifications")
