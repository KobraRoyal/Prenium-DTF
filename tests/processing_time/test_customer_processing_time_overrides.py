from decimal import Decimal

import pytest
from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerMembership
from apps.orders.services.pricing import OrderPricingService
from apps.processing_time.models import CustomerProcessingTimeOptionOverride, ProcessingTimeOption
from apps.processing_time.services.customer_overrides import CustomerProcessingTimeOverrideService
from apps.processing_time.services.options import ProcessingTimeOptionService
from django.contrib.auth import get_user_model


def _seed_catalog() -> None:
    CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="100.00",
        currency="EUR",
        display_order=1,
    )
    CatalogService.objects.create(
        code="file-prep",
        name="Preparation fichier",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price="10.00",
        currency="EUR",
        display_order=2,
    )


@pytest.mark.django_db
def test_customer_processing_time_override_changes_quote_only_for_that_customer():
    user = get_user_model().objects.create_user(email="cust-a@example.com", password="pass")
    customer_a = Customer.objects.create(name="Client A")
    customer_b = Customer.objects.create(name="Client B")
    CustomerMembership.objects.create(customer=customer_a, user=user)
    _seed_catalog()
    ProcessingTimeOptionService().ensure_default_options()
    fast = ProcessingTimeOption.objects.get(code="fast")

    CustomerProcessingTimeOptionOverride.objects.create(
        customer=customer_a,
        option=fast,
        markup_percent=Decimal("10.00"),
    )

    quote_a = OrderPricingService().estimate_gang_sheet_quote(
        customer=customer_a,
        surface_sqm=Decimal("1.0000"),
        processing_time_code="fast",
    )
    quote_b = OrderPricingService().estimate_gang_sheet_quote(
        customer=customer_b,
        surface_sqm=Decimal("1.0000"),
        processing_time_code="fast",
    )

    assert quote_a["processing_time_markup_percent"] == Decimal("10.00")
    assert quote_a["processing_time_markup_amount"] == Decimal("10.00")
    assert quote_b["processing_time_markup_percent"] == Decimal("20.00")
    assert quote_b["processing_time_markup_amount"] == Decimal("20.00")


@pytest.mark.django_db
def test_disabled_processing_time_option_hidden_for_customer():
    user = get_user_model().objects.create_user(email="cust-b@example.com", password="pass")
    customer = Customer.objects.create(name="Client masque express")
    CustomerMembership.objects.create(customer=customer, user=user)
    ProcessingTimeOptionService().ensure_default_options()
    express = ProcessingTimeOption.objects.get(code="express")

    CustomerProcessingTimeOptionOverride.objects.create(
        customer=customer,
        option=express,
        is_enabled=False,
    )

    service = ProcessingTimeOptionService()
    options = service.list_active_options_for_customer(customer)
    codes = {option.code for option in options}
    assert "express" not in codes
    assert "standard" in codes
    assert "fast" in codes
    assert service.clamp_code_for_customer(customer=customer, code="express") == "standard"


@pytest.mark.django_db
def test_only_standard_enabled_hides_processing_time_ui_for_customer():
    customer = Customer.objects.create(name="Standard only")
    ProcessingTimeOptionService().ensure_default_options()
    for code in ("fast", "express"):
        CustomerProcessingTimeOptionOverride.objects.create(
            customer=customer,
            option=ProcessingTimeOption.objects.get(code=code),
            is_enabled=False,
        )

    ctx = ProcessingTimeOptionService().checkout_ui_context(customer=customer, widget="radios")
    assert len(ctx["processing_time_options"]) == 1
    assert ctx["show_processing_time_choice"] is False
    assert ctx["show_processing_time_quote_row"] is False
    assert ctx["selected_processing_time_code"] == "standard"


@pytest.mark.django_db
def test_customer_override_service_clears_row_when_back_to_global_defaults():
    customer = Customer.objects.create(name="Reset client")
    ProcessingTimeOptionService().ensure_default_options()
    service = CustomerProcessingTimeOverrideService()

    service.update_for_customer(
        customer=customer,
        payloads=[
            {
                "code": "fast",
                "is_enabled": True,
                "markup_percent": Decimal("15.00"),
                "flat_fee_eur": None,
            }
        ],
        actor=None,
        source="test",
    )
    assert CustomerProcessingTimeOptionOverride.objects.filter(customer=customer).count() == 1

    service.update_for_customer(
        customer=customer,
        payloads=[
            {
                "code": "fast",
                "is_enabled": True,
                "markup_percent": None,
                "flat_fee_eur": None,
            }
        ],
        actor=None,
        source="test",
    )
    assert CustomerProcessingTimeOptionOverride.objects.filter(customer=customer).count() == 0
