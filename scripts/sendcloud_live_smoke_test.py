# ruff: noqa: E402

import base64
import json
import os
import urllib.error
import urllib.request

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.production.models import ProductionJob
from apps.production.services.workflow import ProductionWorkflowService
from apps.shipping.services.sendcloud import ShipmentService
from django.conf import settings as s
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist

auth = base64.b64encode(f"{s.SENDCLOUD_PUBLIC_KEY}:{s.SENDCLOUD_SECRET_KEY}".encode()).decode()


def call(method: str, url: str, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode()
            print(method, resp.status, url)
            print(body[:1500])
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        print(method, exc.code, url, exc.read()[:800])
        return None


base = s.SENDCLOUD_API_BASE_URL.rstrip("/")
print("=== shipping options ===")
options = call(
    "POST",
    f"{base}/shipping-options",
    {
        "from_country_code": "FR",
        "to_country_code": "FR",
        "from_postal_code": "35310",
        "to_postal_code": "75001",
        "parcels": [{"weight": {"value": "1.0", "unit": "kg"}}],
        "calculate_quotes": False,
    },
)

codes = []
if isinstance(options, dict):
    data = options.get("data") or options.get("shipping_options") or options
    if isinstance(data, list):
        for item in data[:10]:
            if isinstance(item, dict):
                code = item.get("code") or (item.get("shipping_option") or {}).get("code")
                if code:
                    codes.append(str(code))
print("CODES", codes[:10])

shipping_option_code = codes[0] if codes else "sendcloud:letter"
print("USING", shipping_option_code)

# Prefer existing READY_TO_SHIP order, else create a dedicated test order.
order = (
    Order.objects.filter(production_job__status=ProductionJob.Status.READY_TO_SHIP)
    .exclude(shipment__status="created")
    .select_related("customer", "production_job")
    .order_by("-created_at")
    .first()
)

User = get_user_model()
staff = User.objects.filter(is_staff=True).order_by("id").first()
if staff is None:
    staff = User.objects.create_user(
        email="sendcloud-test@ids.supply", password="pass", is_staff=True
    )

if order is None:
    customer = Customer.objects.order_by("id").first()
    if customer is None:
        customer = Customer.objects.create(
            name="Sendcloud Test Customer", billing_email="test@example.com"
        )
        CustomerMembership.objects.create(
            customer=customer, user=staff, role=CustomerMembership.Role.OWNER
        )
    order = Order.objects.create(
        customer=customer,
        created_by=staff,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        currency="EUR",
        subtotal_amount="25.00",
        total_amount="25.00",
        customer_note="Test Sendcloud live",
    )
    workflow = ProductionWorkflowService()
    workflow.transition_job(
        order_public_id=order.public_id,
        to_status=ProductionJob.Status.IN_PROGRESS,
        actor=staff,
        source="sendcloud_live_test",
    )
    workflow.transition_job(
        order_public_id=order.public_id,
        to_status=ProductionJob.Status.READY_TO_SHIP,
        actor=staff,
        source="sendcloud_live_test",
    )
    order.refresh_from_db()

print("ORDER", order.public_id, order.customer.name)

recipient_email = (
    getattr(order.customer, "billing_email", "") or s.SENDCLOUD_SENDER_EMAIL or "test@example.com"
)
payload = {
    "shipping_option_code": shipping_option_code,
    "recipient": {
        "name": order.customer.name or "Client Test",
        "company_name": order.customer.name or "",
        "address_line_1": order.customer.shipping_address_line1 or "1 rue de Rivoli",
        "address_line_2": order.customer.shipping_address_line2 or "",
        "house_number": "1",
        "postal_code": order.customer.shipping_postal_code or "75001",
        "city": order.customer.shipping_city or "Paris",
        "country_code": order.customer.shipping_country or "FR",
        "email": recipient_email,
        "phone_number": "",
    },
    "parcel": {"weight": {"value": "1.0", "unit": "kg"}},
    "label_details": {"mime_type": "application/pdf", "dpi": 72},
}

print("=== declare order (no label) ===")
try:
    _order, shipment = ShipmentService().create_shipment(
        order_public_id=order.public_id,
        actor=staff,
        source="sendcloud_live_test",
        payload=payload,
    )
    print(
        "RESULT",
        {
            "status": shipment.status,
            "sendcloud_order_id": shipment.sendcloud_order_id,
            "parcel_id": shipment.sendcloud_parcel_id,
            "tracking_number": shipment.tracking_number,
            "has_label": bool(shipment.label_file),
            "sendcloud_status": shipment.sendcloud_status_code,
            "error": shipment.last_error_message,
        },
    )
except Exception as exc:  # noqa: BLE001
    print("CREATE_FAILED", type(exc).__name__, str(exc)[:500])
    try:
        shipment = order.shipment
        print(
            "SHIPMENT_STATE",
            shipment.status,
            shipment.last_error_message,
            shipment.sendcloud_order_id,
            shipment.sendcloud_parcel_id,
        )
    except ObjectDoesNotExist:
        print("NO_LOCAL_SHIPMENT")
