from django import template

from apps.notifications.services.preferences import user_email_preference_service

register = template.Library()


@register.inclusion_tag(
    "portal/partials/profile_email_notifications.html",
    takes_context=True,
)
def profile_email_notifications(context):
    request = context["request"]
    return {
        "request": request,
        "choices": user_email_preference_service.visible_choices(user=request.user),
        "nav_mode": context.get("nav_mode") or "client",
        "notifications_saved": request.GET.get("notifications_saved") == "1",
    }
