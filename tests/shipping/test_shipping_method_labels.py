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


def test_processing_delay_label_names_the_mode_without_the_carrier():
    from types import SimpleNamespace

    from apps.shipping.services.methods import shipping_processing_delay_label

    standard = SimpleNamespace(name="Livraison standard", eta_label="2–3 jours · Chronopost 13")
    pickup = SimpleNamespace(name="Retrait atelier", eta_label="1–2 jours")

    assert shipping_processing_delay_label(standard) == "Standard — délai de traitement 2–3 jours"
    assert (
        shipping_processing_delay_label(pickup) == "Retrait atelier — délai de traitement 1–2 jours"
    )


def test_custom_shipping_delay_is_kept():
    method = ShippingMethod.objects.get(code="standard")
    method.eta_label = "Sous 5 jours"
    method.name = "Coursier privé"
    method.save(update_fields=["eta_label", "name", "updated_at"])

    ShippingMethodService().ensure_default_methods()

    method.refresh_from_db()
    assert method.eta_label == "Sous 5 jours"
    assert method.name == "Coursier privé"
