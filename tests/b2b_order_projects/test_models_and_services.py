from decimal import Decimal

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.b2b_order_projects.models import B2BOrderProject
from apps.b2b_order_projects.services import B2BOrderProjectService, ProjectDomainError
from apps.customers.models import Customer, CustomerMembership
from apps.uploads.services.asset_analysis import AssetAnalysisService
from apps.uploads.services.assets import AssetService
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from .helpers import png_upload


def customer_scope(email="owner@example.com", role=CustomerMembership.Role.OWNER):
    user = get_user_model().objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(name="Atelier", b2b_order_projects_enabled=True)
    membership = CustomerMembership.objects.create(customer=customer, user=user, role=role)
    return user, customer, membership


@pytest.mark.django_db
def test_project_service_creates_unique_numbers_and_audit_without_order_or_production_job():
    user, customer, _membership = customer_scope()
    service = B2BOrderProjectService()

    first = service.create_project(
        customer=customer, actor=user, data={"name": "Série été"}, source="test"
    )
    second = service.create_project(
        customer=customer, actor=user, data={"name": "Série hiver"}, source="test"
    )

    assert first.project_number.startswith("DTF-B2B-")
    assert first.project_number != second.project_number
    assert first.converted_order is None
    assert not hasattr(first, "production_job")
    assert AuditLogEntry.objects.filter(
        action="b2b_order_project.created", target_public_id=first.public_id
    ).exists()


@pytest.mark.django_db
def test_item_tenant_and_positive_constraints_are_enforced():
    user, customer, _membership = customer_scope()
    project = B2BOrderProjectService().create_project(
        customer=customer, actor=user, data={"name": "Projet"}, source="test"
    )

    with pytest.raises(ProjectDomainError, match="dimensions"):
        B2BOrderProjectService().add_item(
            project=project,
            actor=user,
            data={"name": "Logo", "width_mm": 0, "height_mm": 50, "quantity": 1},
            source="test",
        )

    item = B2BOrderProjectService().add_item(
        project=project,
        actor=user,
        data={"name": "Logo", "width_mm": "100.50", "height_mm": 50, "quantity": 2},
        source="test",
    )
    project.refresh_from_db()
    assert item.customer == customer
    assert item.width_mm == Decimal("100.50")
    assert project.status == B2BOrderProject.Status.INCOMPLETE

    other_customer = Customer.objects.create(name="Autre")
    item.customer = other_customer
    with pytest.raises(ValidationError, match="même client"):
        item.full_clean()

    with pytest.raises(IntegrityError):
        type(item).objects.create(
            customer=customer,
            project=project,
            name="Autre",
            width_mm=10,
            height_mm=10,
            quantity=1,
            sort_order=item.sort_order,
        )


@pytest.mark.django_db
def test_submit_locks_project_and_rejects_further_changes():
    user, customer, _membership = customer_scope()
    service = B2BOrderProjectService()
    project = service.create_project(
        customer=customer, actor=user, data={"name": "Projet"}, source="test"
    )
    item = service.add_item(
        project=project,
        actor=user,
        data={"name": "Logo", "width_mm": 100, "height_mm": 50, "quantity": 1},
        source="test",
    )
    version = AssetService().attach_project_item_file(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        uploaded_file=png_upload(),
        source="test",
    )
    AssetAnalysisService().analyze(version_public_id=version.public_id, source="test")
    project.refresh_from_db()

    assert project.status == B2BOrderProject.Status.ACTION_REQUIRED
    service.confirm_item_analysis(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        source="test",
    )
    project.refresh_from_db()

    submitted = service.submit(project=project, actor=user, source="test")
    assert submitted.status == B2BOrderProject.Status.SUBMITTED
    assert submitted.submitted_at is not None

    with pytest.raises(ProjectDomainError) as error:
        service.update_project(
            project=submitted, actor=user, data={"name": "Altéré"}, source="test"
        )
    assert error.value.code == "PROJECT_NOT_EDITABLE"


@pytest.mark.django_db
def test_invalid_transition_is_audited():
    user, customer, _membership = customer_scope()
    service = B2BOrderProjectService()
    project = service.create_project(
        customer=customer, actor=user, data={"name": "Vide"}, source="test"
    )

    with pytest.raises(ProjectDomainError) as error:
        service.submit(project=project, actor=user, source="test")

    assert error.value.code == "INVALID_PROJECT_TRANSITION"
    assert AuditLogEntry.objects.filter(
        action="b2b_order_project.transition_rejected",
        target_public_id=project.public_id,
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


@pytest.mark.django_db
def test_support_color_multicolor_is_normalized_on_item_update():
    user, customer, _membership = customer_scope("support-color@example.com")
    service = B2BOrderProjectService()
    project = service.create_project(
        customer=customer, actor=user, data={"name": "Couleur support"}, source="test"
    )
    item = service.add_item(
        project=project,
        actor=user,
        data={"name": "Logo", "width_mm": 100, "height_mm": 50, "quantity": 1},
        source="test",
    )
    item = service.update_item(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        data={"support_color_multicolor": "on"},
        source="test",
    )
    assert item.support_color_hex == "#multicolor"
    assert item.support_color_label == "Multicolore"


@pytest.mark.django_db
def test_dimension_change_invalidates_client_analysis_confirmation():
    user, customer, _membership = customer_scope("dimension-confirmation@example.com")
    service = B2BOrderProjectService()
    project = service.create_project(
        customer=customer, actor=user, data={"name": "Validation"}, source="test"
    )
    item = service.add_item(
        project=project,
        actor=user,
        data={"name": "Logo", "width_mm": 100, "height_mm": 50, "quantity": 1},
        source="test",
    )
    version = AssetService().attach_project_item_file(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        uploaded_file=png_upload(),
        source="test",
    )
    AssetAnalysisService().analyze(version_public_id=version.public_id, source="test")
    service.confirm_item_analysis(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        source="test",
    )

    service.update_item(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        data={"width_mm": "120.00"},
        source="test",
    )

    item.refresh_from_db()
    project.refresh_from_db()
    assert item.client_confirmed_asset_version is None
    assert item.client_confirmed_at is None
    assert project.status == B2BOrderProject.Status.ACTION_REQUIRED
    assert AuditLogEntry.objects.filter(
        action="b2b_order_project.item_analysis_confirmed",
        target_public_id=project.public_id,
    ).exists()
