from decimal import Decimal

import pytest
from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.orders.services.pricing import OrderPricingService
from apps.processing_time.models import ProcessingTimeOption
from apps.processing_time.services.options import ProcessingTimeOptionService
from django.contrib.auth import get_user_model
from django.test import TestCase


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
def test_processing_time_service_compute_surcharge_percent_and_flat_fee():
    ProcessingTimeOptionService().ensure_default_options()
    express = ProcessingTimeOption.objects.get(code="express")
    result = ProcessingTimeOptionService().compute_surcharge(
        dtf_amount=Decimal("100.00"),
        option=express,
    )
    assert result["processing_time_markup_percent"] == Decimal("40.00")
    assert result["processing_time_markup_amount"] == Decimal("40.00")
    assert result["processing_time_flat_fee"] == Decimal("7.00")
    assert result["processing_time_surcharge_amount"] == Decimal("47.00")


@pytest.mark.django_db
def test_checkout_ui_context_hides_choice_when_single_option_enabled():
    customer = Customer.objects.create(name="Single delay client")
    ProcessingTimeOptionService().ensure_default_options()
    express = ProcessingTimeOption.objects.get(code="express")
    fast = ProcessingTimeOption.objects.get(code="fast")
    express.is_active = False
    express.save(update_fields=["is_active"])
    fast.is_active = False
    fast.save(update_fields=["is_active"])

    ctx = ProcessingTimeOptionService().checkout_ui_context(customer=customer, widget="radios")
    assert ctx["show_processing_time_choice"] is False
    assert ctx["show_processing_time_quote_row"] is False
    assert ctx["selected_processing_time_code"] == "standard"
    assert len(ctx["processing_time_options"]) == 1


@pytest.mark.django_db
def test_estimate_gang_sheet_quote_applies_processing_time_surcharge():
    user = get_user_model().objects.create_user(email="quote@example.com", password="pass")
    customer = Customer.objects.create(name="Quote")
    CustomerMembership.objects.create(customer=customer, user=user)
    _seed_catalog()
    ProcessingTimeOptionService().ensure_default_options()

    pricing = OrderPricingService()
    standard = pricing.estimate_gang_sheet_quote(
        customer=customer,
        surface_sqm=Decimal("1.0000"),
        processing_time_code="standard",
    )
    fast = pricing.estimate_gang_sheet_quote(
        customer=customer,
        surface_sqm=Decimal("1.0000"),
        processing_time_code="fast",
    )

    assert standard["dtf_amount_eur"] == Decimal("100.00")
    assert standard["processing_time_surcharge_amount"] == Decimal("0.00")
    assert standard["subtotal_eur"] == Decimal("110.00")

    assert fast["processing_time_markup_percent"] == Decimal("20.00")
    assert fast["processing_time_markup_amount"] == Decimal("20.00")
    assert fast["subtotal_eur"] == Decimal("130.00")
    assert fast["prep_amount_eur"] == Decimal("10.00")


@pytest.mark.django_db
def test_processing_time_markup_excludes_prep_and_shipping():
    """La majoration % ne porte que sur le DTF ; préparation et port restent inchangés."""
    user = get_user_model().objects.create_user(email="scope@example.com", password="pass")
    customer = Customer.objects.create(name="Scope")
    CustomerMembership.objects.create(customer=customer, user=user)
    _seed_catalog()
    ProcessingTimeOptionService().ensure_default_options()
    from apps.shipping.models import ShippingMethod

    ShippingMethod.objects.update_or_create(
        code="standard",
        defaults={
            "name": "Standard",
            "base_price": Decimal("8.00"),
            "is_pickup": False,
            "is_active": True,
            "currency": "EUR",
            "display_order": 20,
        },
    )

    quote = OrderPricingService().estimate_gang_sheet_quote(
        customer=customer,
        surface_sqm=Decimal("1.0000"),
        file_count=3,
        processing_time_code="fast",
        shipping_method_code="standard",
    )

    assert quote["dtf_amount_eur"] == Decimal("100.00")
    assert quote["prep_amount_eur"] == Decimal("30.00")
    assert quote["processing_time_markup_amount"] == Decimal("20.00")
    assert quote["subtotal_eur"] == Decimal("150.00")
    assert quote["shipping_amount_eur"] == Decimal("8.00")


class ProcessingTimeSettingsFormTests(TestCase):
    def setUp(self):
        ProcessingTimeOptionService().ensure_default_options()
        self.options = list(ProcessingTimeOption.objects.order_by("display_order"))

    def test_settings_form_requires_single_default(self):
        from apps.processing_time.forms_staff import StaffProcessingTimeSettingsForm

        data = {}
        for option in self.options:
            prefix = option.code.replace("-", "_")
            data.update(
                {
                    f"{prefix}__name": option.name,
                    f"{prefix}__eta_label": option.eta_label,
                    f"{prefix}__disclaimer": option.disclaimer,
                    f"{prefix}__business_days": option.business_days,
                    f"{prefix}__markup_percent": str(option.markup_percent),
                    f"{prefix}__flat_fee_eur": str(option.flat_fee_eur),
                    f"{prefix}__is_default": option.is_default,
                    f"{prefix}__is_active": option.is_active,
                    f"{prefix}__display_order": option.display_order,
                }
            )
        data["standard__is_default"] = False
        data["fast__is_default"] = False
        data["express__is_default"] = False
        form = StaffProcessingTimeSettingsForm(data, options=tuple(self.options))
        assert not form.is_valid()
        assert "option par défaut" in str(form.errors).lower()

    def test_create_order_snapshots_processing_time(self):
        from apps.orders.services.orders import OrderService

        user = get_user_model().objects.create_user(email="order@example.com", password="pass")
        customer = Customer.objects.create(name="Order")
        membership = CustomerMembership.objects.create(customer=customer, user=user)
        order = OrderService().create_b2b_deferred_order(
            customer=customer,
            actor=user,
            customer_membership=membership,
            processing_time_code="fast",
        )
        assert order.processing_time_code == "fast"
        assert order.processing_time_markup_percent == Decimal("20.00")
