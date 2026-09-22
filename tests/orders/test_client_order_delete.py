import pytest
from apps.auditlog.models import AuditLogEntry
from apps.billing.models import Invoice, Payment
from apps.billing.services.gateways import PaymentGatewayError
from apps.billing.services.payments import PaymentService
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.orders.services.orders import OrderService
from apps.production.models import ProductionJob
from apps.production.services.workflow import ProductionWorkflowService
from apps.shipping.models import Shipment
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone


def _create_client_order(*, email: str, billing_mode=Order.BillingMode.IMMEDIATE, **order_fields):
    user = get_user_model().objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(name=email)
    CustomerMembership.objects.create(customer=customer, user=user)
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=billing_mode,
        pricing_status=Order.PricingStatus.PRICED,
        currency="EUR",
        subtotal_amount="12.00",
        total_amount="12.00",
        source="client_b2b_project",
        **order_fields,
    )
    ProductionWorkflowService().get_or_create_for_order(order=order)
    return user, customer, order


def _delete_url(customer, order):
    return reverse(
        "portal:client-order-delete",
        kwargs={
            "customer_public_id": customer.public_id,
            "order_public_id": order.public_id,
        },
    )


@pytest.mark.django_db
def test_client_delete_lock_query_does_not_outer_join_nullable_relations():
    _user, customer, order = _create_client_order(email="lock-sql@example.com")
    sql = str(
        Order.objects.select_for_update()
        .select_related("customer")
        .filter(public_id=order.public_id, customer=customer)
        .query
    ).upper()
    assert "LEFT OUTER JOIN" not in sql


@pytest.mark.django_db
def test_delete_client_order_soft_cancels_open_checkout_and_stays_listed():
    user, customer, order = _create_client_order(email="client-delete@example.com")
    Payment.objects.create(
        order=order,
        created_by=user,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.PENDING,
        amount="12.00",
        currency="EUR",
        source="test",
    )

    deleted = OrderService().delete_client_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
    )

    assert deleted.status == Order.Status.CANCELLED
    assert deleted.cancelled_by_id == user.pk
    assert deleted.cancellation_reason == "Supprimée par le client avant paiement."
    payment = Payment.objects.get(order=order)
    assert payment.status == Payment.Status.CANCELLED
    assert OrderService().list_customer_orders(customer).filter(pk=order.pk).exists()
    assert not OrderService().list_staff_orders().filter(pk=order.pk).exists()
    assert AuditLogEntry.objects.filter(
        action="order.deleted_client",
        target_public_id=order.public_id,
    ).exists()


@pytest.mark.django_db
def test_delete_client_order_refuses_captured_deferred_invoice_and_production():
    user, customer, paid = _create_client_order(email="paid@example.com")
    Payment.objects.create(
        order=paid,
        created_by=user,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.CAPTURED,
        amount="12.00",
        currency="EUR",
        captured_at=timezone.now(),
        source="test",
    )
    with pytest.raises(ValidationError, match="paiement a été confirmé"):
        OrderService().delete_client_order(
            customer=customer,
            order_public_id=paid.public_id,
            actor=user,
            source="test",
        )
    paid.refresh_from_db()
    assert paid.status == Order.Status.SUBMITTED

    _user, _customer, deferred = _create_client_order(
        email="deferred@example.com",
        billing_mode=Order.BillingMode.DEFERRED,
    )
    with pytest.raises(ValidationError, match="réglée par carte"):
        OrderService().delete_client_order(
            customer=_customer,
            order_public_id=deferred.public_id,
            actor=_user,
            source="test",
        )

    invoiced_user, invoiced_customer, invoiced = _create_client_order(email="invoice@example.com")
    Invoice.objects.create(
        order=invoiced,
        status=Invoice.Status.ISSUED,
        invoice_number="JP-CLIENT-DEL",
        subtotal_amount="12.00",
        total_amount="12.00",
        currency="EUR",
        source="test",
    )
    with pytest.raises(ValidationError, match="justificatif"):
        OrderService().delete_client_order(
            customer=invoiced_customer,
            order_public_id=invoiced.public_id,
            actor=invoiced_user,
            source="test",
        )

    started_user, started_customer, started = _create_client_order(email="started@example.com")
    job = started.production_job
    job.status = ProductionJob.Status.IN_PROGRESS
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at", "updated_at"])
    with pytest.raises(ValidationError, match="production a déjà démarré"):
        OrderService().delete_client_order(
            customer=started_customer,
            order_public_id=started.public_id,
            actor=started_user,
            source="test",
        )

    shipped_user, shipped_customer, shipped = _create_client_order(email="shipped@example.com")
    Shipment.objects.create(order=shipped, created_by=shipped_user)
    with pytest.raises(ValidationError, match="expédition"):
        OrderService().delete_client_order(
            customer=shipped_customer,
            order_public_id=shipped.public_id,
            actor=shipped_user,
            source="test",
        )
    assert AuditLogEntry.objects.filter(action="order.delete_client_rejected").count() == 5


@pytest.mark.django_db
def test_close_open_stripe_checkout_expires_session_before_local_cancel():
    user, _customer, order = _create_client_order(email="stripe-open@example.com")
    payment = Payment.objects.create(
        order=order,
        created_by=user,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.PENDING,
        amount="12.00",
        currency="EUR",
        stripe_checkout_session_id="cs_test_open",
        source="test",
    )

    class FakeGateway:
        provider = Payment.Provider.STRIPE
        expired: list[str] = []

        def checkout_state(self, *, provider_payment_id: str) -> str:
            return "OPEN"

        def expire_checkout(self, *, provider_payment_id: str) -> str:
            self.expired.append(provider_payment_id)
            return "EXPIRED"

    gateway = FakeGateway()
    PaymentService(gateway=gateway).close_open_checkouts_before_client_cancel(
        order=order,
        actor=user,
        source="test",
    )

    payment.refresh_from_db()
    assert gateway.expired == ["cs_test_open"]
    assert payment.status == Payment.Status.CANCELLED


@pytest.mark.django_db
def test_close_open_stripe_checkout_refuses_when_remote_is_paid():
    user, _customer, order = _create_client_order(email="stripe-paid@example.com")
    Payment.objects.create(
        order=order,
        created_by=user,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.PENDING,
        amount="12.00",
        currency="EUR",
        stripe_checkout_session_id="cs_test_paid",
        source="test",
    )

    class FakeGateway:
        provider = Payment.Provider.STRIPE

        def checkout_state(self, *, provider_payment_id: str) -> str:
            return "COMPLETED"

        def confirm_checkout(self, *, provider_payment_id: str):
            raise PaymentGatewayError("session déjà payée")

    with pytest.raises(ValidationError, match="paiement a été confirmé"):
        PaymentService(gateway=FakeGateway()).close_open_checkouts_before_client_cancel(
            order=order,
            actor=user,
            source="test",
        )


@pytest.mark.django_db
def test_client_order_delete_view_is_scoped_and_keeps_pay_as_primary():
    user, customer, order = _create_client_order(email="owner-ui@example.com")
    other, other_customer, _other_order = _create_client_order(email="other@example.com")
    client = Client()
    delete_url = _delete_url(customer, order)
    detail_url = reverse(
        "portal:client-order-detail",
        kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
    )
    list_url = reverse(
        "portal:client-order-list",
        kwargs={"customer_public_id": customer.public_id},
    )

    anonymous = client.post(delete_url)
    assert anonymous.status_code == 302
    assert "/login" in anonymous["Location"] or "accounts/login" in anonymous["Location"]

    assert client.login(email=other.email, password="pass")
    denied = client.post(delete_url)
    assert denied.status_code == 403
    order.refresh_from_db()
    assert order.status == Order.Status.SUBMITTED

    assert client.login(email=user.email, password="pass")
    detail = client.get(detail_url)
    html = detail.content.decode()
    assert detail.status_code == 200
    assert "Supprimer cette commande" in html
    assert "Confirmer la suppression" in html
    assert "Payer maintenant" not in html or "client-order-detail-actions" in html

    listing = client.get(list_url)
    listing_html = listing.content.decode()
    assert ">Payer</a>" in listing_html
    assert "Supprimer" in listing_html
    assert 'name="next" value="list"' in listing_html

    response = client.post(delete_url, {"next": "list"})
    assert response.status_code == 302
    assert response["Location"].endswith(list_url)
    messages = [message.message for message in get_messages(response.wsgi_request)]
    assert any("Annulée" in message for message in messages)
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED

    listing_after = client.get(list_url)
    after_html = listing_after.content.decode()
    assert "Annulée" in after_html
    assert ">Payer</a>" not in after_html
    assert "Supprimer" not in after_html
    assert other_customer.public_id != customer.public_id

    readonly = get_user_model().objects.create_user(email="readonly@example.com", password="pass")
    CustomerMembership.objects.create(
        customer=customer,
        user=readonly,
        role=CustomerMembership.Role.READONLY,
    )
    fresh_user, fresh_customer, fresh_order = _create_client_order(email="fresh-delete@example.com")
    assert client.login(email=readonly.email, password="pass")
    forbidden = client.post(_delete_url(customer, order))
    assert forbidden.status_code == 403
    assert client.login(email=fresh_user.email, password="pass")
    allowed = client.get(
        reverse(
            "portal:client-order-detail",
            kwargs={
                "customer_public_id": fresh_customer.public_id,
                "order_public_id": fresh_order.public_id,
            },
        )
    )
    assert "Confirmer la suppression" in allowed.content.decode()
