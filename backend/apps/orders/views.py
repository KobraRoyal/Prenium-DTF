from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasStaffOrderReadAccess
from apps.customers.permissions import HasScopedCustomerAccess

from .services.orders import OrderService

order_service = OrderService()


def serialize_order_item(item) -> dict[str, object]:
    return {
        "public_id": str(item.public_id),
        "service_public_id": str(item.service.public_id),
        "service_code": item.service_code,
        "service_name": item.service_name,
        "service_type": item.service_type,
        "unit": item.unit,
        "quantity": f"{item.quantity:.2f}",
        "unit_price": f"{item.unit_price:.2f}",
        "line_total": f"{item.line_total:.2f}",
    }


def serialize_order(order, *, include_customer: bool) -> dict[str, object]:
    payload = {
        "public_id": str(order.public_id),
        "customer_public_id": str(order.customer.public_id),
        "status": order.status,
        "billing_mode": order.billing_mode,
        "pricing_status": order.pricing_status,
        "credit_hold_status": order.credit_hold_status,
        "currency": order.currency,
        "subtotal_amount": f"{order.subtotal_amount:.2f}",
        "total_amount": f"{order.total_amount:.2f}",
        "customer_note": order.customer_note,
        "created_at": order.created_at.isoformat(),
        "items": [serialize_order_item(item) for item in order.items.all()],
    }
    if include_customer:
        payload["customer"] = {
            "public_id": str(order.customer.public_id),
            "name": order.customer.name,
        }
    return payload


def raise_api_validation_error(error: DjangoValidationError):
    if hasattr(error, "message_dict"):
        raise DRFValidationError(error.message_dict)
    raise DRFValidationError({"detail": error.messages})


class ClientOrderListCreateView(APIView):
    permission_classes = [IsAuthenticated, HasScopedCustomerAccess]

    def get(self, request, customer_public_id):
        orders = order_service.list_customer_orders(self.customer)
        return Response(
            {
                "customer_public_id": str(self.customer.public_id),
                "orders": [serialize_order(order, include_customer=False) for order in orders],
            }
        )

    def post(self, request, customer_public_id):
        try:
            order = order_service.create_order(
                customer=self.customer,
                actor=request.user,
                customer_membership=self.customer_membership,
                items=request.data.get("items", []),
                customer_note=request.data.get("customer_note", ""),
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        return Response(serialize_order(order, include_customer=False), status=201)


class ClientOrderDetailView(APIView):
    permission_classes = [IsAuthenticated, HasScopedCustomerAccess]

    def get(self, request, customer_public_id, order_public_id):
        order = order_service.get_customer_order(self.customer, order_public_id)
        if order is None:
            raise Http404
        return Response(serialize_order(order, include_customer=False))


class StaffOrderListView(APIView):
    permission_classes = [IsAuthenticated, HasStaffOrderReadAccess]

    def get(self, request):
        orders = order_service.list_staff_orders()
        return Response(
            {"orders": [serialize_order(order, include_customer=True) for order in orders]}
        )


class StaffOrderDetailView(APIView):
    permission_classes = [IsAuthenticated, HasStaffOrderReadAccess]

    def get(self, request, order_public_id):
        order = order_service.get_staff_order(order_public_id)
        if order is None:
            raise Http404
        return Response(serialize_order(order, include_customer=True))
