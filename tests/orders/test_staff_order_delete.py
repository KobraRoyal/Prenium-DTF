import pytest
from apps.auditlog.models import AuditLogEntry
from apps.billing.models import Invoice, Payment
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.orders.services.orders import OrderService
from apps.production.models import ProductionJob
from apps.production.services.workflow import ProductionWorkflowService
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone


def _create_staff(*, email: str, permissions: list[str]):
    user = get_user_model().objects.create_user(email=email, password="pass1234")
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    perms = [Permission.objects.get(codename="access_staff_portal")]
    for codename in permissions:
        perms.append(Permission.objects.get(codename=codename))
    user.user_permissions.add(*perms)
    return user


def _create_submitted_order(*, actor=None):
    owner = actor or get_user_model().objects.create_user(
        email="owner-delete@example.com", password="pass"
    )
    customer = Customer.objects.create(name="Client Delete")
    CustomerMembership.objects.create(customer=customer, user=owner)
    order = Order.objects.create(
        customer=customer,
        created_by=owner,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        currency="EUR",
        subtotal_amount="0.00",
        total_amount="0.00",
        source="client_b2b_project",
    )
    ProductionWorkflowService().get_or_create_for_order(order=order)
    return order, owner


@pytest.mark.django_db
def test_delete_staff_order_soft_cancels_and_audits():
    order, owner = _create_submitted_order()
    staff = _create_staff(
        email="ops-delete@example.com",
        permissions=["view_order", "delete_atelier_order"],
    )

    deleted = OrderService().delete_staff_order(
        order_public_id=order.public_id,
        actor=staff,
        source="test",
        reason="Doublon client",
    )

    assert deleted.status == Order.Status.CANCELLED
    assert deleted.cancelled_by_id == staff.pk
    assert deleted.cancellation_reason == "Doublon client"
    assert deleted.cancelled_at is not None
    assert not OrderService().list_staff_orders().filter(pk=order.pk).exists()
    assert OrderService().list_staff_orders(include_cancelled=True).filter(pk=order.pk).exists()
    assert AuditLogEntry.objects.filter(
        action="order.deleted_atelier",
        target_public_id=order.public_id,
    ).exists()


@pytest.mark.django_db
def test_delete_staff_order_refuses_captured_payment():
    order, _owner = _create_submitted_order()
    staff = _create_staff(
        email="ops-pay@example.com",
        permissions=["view_order", "delete_atelier_order"],
    )
    Payment.objects.create(
        order=order,
        created_by=staff,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.CAPTURED,
        amount="10.00",
        currency="EUR",
        captured_at=timezone.now(),
        source="test",
    )

    with pytest.raises(ValidationError, match="paiement a déjà été capturé"):
        OrderService().delete_staff_order(
            order_public_id=order.public_id,
            actor=staff,
            source="test",
        )
    order.refresh_from_db()
    assert order.status == Order.Status.SUBMITTED
    assert AuditLogEntry.objects.filter(action="order.delete_rejected").exists()


@pytest.mark.django_db
def test_delete_staff_order_refuses_invoice_and_started_production():
    order, _owner = _create_submitted_order()
    staff = _create_staff(
        email="ops-inv@example.com",
        permissions=["view_order", "delete_atelier_order"],
    )
    Invoice.objects.create(
        order=order,
        status=Invoice.Status.ISSUED,
        invoice_number="JP-TEST-001",
        subtotal_amount="10.00",
        total_amount="10.00",
        currency="EUR",
        source="test",
    )
    with pytest.raises(ValidationError, match="justificatif|facture"):
        OrderService().delete_staff_order(
            order_public_id=order.public_id,
            actor=staff,
            source="test",
        )

    order_b, _ = _create_submitted_order(
        actor=get_user_model().objects.create_user(email="owner2@example.com", password="pass")
    )
    job = order_b.production_job
    job.status = ProductionJob.Status.IN_PROGRESS
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at", "updated_at"])
    with pytest.raises(ValidationError, match="production a déjà démarré"):
        OrderService().delete_staff_order(
            order_public_id=order_b.public_id,
            actor=staff,
            source="test",
        )


@pytest.mark.django_db
def test_production_transition_blocked_when_order_cancelled():
    order, _owner = _create_submitted_order()
    staff = _create_staff(
        email="ops-prod@example.com",
        permissions=["view_order", "delete_atelier_order", "transition_productionjob"],
    )
    OrderService().delete_staff_order(
        order_public_id=order.public_id,
        actor=staff,
        source="test",
    )
    with pytest.raises(ValidationError, match="retirée de la file"):
        ProductionWorkflowService().transition_job(
            order_public_id=order.public_id,
            to_status=ProductionJob.Status.IN_PROGRESS,
            actor=staff,
            source="test",
        )


@pytest.mark.django_db
def test_staff_order_delete_view_requires_permission():
    order, _owner = _create_submitted_order()
    viewer = _create_staff(email="viewer@example.com", permissions=["view_order"])
    deleter = _create_staff(
        email="deleter@example.com",
        permissions=["view_order", "delete_atelier_order"],
    )
    client = Client()
    url = reverse("portal:staff-order-delete", kwargs={"order_public_id": order.public_id})

    assert client.login(email="viewer@example.com", password="pass1234")
    response = client.post(url)
    assert response.status_code == 403
    order.refresh_from_db()
    assert order.status == Order.Status.SUBMITTED

    assert client.login(email="deleter@example.com", password="pass1234")
    response = client.post(url)
    assert response.status_code == 302
    assert reverse("portal:staff-order-list") in response["Location"]
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
