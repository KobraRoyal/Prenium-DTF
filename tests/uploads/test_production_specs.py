from decimal import Decimal

from apps.uploads.models import OrderUpload
from apps.uploads.services.production_specs import OrderUploadProductionSpecService


def test_production_specs_format_client_dimensions_and_multicolor_support():
    upload = OrderUpload(
        width_mm=Decimal("120.50"),
        height_mm=Decimal("80.00"),
        support_color_hex="#multicolor",
    )

    specs = OrderUploadProductionSpecService().serialize(order_upload=upload)

    assert specs["dimensions_label"] == "120,5 × 80 mm"
    assert specs["support_color_label"] == "Multicolore"
    assert specs["support_color_is_multicolor"] is True


def test_production_specs_make_missing_client_information_explicit():
    upload = OrderUpload(width_mm=None, height_mm=None, support_color_hex="")

    specs = OrderUploadProductionSpecService().serialize(order_upload=upload)

    assert specs["dimensions_label"] == "Non renseignée"
    assert specs["support_color_label"] == "Non renseignée"
