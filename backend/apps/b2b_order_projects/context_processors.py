from django.conf import settings


def b2b_order_project_flags(request):
    return {
        "b2b_order_projects_globally_enabled": getattr(
            settings, "B2B_DTF_ORDER_PROJECT_ENABLED", False
        )
    }
