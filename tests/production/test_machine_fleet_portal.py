import uuid

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.production.models import (
    ProductionJob,
    ProductionJobMachineAssignment,
    ProductionMachine,
    ProductionPrintRecord,
)
from apps.production.services.machine_assignments import (
    ProductionMachineAssignmentService,
)
from apps.production.services.machine_fleet import MachineFleetService
from apps.production.services.print_tracking import ProductionPrintTrackingService
from apps.production.services.workflow import ProductionWorkflowService
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse


def create_user(email, *, permissions=(), is_staff=True, staff_portal=True):
    user = get_user_model().objects.create_user(
        email=email,
        password="pass",
        is_staff=is_staff,
    )
    permission_codenames = set(permissions)
    if is_staff and staff_portal:
        permission_codenames.add("access_staff_portal")
    for codename in permission_codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


def logged_client(user, *, enforce_csrf_checks=False):
    client = Client(enforce_csrf_checks=enforce_csrf_checks)
    assert client.login(email=user.email, password="pass") is True
    return client


def create_order(*, actor, customer=None):
    customer = customer or Customer.objects.create(name="Portal machine customer")
    return Order.objects.create(
        customer=customer,
        created_by=actor,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        currency="EUR",
        subtotal_amount="0.00",
        total_amount="0.00",
    )


def create_machine(*, manager, code="DTF-01", name="Atlas"):
    return MachineFleetService().create_machine(
        actor=manager,
        source="test",
        data={"code": code, "name": name, "status": ProductionMachine.Status.ACTIVE},
    )


@pytest.mark.django_db
def test_machine_fleet_page_is_staff_only_and_permission_scoped():
    route = reverse("portal:staff-machine-fleet")
    anonymous = Client()
    client_user = create_user("client-fleet@example.com", is_staff=False)
    staff_without_view = create_user(
        "staff-no-fleet@example.com",
        permissions=("access_staff_portal",),
    )
    viewer = create_user(
        "staff-fleet-view@example.com",
        permissions=("access_staff_portal", "view_productionmachine"),
    )

    assert anonymous.get(route).status_code == 302
    assert logged_client(client_user).get(route).status_code == 403
    assert logged_client(staff_without_view).get(route).status_code == 403
    allowed = logged_client(viewer).get(route)
    assert allowed.status_code == 200
    assert "Parc machines DTF" in allowed.content.decode()
    assert "Ajouter une imprimante" not in allowed.content.decode()


@pytest.mark.django_db
def test_machine_create_htmx_requires_manage_permission_and_escapes_name():
    route = reverse("portal:staff-machine-create")
    viewer = create_user(
        "staff-fleet-readonly@example.com",
        permissions=("access_staff_portal", "view_productionmachine"),
    )
    manager = create_user(
        "staff-fleet-manage@example.com",
        permissions=(
            "access_staff_portal",
            "view_productionmachine",
            "manage_productionmachine",
        ),
    )
    payload = {
        "code": "dtf-xss",
        "name": '<script>alert("fleet")</script>',
        "status": ProductionMachine.Status.ACTIVE,
    }

    assert logged_client(viewer).post(route, payload).status_code == 403
    assert AuditLogEntry.objects.filter(
        action="production.machine.permission_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()
    response = logged_client(manager).post(
        route,
        payload,
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    html = response.content.decode()
    assert "DTF-XSS" in html
    assert "&lt;script&gt;" in html
    assert '<script>alert("fleet")</script>' not in html
    assert ProductionMachine.objects.filter(code="DTF-XSS").exists()


@pytest.mark.django_db
def test_fleet_only_roles_never_receive_customer_print_ledger():
    manager = create_user(
        "fleet-ledger-manager@example.com",
        permissions=("manage_productionmachine",),
    )
    operator = create_user(
        "fleet-ledger-operator@example.com",
        permissions=(
            "view_order",
            "view_productionjob",
            "assign_productionmachine",
            "confirm_productionprint",
        ),
    )
    customer = Customer.objects.create(name="Secret ledger customer")
    order = create_order(actor=operator, customer=customer)
    machine = create_machine(manager=manager, code="DTF-LEDGER")
    job, _assignment, _changed = ProductionMachineAssignmentService().assign(
        order_public_id=order.public_id,
        machine_public_id=machine.public_id,
        actor=operator,
        source="test",
    )
    job.status = ProductionJob.Status.IN_PROGRESS
    job.save(update_fields=("status", "updated_at"))
    ProductionPrintTrackingService().confirm_print(
        order_public_id=order.public_id,
        actor=operator,
        source="test",
        note="Secret print note",
    )
    fleet_viewer = create_user(
        "fleet-ledger-viewer@example.com",
        permissions=("view_productionmachine",),
    )

    response = logged_client(fleet_viewer).get(reverse("portal:staff-machine-fleet"))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Journal des impressions" not in html
    assert customer.name not in html
    assert str(order.public_id) not in html
    assert "Secret print note" not in html

    mutation_response = logged_client(manager).post(
        reverse("portal:staff-machine-create"),
        {"code": "DTF-MANAGER", "name": "Manager only", "status": "active"},
        HTTP_HX_REQUEST="true",
    )
    assert mutation_response.status_code == 200
    mutation_html = mutation_response.content.decode()
    assert "Journal des impressions" not in mutation_html
    assert customer.name not in mutation_html
    assert str(order.public_id) not in mutation_html


@pytest.mark.django_db
def test_machine_mutations_are_post_only_and_csrf_protected():
    manager = create_user(
        "staff-fleet-csrf@example.com",
        permissions=(
            "access_staff_portal",
            "view_productionmachine",
            "manage_productionmachine",
        ),
    )
    route = reverse("portal:staff-machine-create")

    assert logged_client(manager).get(route).status_code == 405
    csrf_client = logged_client(manager, enforce_csrf_checks=True)
    assert csrf_client.post(
        route,
        {"code": "DTF-CSRF", "name": "CSRF", "status": "active"},
    ).status_code == 403


@pytest.mark.django_db
def test_portal_assignment_and_print_confirmation_render_history():
    manager = create_user(
        "portal-machine-manager@example.com",
        permissions=("manage_productionmachine",),
    )
    operator = create_user(
        "portal-machine-operator@example.com",
        permissions=(
            "access_staff_portal",
            "view_order",
            "view_productionjob",
            "assign_productionmachine",
            "confirm_productionprint",
        ),
    )
    order = create_order(actor=operator)
    machine = create_machine(manager=manager)
    assignment_route = reverse(
        "portal:staff-order-machine-assignment",
        kwargs={"order_public_id": order.public_id},
    )
    client = logged_client(operator)

    assignment_response = client.post(
        assignment_route,
        {"machine_public_id": machine.public_id},
        HTTP_HX_REQUEST="true",
    )

    assert assignment_response.status_code == 200
    assert "Atlas" in assignment_response.content.decode()
    assert ProductionJobMachineAssignment.objects.filter(machine=machine).exists()

    job = ProductionJob.objects.get(order=order)
    job.status = ProductionJob.Status.IN_PROGRESS
    job.save(update_fields=("status", "updated_at"))
    print_route = reverse(
        "portal:staff-order-print-confirmation",
        kwargs={"order_public_id": order.public_id},
    )
    print_response = client.post(
        print_route,
        {"request_token": uuid.uuid4(), "print_note": "Contrôle validé"},
        HTTP_HX_REQUEST="true",
    )

    assert print_response.status_code == 200
    html = print_response.content.decode()
    assert "Impressions confirmées" in html
    assert "Contrôle validé" in html
    assert ProductionPrintRecord.objects.filter(production_job=job, machine=machine).exists()


@pytest.mark.django_db
def test_assignment_route_checks_permissions_before_object_lookup():
    partial_operator = create_user(
        "portal-machine-partial@example.com",
        permissions=("access_staff_portal", "view_order", "view_productionjob"),
    )
    client = logged_client(partial_operator)
    existing_order = create_order(actor=partial_operator)
    existing_route = reverse(
        "portal:staff-order-machine-assignment",
        kwargs={"order_public_id": existing_order.public_id},
    )
    missing_route = reverse(
        "portal:staff-order-machine-assignment",
        kwargs={"order_public_id": uuid.uuid4()},
    )

    existing_response = client.post(
        existing_route,
        {"machine_public_id": uuid.uuid4()},
    )
    missing_response = client.post(
        missing_route,
        {"machine_public_id": uuid.uuid4()},
    )

    assert existing_response.status_code == 403
    assert missing_response.status_code == 403
    assert not ProductionJobMachineAssignment.objects.exists()


@pytest.mark.django_db
def test_production_panel_checks_order_permission_before_object_lookup():
    partial_viewer = create_user(
        "portal-panel-partial@example.com",
        permissions=("view_productionjob",),
    )
    existing_order = create_order(actor=partial_viewer)
    client = logged_client(partial_viewer)

    for order_public_id in (existing_order.public_id, uuid.uuid4()):
        route = reverse(
            "portal:staff-order-panel-production",
            kwargs={"order_public_id": order_public_id},
        )
        assert client.get(route).status_code == 403


@pytest.mark.django_db
def test_print_route_checks_permissions_before_object_lookup_and_audits():
    partial_operator = create_user(
        "portal-print-partial@example.com",
        permissions=("view_order", "view_productionjob"),
    )
    existing_order = create_order(actor=partial_operator)
    client = logged_client(partial_operator)

    for order_public_id in (existing_order.public_id, uuid.uuid4()):
        route = reverse(
            "portal:staff-order-print-confirmation",
            kwargs={"order_public_id": order_public_id},
        )
        assert client.post(route, {"request_token": uuid.uuid4()}).status_code == 403

    assert AuditLogEntry.objects.filter(
        action="production.print.confirmation_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).count() == 2


@pytest.mark.django_db
def test_machine_permissions_remain_separate_and_all_mutations_require_csrf():
    fleet_manager = create_user(
        "portal-separation-manager@example.com",
        permissions=("view_productionmachine", "manage_productionmachine"),
    )
    assign_operator = create_user(
        "portal-separation-assign@example.com",
        permissions=("view_order", "view_productionjob", "assign_productionmachine"),
    )
    viewer = create_user(
        "portal-separation-viewer@example.com",
        permissions=("view_productionmachine",),
    )
    order = create_order(actor=assign_operator)
    machine = create_machine(manager=fleet_manager)
    assignment_route = reverse(
        "portal:staff-order-machine-assignment",
        kwargs={"order_public_id": order.public_id},
    )
    print_route = reverse(
        "portal:staff-order-print-confirmation",
        kwargs={"order_public_id": order.public_id},
    )
    update_route = reverse(
        "portal:staff-machine-update",
        kwargs={"machine_public_id": machine.public_id},
    )

    assert logged_client(fleet_manager).post(
        assignment_route,
        {"machine_public_id": machine.public_id},
    ).status_code == 403
    assert logged_client(assign_operator).post(
        print_route,
        {"request_token": uuid.uuid4()},
    ).status_code == 403
    assert logged_client(viewer).post(
        update_route,
        {"code": machine.code, "name": machine.name, "status": "active"},
    ).status_code == 403

    csrf_manager = logged_client(fleet_manager, enforce_csrf_checks=True)
    assert csrf_manager.post(
        update_route,
        {"code": machine.code, "name": machine.name, "status": "active"},
    ).status_code == 403
    csrf_operator = logged_client(assign_operator, enforce_csrf_checks=True)
    assert csrf_operator.post(
        assignment_route,
        {"machine_public_id": machine.public_id},
    ).status_code == 403

    confirm_operator = create_user(
        "portal-separation-confirm@example.com",
        permissions=(
            "view_order",
            "view_productionjob",
            "confirm_productionprint",
        ),
    )
    assert logged_client(confirm_operator, enforce_csrf_checks=True).post(
        print_route,
        {"request_token": uuid.uuid4()},
    ).status_code == 403


@pytest.mark.django_db
def test_client_portal_never_exposes_machine_identity_or_history():
    manager = create_user(
        "client-boundary-manager@example.com",
        permissions=("manage_productionmachine",),
    )
    operator = create_user(
        "client-boundary-operator@example.com",
        permissions=(
            "view_order",
            "view_productionjob",
            "assign_productionmachine",
        ),
    )
    client_user = create_user("client-boundary@example.com", is_staff=False)
    customer = Customer.objects.create(name="Boundary customer")
    CustomerMembership.objects.create(customer=customer, user=client_user)
    order = create_order(actor=client_user, customer=customer)
    machine = create_machine(
        manager=manager,
        code="DTF-PRIVATE",
        name="Private machine name",
    )
    ProductionMachineAssignmentService().assign(
        order_public_id=order.public_id,
        machine_public_id=machine.public_id,
        actor=operator,
        source="test",
    )
    ProductionWorkflowService().transition_job(
        order_public_id=order.public_id,
        to_status=ProductionJob.Status.IN_PROGRESS,
        actor=operator,
        source="test",
    )
    panel_route = reverse(
        "portal:client-order-panel-production",
        kwargs={
            "customer_public_id": customer.public_id,
            "order_public_id": order.public_id,
        },
    )

    response = logged_client(client_user).get(panel_route)

    assert response.status_code == 200
    html = response.content.decode()
    assert "DTF-PRIVATE" not in html
    assert "Private machine name" not in html
    assert str(machine.public_id) not in html

    other_customer = Customer.objects.create(name="Other customer")
    CustomerMembership.objects.create(customer=other_customer, user=client_user)
    cross_tenant_route = reverse(
        "portal:client-order-panel-production",
        kwargs={
            "customer_public_id": other_customer.public_id,
            "order_public_id": order.public_id,
        },
    )
    cross_response = logged_client(client_user).get(cross_tenant_route)
    assert cross_response.status_code == 404
    assert "DTF-PRIVATE" not in cross_response.content.decode()
