import pytest
from apps.auditlog.models import AuditLogEntry
from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerMembership
from apps.orders.services.orders import OrderService
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError


@pytest.mark.django_db
def test_order_service_creates_snapshotted_order_and_audit_entry():
    user = get_user_model().objects.create_user(email="owner@example.com", password="pass")
    customer = Customer.objects.create(name="Acme")
    CustomerMembership.objects.create(customer=customer, user=user)
    dtf_service = CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.50",
        display_order=1,
    )
    prep_service = CatalogService.objects.create(
        code="prep-file",
        name="Preparation fichier",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price="25.00",
        display_order=2,
    )

    order = OrderService().create_order(
        customer=customer,
        actor=user,
        items=[
            {"service_public_id": str(dtf_service.public_id), "quantity": "2.50"},
            {"service_public_id": str(prep_service.public_id), "quantity": 1},
        ],
        customer_note="Premiere commande",
    )

    assert order.customer == customer
    assert order.status == "submitted"
    assert str(order.total_amount) == "56.25"
    assert order.items.count() == 2
    assert order.items.first().service_name == "DTF au metre"
    assert order.production_job.status == "queued"
    assert order.production_job.manufacturing_order_number.startswith("OF-")
    assert AuditLogEntry.objects.filter(
        action="order.created",
        target_public_id=order.public_id,
    ).exists()


@pytest.mark.django_db
def test_order_service_refuses_invalid_fixed_quantity():
    user = get_user_model().objects.create_user(email="owner@example.com", password="pass")
    customer = Customer.objects.create(name="Acme")
    CustomerMembership.objects.create(customer=customer, user=user)
    prep_service = CatalogService.objects.create(
        code="prep-file",
        name="Preparation fichier",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price="25.00",
    )

    with pytest.raises(ValidationError, match="Fixed-price services must use a quantity of 1."):
        OrderService().create_order(
            customer=customer,
            actor=user,
            items=[{"service_public_id": str(prep_service.public_id), "quantity": 2}],
        )


@pytest.mark.django_db
def test_order_service_refuses_actor_outside_customer_scope():
    user = get_user_model().objects.create_user(email="owner@example.com", password="pass")
    customer = Customer.objects.create(name="Acme")
    dtf_service = CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.50",
    )

    with pytest.raises(ValidationError, match="Actor is not allowed for this customer."):
        OrderService().create_order(
            customer=customer,
            actor=user,
            items=[{"service_public_id": str(dtf_service.public_id), "quantity": "1.00"}],
        )


@pytest.mark.django_db
def test_order_service_accepts_validated_customer_membership():
    user = get_user_model().objects.create_user(email="owner@example.com", password="pass")
    customer = Customer.objects.create(name="Acme")
    customer_membership = CustomerMembership.objects.create(customer=customer, user=user)
    dtf_service = CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.50",
    )

    order = OrderService().create_order(
        customer=customer,
        actor=user,
        customer_membership=customer_membership,
        items=[{"service_public_id": str(dtf_service.public_id), "quantity": "1.00"}],
    )

    assert order.customer == customer
    assert order.created_by == user
    assert str(order.total_amount) == "12.50"


@pytest.mark.django_db
def test_order_service_refuses_mismatched_customer_membership():
    user = get_user_model().objects.create_user(email="owner@example.com", password="pass")
    customer_a = Customer.objects.create(name="Acme A")
    customer_b = Customer.objects.create(name="Acme B")
    customer_membership = CustomerMembership.objects.create(customer=customer_a, user=user)
    dtf_service = CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.50",
    )

    with pytest.raises(ValidationError, match="Actor is not allowed for this customer."):
        OrderService().create_order(
            customer=customer_b,
            actor=user,
            customer_membership=customer_membership,
            items=[{"service_public_id": str(dtf_service.public_id), "quantity": "1.00"}],
        )


@pytest.mark.django_db
def test_order_service_refuses_non_persisted_customer_membership_scope():
    user = get_user_model().objects.create_user(email="owner@example.com", password="pass")
    customer = Customer.objects.create(name="Acme")
    dtf_service = CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.50",
    )
    forged_membership = CustomerMembership(customer=customer, user=user, is_active=True)

    with pytest.raises(ValidationError, match="Actor is not allowed for this customer."):
        OrderService().create_order(
            customer=customer,
            actor=user,
            customer_membership=forged_membership,
            items=[{"service_public_id": str(dtf_service.public_id), "quantity": "1.00"}],
        )


@pytest.mark.django_db
def test_filter_customer_orders_matches_reference_note_and_short_ref():
    user = get_user_model().objects.create_user(email="search@example.com", password="pass")
    customer = Customer.objects.create(name="Search Co")
    CustomerMembership.objects.create(customer=customer, user=user)
    service = OrderService()

    summer = service.create_b2b_deferred_order(
        customer=customer,
        actor=user,
        customer_note="Collection été\nLivraison rapide",
        source="test",
    )
    winter = service.create_b2b_deferred_order(
        customer=customer,
        actor=user,
        customer_note="Collection hiver",
        source="test",
    )

    by_note = service.filter_customer_orders(
        service.list_customer_orders(customer),
        query="été",
    )
    assert list(by_note.values_list("pk", flat=True)) == [summer.pk]

    by_short_ref = service.filter_customer_orders(
        service.list_customer_orders(customer),
        query=str(summer.public_id).split("-")[-1][:8],
    )
    assert winter.pk not in by_short_ref.values_list("pk", flat=True)
    assert summer.pk in by_short_ref.values_list("pk", flat=True)

    empty = service.filter_customer_orders(
        service.list_customer_orders(customer),
        query="   ",
    )
    assert empty.count() == 2
