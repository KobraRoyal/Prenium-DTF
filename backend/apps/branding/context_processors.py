from django.utils.functional import SimpleLazyObject

from apps.branding.services import brand_theme_service


def brand_theme(_request):
    return {
        "site_brand_theme": SimpleLazyObject(
            lambda: brand_theme_service.get_effective_theme().as_context()
        )
    }
