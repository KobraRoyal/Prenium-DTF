import csv
from datetime import datetime, time
from decimal import Decimal
from io import StringIO
from threading import Event, Thread

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.billing.forms import previous_closed_month_start
from apps.billing.models import BillingStatement
from apps.billing.services.statements import BillingStatementService
from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerVolumeDiscountTier
from apps.orders.models import Order, OrderLine
from apps.orders.services.orders import OrderService
from apps.orders.services.pricing import OrderPricingService
from apps.uploads.models import OrderUpload
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import (
    IntegrityError,
    close_old_connections,
    connection,
    connections,
    transaction,
)
from django.db.models.deletion import ProtectedError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient


def _staff_user(*, email: str, permissions: list[str]):
    user = get_user_model().objects.create_user(email=email, password="pass", is_staff=True)
    for codename in permissions:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


def _month_datetime(month_start, *, day: int = 10):
    return timezone.make_aware(
        datetime.combine(month_start.replace(day=day), time(hour=10)),
        timezone.get_current_timezone(),
    )


def _priced_deferred_order(
    *,
    customer: Customer,
    month_start,
    total: str = "95.00",
    subtotal: str = "90.00",
    shipping: str = "5.00",
    discount: str = "10.00",
    discount_percent: str = "10.00",
    create_line: bool = True,
):
    order = Order.objects.create(
        customer=customer,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PRICED,
        subtotal_amount=Decimal(subtotal),
        shipping_amount=Decimal(shipping),
        total_amount=Decimal(total),
        volume_discount_amount=Decimal(discount),
        volume_discount_percent=Decimal(discount_percent),
    )
    if create_line:
        recap_service, _created = CatalogService.objects.get_or_create(
            code="billing-recap-generic-line",
            defaults={
                "name": "Service comptable récapitulatif",
                "service_type": CatalogService.ServiceType.FILE_PREPARATION,
                "unit": CatalogService.Unit.FIXED,
                "base_price": Decimal("0.00"),
            },
        )
        OrderLine.objects.create(
            order=order,
            service=recap_service,
            position=1,
            service_code=recap_service.code,
            service_name=recap_service.name,
            service_type=recap_service.service_type,
            unit=recap_service.unit,
            quantity=Decimal("1.00"),
            unit_price=Decimal(subtotal),
            line_total=Decimal(subtotal),
        )
    Order.objects.filter(pk=order.pk).update(created_at=_month_datetime(month_start))
    order.refresh_from_db()
    return order


@pytest.mark.django_db
def test_generate_monthly_statement_groups_only_eligible_orders_and_audits():
    month = previous_closed_month_start()
    customer = Customer.objects.create(name="Client Encours")
    other_customer = Customer.objects.create(name="Autre Client")
    actor = _staff_user(email="billing@example.com", permissions=[])
    first = _priced_deferred_order(customer=customer, month_start=month)
    second = _priced_deferred_order(
        customer=customer,
        month_start=month,
        total="52.00",
        subtotal="50.00",
        shipping="2.00",
        discount="0.00",
        discount_percent="0.00",
    )
    immediate = _priced_deferred_order(customer=customer, month_start=month)
    immediate.billing_mode = Order.BillingMode.IMMEDIATE
    immediate.save(update_fields=["billing_mode", "updated_at"])
    pending = _priced_deferred_order(customer=customer, month_start=month)
    pending.pricing_status = Order.PricingStatus.PENDING
    pending.save(update_fields=["pricing_status", "updated_at"])
    foreign = _priced_deferred_order(customer=other_customer, month_start=month)

    statement = BillingStatementService().generate_monthly_statement(
        customer=customer,
        month=month,
        actor=actor,
        source="test",
    )

    assert statement.period_start == month
    assert statement.period_end.month == month.month
    assert statement.total_amount == Decimal("147.00")
    assert statement.currency == "EUR"
    assert statement.status == BillingStatement.Status.ISSUED
    assert statement.issued_at is not None
    assert statement.snapshot["version"] == 1
    assert len(statement.snapshot_sha256) == 64
    assert set(statement.orders.values_list("pk", flat=True)) == {first.pk, second.pk}
    for excluded in (immediate, pending, foreign):
        excluded.refresh_from_db()
        assert excluded.billing_statement_id is None
    assert AuditLogEntry.objects.filter(
        action="billing.statement_generated",
        target_public_id=statement.public_id,
    ).exists()

    with pytest.raises(ValidationError, match="existe déjà"):
        BillingStatementService().generate_monthly_statement(
            customer=customer,
            month=month,
            actor=actor,
            source="test.duplicate",
        )


@pytest.mark.django_db
def test_statement_export_contains_order_detail_total_and_safe_customer_text():
    month = previous_closed_month_start()
    customer = Customer.objects.create(
        name="=Client Comptable",
        billing_email="compta@example.com",
        siren="123456789",
        vat_number="FR00123456789",
        billing_address_line1="8 rue du Test",
        billing_postal_code="75001",
        billing_city="Paris",
    )
    order = _priced_deferred_order(
        customer=customer,
        month_start=month,
        create_line=False,
    )
    dtf_service = CatalogService.objects.create(
        code="dtf-recap",
        name="DTF",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price=Decimal("20.00"),
    )
    prep_service = CatalogService.objects.create(
        code="prep-recap",
        name="Préparation",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price=Decimal("10.00"),
    )
    OrderLine.objects.create(
        order=order,
        service=dtf_service,
        position=1,
        service_code=dtf_service.code,
        service_name=dtf_service.name,
        service_type=dtf_service.service_type,
        unit=dtf_service.unit,
        quantity=Decimal("5.50"),
        unit_price=Decimal("16.36"),
        line_total=Decimal("80.00"),
    )
    OrderLine.objects.create(
        order=order,
        service=prep_service,
        position=2,
        service_code=prep_service.code,
        service_name=prep_service.name,
        service_type=prep_service.service_type,
        unit=prep_service.unit,
        quantity=Decimal("1.00"),
        unit_price=Decimal("10.00"),
        line_total=Decimal("10.00"),
    )
    service = BillingStatementService()
    statement = service.generate_monthly_statement(
        customer=customer,
        month=month,
        actor=None,
        source="test",
    )
    statement = service.get_for_customer(
        customer=customer,
        statement_public_id=statement.public_id,
    )

    content = service.render_csv(statement=statement)
    assert content.startswith("\ufeff")
    rows = list(csv.DictReader(StringIO(content.lstrip("\ufeff")), delimiter=";"))

    assert [row["type_ligne"] for row in rows] == ["commande", "total"]
    assert rows[0]["client"] == "'=Client Comptable"
    assert rows[0]["surface_dtf_m2"] == "5,5000"
    assert rows[0]["volume_dtf_m_lineaires"] == "10,0000"
    assert rows[0]["dtf_brut_ht"] == "90,00"
    assert rows[0]["remise_volume_ht"] == "10,00"
    assert rows[0]["total_a_facturer_ht"] == "95,00"
    assert rows[1]["commande_reference"] == "TOTAL"
    assert rows[1]["total_a_facturer_ht"] == "95,00"
    assert "total_ttc" not in rows[0]


@pytest.mark.django_db
def test_statement_freezes_pricing_and_atelier_deletion():
    month = previous_closed_month_start()
    customer = Customer.objects.create(name="Client Figé")
    order = _priced_deferred_order(customer=customer, month_start=month)
    statement = BillingStatementService().generate_monthly_statement(
        customer=customer,
        month=month,
        actor=None,
        source="test",
    )
    order.refresh_from_db()

    assert "récapitulatif de facturation" in OrderService().staff_delete_block_reason(order)
    with pytest.raises(ValidationError, match="tarification est figée"):
        OrderPricingService().invalidate_deferred_pricing_after_meterage_change(
            order=order,
            actor=None,
            source="test",
        )
    with pytest.raises(ProtectedError):
        statement.delete()


@pytest.mark.django_db
def test_staff_can_generate_and_export_scoped_customer_statement():
    month = previous_closed_month_start()
    customer = Customer.objects.create(name="Client Export")
    other_customer = Customer.objects.create(name="Client Étranger")
    order = _priced_deferred_order(customer=customer, month_start=month)
    staff = _staff_user(
        email="statement@example.com",
        permissions=[
            "access_staff_portal",
            "view_customer",
            "view_billingstatement",
            "add_billingstatement",
        ],
    )
    client = APIClient()
    assert client.login(email=staff.email, password="pass") is True

    detail = client.get(
        reverse(
            "portal:staff-customer-detail",
            kwargs={"customer_public_id": customer.public_id},
        )
    )
    assert detail.status_code == 200
    assert b"customer-billing-statements" in detail.content

    create_response = client.post(
        reverse(
            "portal:staff-customer-billing-statement-create",
            kwargs={"customer_public_id": customer.public_id},
        ),
        {"statement-month": month.strftime("%Y-%m")},
    )
    assert create_response.status_code == 302
    statement = BillingStatement.objects.get(customer=customer)
    order.refresh_from_db()
    assert order.billing_statement_id == statement.pk

    export_url = reverse(
        "portal:staff-customer-billing-statement-export",
        kwargs={
            "customer_public_id": customer.public_id,
            "statement_public_id": statement.public_id,
        },
    )
    export_response = client.get(export_url)
    assert export_response.status_code == 200
    assert export_response["Content-Type"].startswith("text/csv")
    assert export_response["Cache-Control"] == "private, no-store"
    assert export_response["X-Content-Type-Options"] == "nosniff"
    assert export_response.content.startswith("\ufeff".encode())
    assert AuditLogEntry.objects.filter(
        action="billing.statement_exported",
        target_public_id=statement.public_id,
    ).exists()

    cross_customer_url = reverse(
        "portal:staff-customer-billing-statement-export",
        kwargs={
            "customer_public_id": other_customer.public_id,
            "statement_public_id": statement.public_id,
        },
    )
    assert client.get(cross_customer_url).status_code == 404


@pytest.mark.django_db
def test_staff_without_billing_permission_cannot_generate_statement():
    month = previous_closed_month_start()
    customer = Customer.objects.create(name="Client Protégé")
    _priced_deferred_order(customer=customer, month_start=month)
    staff = _staff_user(
        email="viewer-statement@example.com",
        permissions=["access_staff_portal", "view_customer"],
    )
    client = APIClient()
    assert client.login(email=staff.email, password="pass") is True

    detail = client.get(
        reverse(
            "portal:staff-customer-detail",
            kwargs={"customer_public_id": customer.public_id},
        )
    )
    assert detail.status_code == 200
    assert b"customer-billing-statements" not in detail.content

    response = client.post(
        reverse(
            "portal:staff-customer-billing-statement-create",
            kwargs={"customer_public_id": customer.public_id},
        ),
        {"statement-month": month.strftime("%Y-%m")},
    )
    assert response.status_code == 403
    assert not BillingStatement.objects.filter(customer=customer).exists()


@pytest.mark.django_db
def test_csv_is_stable_after_customer_and_order_data_change():
    month = previous_closed_month_start()
    customer = Customer.objects.create(
        name="Identité figée",
        billing_email="avant@example.com",
        billing_city="Lyon",
    )
    order = _priced_deferred_order(customer=customer, month_start=month)
    service = BillingStatementService()
    statement = service.generate_monthly_statement(
        customer=customer,
        month=month,
        actor=None,
        source="test",
    )
    first_export = service.render_csv(statement=statement)

    Customer.objects.filter(pk=customer.pk).update(
        name="Identité modifiée",
        billing_email="apres@example.com",
        billing_city="Bordeaux",
    )
    Order.objects.filter(pk=order.pk).update(
        subtotal_amount=Decimal("999.00"),
        shipping_amount=Decimal("1.00"),
        total_amount=Decimal("1000.00"),
    )
    statement.refresh_from_db()

    assert service.render_csv(statement=statement) == first_export
    assert "Identité figée" in first_export
    assert "Identité modifiée" not in first_export


@pytest.mark.django_db
def test_export_rejects_corrupted_cross_customer_order_relation():
    month = previous_closed_month_start()
    customer = Customer.objects.create(name="Client du relevé")
    other_customer = Customer.objects.create(name="Client intrus")
    order = _priced_deferred_order(customer=customer, month_start=month)
    service = BillingStatementService()
    statement = service.generate_monthly_statement(
        customer=customer,
        month=month,
        actor=None,
        source="test",
    )

    Order.objects.filter(pk=order.pk).update(customer=other_customer)
    statement.refresh_from_db()

    with pytest.raises(ValidationError, match="autre client"):
        service.render_csv(statement=statement)


@pytest.mark.django_db
def test_http_export_failure_is_generic_hardened_and_audited():
    month = previous_closed_month_start()
    customer = Customer.objects.create(name="Client confidentiel")
    other_customer = Customer.objects.create(name="Client à ne pas divulguer")
    order = _priced_deferred_order(customer=customer, month_start=month)
    statement = BillingStatementService().generate_monthly_statement(
        customer=customer,
        month=month,
        actor=None,
        source="test",
    )
    Order.objects.filter(pk=order.pk).update(customer=other_customer)
    staff = _staff_user(
        email="failed-export@example.com",
        permissions=[
            "access_staff_portal",
            "view_customer",
            "view_billingstatement",
        ],
    )
    client = APIClient()
    assert client.login(email=staff.email, password="pass") is True

    response = client.get(
        reverse(
            "portal:staff-customer-billing-statement-export",
            kwargs={
                "customer_public_id": customer.public_id,
                "statement_public_id": statement.public_id,
            },
        )
    )

    assert response.status_code == 409
    assert response["Cache-Control"] == "private, no-store"
    assert response["X-Content-Type-Options"] == "nosniff"
    body = response.content.decode()
    assert body == "Ce récapitulatif ne peut pas être exporté. Contactez un administrateur."
    assert other_customer.name not in body
    assert "autre client" not in body.lower()
    assert AuditLogEntry.objects.filter(
        action="billing.statement_export_failed",
        target_public_id=statement.public_id,
        metadata__reason_code="snapshot_integrity_validation_failed",
    ).exists()


@pytest.mark.django_db
def test_order_validation_rejects_statement_owned_by_another_customer():
    month = previous_closed_month_start()
    customer = Customer.objects.create(name="Client commande")
    other_customer = Customer.objects.create(name="Client relevé")
    order = _priced_deferred_order(customer=customer, month_start=month)
    foreign_statement = BillingStatement.objects.create(
        customer=other_customer,
        label="Relevé étranger",
        period_start=month,
        period_end=month,
        status=BillingStatement.Status.ISSUED,
        total_amount=Decimal("0.00"),
    )

    order.billing_statement = foreign_statement
    with pytest.raises(ValidationError, match="même client"):
        order.full_clean()


@pytest.mark.django_db
def test_one_statement_per_customer_and_month_is_database_enforced():
    month = previous_closed_month_start()
    customer = Customer.objects.create(name="Client unique")
    BillingStatement.objects.create(
        customer=customer,
        period_start=month,
        period_end=month,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        BillingStatement.objects.create(
            customer=customer,
            period_start=month,
            period_end=month.replace(day=2),
        )


@pytest.mark.django_db
def test_generation_rejects_mixed_order_currencies():
    month = previous_closed_month_start()
    customer = Customer.objects.create(name="Client multi-devises")
    _priced_deferred_order(customer=customer, month_start=month)
    usd_order = _priced_deferred_order(customer=customer, month_start=month)
    Order.objects.filter(pk=usd_order.pk).update(currency="USD")

    with pytest.raises(ValidationError, match="devise unique"):
        BillingStatementService().generate_monthly_statement(
            customer=customer,
            month=month,
            actor=None,
            source="test",
        )
    assert not BillingStatement.objects.filter(customer=customer).exists()


@pytest.mark.django_db
def test_generation_rejects_subtotal_not_matching_order_lines():
    month = previous_closed_month_start()
    customer = Customer.objects.create(name="Client ventilation incohérente")
    order = _priced_deferred_order(customer=customer, month_start=month)
    order.items.update(line_total=Decimal("89.00"))

    with pytest.raises(ValidationError, match="lignes comptables"):
        BillingStatementService().generate_monthly_statement(
            customer=customer,
            month=month,
            actor=None,
            source="test",
        )
    assert not BillingStatement.objects.filter(customer=customer).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "permissions",
    [
        ["access_staff_portal", "view_billingstatement", "add_billingstatement"],
        ["access_staff_portal", "view_customer", "add_billingstatement"],
        ["access_staff_portal", "view_customer", "view_billingstatement"],
        ["view_customer", "view_billingstatement", "add_billingstatement"],
    ],
)
def test_generation_requires_every_customer_and_billing_permission(permissions):
    month = previous_closed_month_start()
    customer = Customer.objects.create(name="Client matrice création")
    _priced_deferred_order(customer=customer, month_start=month)
    staff = _staff_user(
        email=f"matrix-create-{len(permissions)}-{permissions[-1]}@example.com",
        permissions=permissions,
    )
    client = APIClient()
    assert client.login(email=staff.email, password="pass") is True

    response = client.post(
        reverse(
            "portal:staff-customer-billing-statement-create",
            kwargs={"customer_public_id": customer.public_id},
        ),
        {"statement-month": month.strftime("%Y-%m")},
    )

    assert response.status_code == 403
    assert not BillingStatement.objects.filter(customer=customer).exists()


@pytest.mark.django_db
def test_generation_rejects_non_staff_and_anonymous_users():
    month = previous_closed_month_start()
    customer = Customer.objects.create(name="Client matrice identité")
    _priced_deferred_order(customer=customer, month_start=month)
    create_url = reverse(
        "portal:staff-customer-billing-statement-create",
        kwargs={"customer_public_id": customer.public_id},
    )
    non_staff = get_user_model().objects.create_user(
        email="non-staff-create@example.com",
        password="pass",
        is_staff=False,
    )
    for codename in (
        "access_staff_portal",
        "view_customer",
        "view_billingstatement",
        "add_billingstatement",
    ):
        non_staff.user_permissions.add(Permission.objects.get(codename=codename))
    client = APIClient()
    assert client.login(email=non_staff.email, password="pass") is True
    assert client.post(create_url, {"statement-month": month.strftime("%Y-%m")}).status_code == 403
    client.logout()
    assert client.post(create_url, {"statement-month": month.strftime("%Y-%m")}).status_code == 403
    assert not BillingStatement.objects.filter(customer=customer).exists()


@pytest.mark.django_db
def test_export_requires_customer_and_billing_permissions_and_staff_access():
    month = previous_closed_month_start()
    customer = Customer.objects.create(name="Client matrice export")
    _priced_deferred_order(customer=customer, month_start=month)
    statement = BillingStatementService().generate_monthly_statement(
        customer=customer,
        month=month,
        actor=None,
        source="test",
    )
    export_url = reverse(
        "portal:staff-customer-billing-statement-export",
        kwargs={
            "customer_public_id": customer.public_id,
            "statement_public_id": statement.public_id,
        },
    )

    for index, permissions in enumerate(
        (
            ["access_staff_portal", "view_customer"],
            ["access_staff_portal", "view_billingstatement"],
        )
    ):
        staff = _staff_user(
            email=f"matrix-export-{index}@example.com",
            permissions=permissions,
        )
        client = APIClient()
        assert client.login(email=staff.email, password="pass") is True
        assert client.get(export_url).status_code == 403

    non_staff = get_user_model().objects.create_user(
        email="non-staff-export@example.com",
        password="pass",
        is_staff=False,
    )
    for codename in ("access_staff_portal", "view_customer", "view_billingstatement"):
        non_staff.user_permissions.add(Permission.objects.get(codename=codename))
    client = APIClient()
    assert client.login(email=non_staff.email, password="pass") is True
    assert client.get(export_url).status_code == 403
    client.logout()
    assert client.get(export_url).status_code == 403


@pytest.mark.django_db(transaction=True)
@override_settings(DTF_LAIZE_CM=100)
def test_statement_waits_for_in_progress_pricing_and_captures_final_discount():
    if connection.vendor != "postgresql":
        pytest.skip("Ce test d’intégration exige les verrous de ligne PostgreSQL.")
    month = previous_closed_month_start()
    user = get_user_model().objects.create_user(
        email="concurrent-billing@example.com",
        password="pass",
    )
    customer = Customer.objects.create(
        name="Client concurrence",
        default_billing_mode=Order.BillingMode.DEFERRED,
    )
    CatalogService.objects.create(
        code="dtf-concurrent-statement",
        name="DTF concurrence",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price=Decimal("10.00"),
        currency="EUR",
        display_order=1,
    )
    CatalogService.objects.create(
        code="prep-concurrent-statement",
        name="Préparation concurrence",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price=Decimal("10.00"),
        currency="EUR",
        display_order=2,
    )
    CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m=Decimal("1.0000"),
        discount_percent=Decimal("10.00"),
    )
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PENDING,
        currency="EUR",
        meterage_override_linear_m=Decimal("1.0000"),
    )
    Order.objects.filter(pk=order.pk).update(created_at=_month_datetime(month))
    OrderUpload.objects.create(
        order=order,
        uploaded_by=user,
        file=f"orders/{order.public_id}/file.png",
        original_filename="file.png",
        mime_type="image/png",
        size_bytes=8,
        quantity=1,
    )
    pricing_has_lock = Event()
    release_pricing = Event()
    statement_started = Event()
    statement_done = Event()
    results: dict[str, object] = {}

    class BlockingPricingService(OrderPricingService):
        def resolve_unit_price_per_sqm(self, *, customer):
            pricing_has_lock.set()
            if not release_pricing.wait(timeout=5):
                raise RuntimeError("Le test n’a pas libéré la tarification.")
            return super().resolve_unit_price_per_sqm(customer=customer)

    def price_order():
        close_old_connections()
        try:
            results["priced"] = BlockingPricingService().compute_and_persist_order_pricing(
                order=Order.objects.get(pk=order.pk),
                actor=user,
                source="test.concurrent",
            )
        except Exception as exc:  # pragma: no cover - remonté dans le thread principal
            results["pricing_error"] = exc
        finally:
            connections.close_all()

    def generate_statement():
        close_old_connections()
        statement_started.set()
        try:
            results["statement"] = BillingStatementService().generate_monthly_statement(
                customer=Customer.objects.get(pk=customer.pk),
                month=month,
                actor=None,
                source="test.concurrent",
            )
        except Exception as exc:  # pragma: no cover - remonté dans le thread principal
            results["statement_error"] = exc
        finally:
            statement_done.set()
            connections.close_all()

    pricing_thread = Thread(target=price_order)
    statement_thread = Thread(target=generate_statement)
    try:
        pricing_thread.start()
        assert pricing_has_lock.wait(timeout=5)
        statement_thread.start()
        assert statement_started.wait(timeout=5)
        assert not statement_done.wait(timeout=0.25)
    finally:
        release_pricing.set()
        if pricing_thread.ident is not None:
            pricing_thread.join(timeout=10)
        if statement_thread.ident is not None:
            statement_thread.join(timeout=10)

    assert not pricing_thread.is_alive()
    assert not statement_thread.is_alive()
    assert "pricing_error" not in results
    assert "statement_error" not in results
    statement = results["statement"]
    assert isinstance(statement, BillingStatement)
    assert statement.snapshot["orders"][0]["volume_discount_percent"] == "10.00"
    assert statement.snapshot["orders"][0]["total_to_invoice_ht"] == "19.00"
