from apps.orders.models import Order
from apps.uploads.models import OrderUploadReview


def external_order_blocked_reason(order) -> str | None:
    """Le parcours manuel exige métrage, tarif et contrôle humain avant impression."""
    external_uploads = [upload for upload in order.uploads.all() if upload.is_external]
    if not external_uploads:
        return None
    meterage = order.meterage_override_linear_m
    if meterage is None or meterage <= 0 or order.pricing_status != Order.PricingStatus.PRICED:
        return "Commande par lien : renseignez le métrage et calculez le tarif avant production."
    if any(
        getattr(getattr(upload, "atelier_review", None), "status", None)
        != OrderUploadReview.Status.APPROVED
        for upload in external_uploads
    ):
        return "Commande par lien : validez le contrôle manuel des fichiers avant production."
    return None
