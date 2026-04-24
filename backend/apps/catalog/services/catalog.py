from apps.catalog.models import CatalogService


class CatalogQueryService:
    def list_active_services(self):
        return CatalogService.objects.active().order_by("display_order", "name")

    def list_staff_services(self):
        return CatalogService.objects.order_by("display_order", "name")

    def get_active_service_map(self, public_ids: list[str]) -> dict[str, CatalogService]:
        services = CatalogService.objects.active().filter(public_id__in=public_ids)
        return {str(service.public_id): service for service in services}

