from django.conf import settings


def b2b_order_project_flags(request):
    return {
        "b2b_order_projects_globally_enabled": getattr(
            settings, "B2B_DTF_ORDER_PROJECT_ENABLED", False
        ),
        "b2b_recommended_dpi": int(getattr(settings, "B2B_RECOMMENDED_DPI", 300)),
        "b2b_min_acceptable_dpi": int(getattr(settings, "B2B_MIN_ACCEPTABLE_DPI", 200)),
    }
