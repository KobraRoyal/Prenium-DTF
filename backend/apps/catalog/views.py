from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasStaffCatalogReadAccess
from apps.customers.permissions import HasScopedCustomerAccess

from .services.catalog import CatalogQueryService

catalog_query_service = CatalogQueryService()


def serialize_catalog_service(service, *, include_inactive: bool) -> dict[str, object]:
    payload = {
        "public_id": str(service.public_id),
        "code": service.code,
        "name": service.name,
        "description": service.description,
        "service_type": service.service_type,
        "unit": service.unit,
        "pricing": {
            "base_price": f"{service.base_price:.2f}",
            "currency": service.currency,
        },
    }
    if include_inactive:
        payload["is_active"] = service.is_active
    return payload


class ClientCatalogServiceListView(APIView):
    permission_classes = [IsAuthenticated, HasScopedCustomerAccess]

    def get(self, request, customer_public_id):
        services = catalog_query_service.list_active_services()
        return Response(
            {
                "customer_public_id": str(self.customer.public_id),
                "services": [
                    serialize_catalog_service(service, include_inactive=False)
                    for service in services
                ],
            }
        )


class StaffCatalogServiceListView(APIView):
    permission_classes = [IsAuthenticated, HasStaffCatalogReadAccess]

    def get(self, request):
        services = catalog_query_service.list_staff_services()
        return Response(
            {
                "services": [
                    serialize_catalog_service(service, include_inactive=True)
                    for service in services
                ]
            }
        )
