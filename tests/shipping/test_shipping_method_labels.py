import pytest
from apps.shipping.models import ShippingMethod
from apps.shipping.services.methods import ShippingMethodService

pytestmark = pytest.mark.django_db


def test_default_shipping_buttons_show_processing_time():
    ShippingMethodService().ensure_default_methods()

    labels = dict(ShippingMethod.objects.values_list("code", "eta_label"))
    labels = dict(ShippingMethod.objects.values_list("code", "eta_label"))
    names = dict(ShippingMethod.objects.values_list("code", "name"))
    assert labels["standard"] == "2–3 jours · Chronopost 13"
    assert labels["express"] == "1–2 jours · Chronopost 13"
    assert labels["pickup"] == "1–2 jours"
    assert names["standard"] == "Standard"
    assert names["express"] == "Express"
    assert names["pickup"] == "Retrait atelier"


def test_custom_shipping_delay_is_kept():
    method = ShippingMethod.objects.get(code="standard")
    method.eta_label = "Sous 5 jours"
    method.name = "Coursier privé"
    method.save(update_fields=["eta_label", "name", "updated_at"])

    ShippingMethodService().ensure_default_methods()

    method.refresh_from_db()
    assert method.eta_label == "Sous 5 jours"
    assert method.name == "Coursier privé"
