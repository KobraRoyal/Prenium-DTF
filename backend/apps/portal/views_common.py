from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from apps.accounts.services.access import AccessScopeService
from apps.billing.services.invoices import InvoiceService
from apps.billing.services.payments import PaymentService
from apps.orders.models import Order
from apps.orders.services.orders import OrderService
from apps.orders.services.pricing import OrderPricingService
from apps.production.services.scans import ProductionScanService
from apps.production.services.workflow import ProductionWorkflowService
from apps.shipping.services.sendcloud import ShipmentService
from apps.uploads.services.uploads import OrderUploadService

access_scope_service = AccessScopeService()
order_service = OrderService()
upload_service = OrderUploadService()
production_workflow_service = ProductionWorkflowService()
production_scan_service = ProductionScanService()
shipment_service = ShipmentService()
billing_service = PaymentService()
invoice_domain_service = InvoiceService()
order_pricing_service = OrderPricingService()


def badge_tone_for_status(status: str) -> str:
    positive = {"ok", "synced", "created", "completed", "ready_to_ship", "submitted"}
    warning = {"warning", "pending", "queued", "in_progress"}
    negative = {"error", "failed", "blocked", "draft"}
    if status in positive:
        return "is-success"
    if status in warning:
        return "is-warning"
    if status in negative:
        return "is-danger"
    return "is-neutral"


def status_label(value: str) -> str:
    labels = {
        "draft": "Brouillon",
        "submitted": "Soumise",
        "pending": "En attente",
        "approved": "Approuvee",
        "captured": "Capturee",
        "failed": "En echec",
        "cancelled": "Annulee",
        "queued": "En file atelier",
        "in_progress": "En production",
        "ready_to_ship": "Prete a expedier",
        "completed": "Terminee",
        "blocked": "Bloquee",
        "created": "Creee",
        "issued": "Emise",
        "void": "Annulee",
        "immediate": "Paiement immediat",
        "deferred": "Facturation differee",
        "priced": "Prix calcule",
        "clear": "Encours dans la limite",
        "monthly": "Mensuelle",
        "bi_monthly": "Bi-mensuelle",
        "ok": "Valide",
        "warning": "A verifier",
        "error": "Erreur",
        "synced": "Synchronise",
    }
    key = str(value)
    return labels.get(key, key.replace("_", " ").capitalize())


def staff_order_upload_rows(order):
    laize_cm = Decimal(int(getattr(settings, "DTF_LAIZE_CM", 55)))
    laize_m = (laize_cm / Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    uploads = list(upload_service.list_order_uploads(order=order))
    upload_count = len(uploads)
    order_linear = getattr(order, "meterage_override_linear_m", None)
    rows = []
    for upload in uploads:
        auto_m2 = order_pricing_service.estimate_meterage_from_inspection(upload=upload)
        preview = None
        if order_linear is not None and upload_count > 0:
            total_sqm = (order_linear * laize_m).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            preview = (total_sqm / Decimal(upload_count)).quantize(
                Decimal("0.0001"),
                rounding=ROUND_HALF_UP,
            )
        elif upload.meterage_override_linear_m is not None:
            preview = (
                upload.meterage_override_linear_m * laize_m * Decimal(upload.quantity)
            ).quantize(
                Decimal("0.0001"),
                rounding=ROUND_HALF_UP,
            )
        elif upload.meterage_override_sqm is not None:
            preview = upload.meterage_override_sqm
        sync = getattr(upload, "drive_sync", None)
        drive_url = sync.google_drive_browser_url() if sync is not None else None
        rows.append(
            {
                "upload": upload,
                "auto_m2": auto_m2,
                "billable_sqm_preview": preview,
                "drive_browser_url": drive_url,
            }
        )
    return rows


def can_set_meterage_override(request, order: Order) -> bool:
    return (
        order.billing_mode == Order.BillingMode.DEFERRED
        and order.status in (Order.Status.DRAFT, Order.Status.SUBMITTED)
        and request.user.has_perm("orders.change_order")
    )


def meterage_context_for_order(request, order: Order, form_error: str = "") -> dict:
    """Champs métrage B2B (panneau Production — saisie atelier)."""
    order_linear = getattr(order, "meterage_override_linear_m", None)
    order_billable_sqm_preview = None
    if order_linear is not None:
        laize_cm = Decimal(int(getattr(settings, "DTF_LAIZE_CM", 55)))
        laize_m = (laize_cm / Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        order_billable_sqm_preview = (order_linear * laize_m).quantize(
            Decimal("0.0001"),
            rounding=ROUND_HALF_UP,
        )
    return {
        "form_error": form_error,
        "order_billable_sqm_preview": order_billable_sqm_preview,
        "can_set_meterage_override": can_set_meterage_override(request, order),
        "dtf_laize_cm": int(getattr(settings, "DTF_LAIZE_CM", 55)),
    }


def htmx_target_id(request) -> str:
    raw = (request.headers.get("HX-Target") or "").strip()
    return raw.lstrip("#")


class ScopedCustomerMixin(LoginRequiredMixin):
    customer = None
    customer_membership = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        customer_public_id = kwargs.get("customer_public_id")
        membership = access_scope_service.get_customer_membership(request.user, customer_public_id)
        if membership is None:
            raise PermissionDenied
        self.customer_membership = membership
        self.customer = membership.customer
        return super().dispatch(request, *args, **kwargs)


class StaffPortalMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not access_scope_service.can_access_staff_portal(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class StaffDomainPermissionMixin(StaffPortalMixin):
    required_permission = ""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.has_perm(self.required_permission):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
