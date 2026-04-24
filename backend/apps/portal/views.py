from __future__ import annotations

from collections import Counter
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from apps.accounts.services.access import AccessScopeService
from apps.billing.models import Invoice
from apps.billing.services.invoices import InvoiceService
from apps.billing.services.payments import PaymentService
from apps.orders.models import Order
from apps.orders.services.orders import OrderService
from apps.orders.services.pricing import OrderPricingService
from apps.portal.htmx import with_toast
from apps.production.models import ProductionJob
from apps.production.services.scans import ProductionScanService
from apps.production.services.workflow import ProductionWorkflowService
from apps.shipping.services.sendcloud import ShipmentService
from apps.uploads.models import OrderDriveFolder, OrderUploadDriveSync
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


def _staff_order_upload_rows(order):
    laize_cm = Decimal(int(getattr(settings, "DTF_LAIZE_CM", 55)))
    laize_m = (laize_cm / Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    uploads = list(upload_service.list_order_uploads(order=order))
    n = len(uploads)
    order_linear = getattr(order, "meterage_override_linear_m", None)
    rows = []
    for u in uploads:
        auto_m2 = order_pricing_service.estimate_meterage_from_inspection(upload=u)
        preview = None
        if order_linear is not None and n > 0:
            total_sqm = (order_linear * laize_m).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            preview = (total_sqm / Decimal(n)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        elif u.meterage_override_linear_m is not None:
            preview = (u.meterage_override_linear_m * laize_m * Decimal(u.quantity)).quantize(
                Decimal("0.0001"),
                rounding=ROUND_HALF_UP,
            )
        elif u.meterage_override_sqm is not None:
            preview = u.meterage_override_sqm
        sync = getattr(u, "drive_sync", None)
        drive_url = sync.google_drive_browser_url() if sync is not None else None
        rows.append(
            {
                "upload": u,
                "auto_m2": auto_m2,
                "billable_sqm_preview": preview,
                "drive_browser_url": drive_url,
            }
        )
    return rows


def _can_set_meterage_override(request, order: Order) -> bool:
    return (
        order.billing_mode == Order.BillingMode.DEFERRED
        and order.status in (Order.Status.DRAFT, Order.Status.SUBMITTED)
        and request.user.has_perm("orders.change_order")
    )


def _meterage_context_for_order(request, order: Order, form_error: str = "") -> dict:
    """Champs métrage B2B (panneau Production — saisie atelier)."""
    ol = getattr(order, "meterage_override_linear_m", None)
    order_billable_sqm_preview = None
    if ol is not None:
        lcm = Decimal(int(getattr(settings, "DTF_LAIZE_CM", 55)))
        lm = (lcm / Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        order_billable_sqm_preview = (ol * lm).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return {
        "form_error": form_error,
        "order_billable_sqm_preview": order_billable_sqm_preview,
        "can_set_meterage_override": _can_set_meterage_override(request, order),
        "dtf_laize_cm": int(getattr(settings, "DTF_LAIZE_CM", 55)),
    }


def _htmx_target_id(request) -> str:
    raw = (request.headers.get("HX-Target") or "").strip()
    return raw.lstrip("#")


class PortalLoginView(LoginView):
    template_name = "portal/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        redirect_to = self.get_redirect_url()
        if redirect_to and url_has_allowed_host_and_scheme(
            url=redirect_to,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return redirect_to
        if access_scope_service.can_access_staff_portal(self.request.user):
            return reverse("portal:staff-dashboard")
        return reverse("portal:client-dashboard")


class PortalLogoutView(LogoutView):
    next_page = "/login/"


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


class ClientDashboardView(LoginRequiredMixin, View):
    template_name = "portal/client/dashboard.html"

    def get(self, request):
        scope = access_scope_service.get_user_scope(request.user)
        memberships = list(scope.memberships)
        selected_membership = memberships[0] if memberships else None
        customer = None
        recent_orders = []
        if selected_membership is not None:
            customer = access_scope_service.get_customer_queryset(request.user).filter(
                public_id=selected_membership.customer_public_id
            ).first()
            if customer is not None:
                recent_orders = list(order_service.list_customer_orders(customer)[:5])
        kpi_rows = []
        if selected_membership is not None:
            kpi_rows = [
                {
                    "label": "Compte client",
                    "value": selected_membership.customer_name,
                    "hint": f"Role : {status_label(str(selected_membership.role))}",
                },
                {
                    "label": "Commandes recentes",
                    "value": str(len(recent_orders)),
                    "hint": None,
                },
            ]
        context = {
            "scope": scope,
            "memberships": memberships,
            "selected_membership": selected_membership,
            "customer": customer,
            "recent_orders": recent_orders,
            "kpi_rows": kpi_rows,
            "nav_mode": "client",
            "nav_key": "client-dashboard",
            "badge_tone_for_status": badge_tone_for_status,
            "status_label": status_label,
        }
        return render(request, self.template_name, context)


class ClientOrderListView(ScopedCustomerMixin, View):
    template_name = "portal/client/orders_list.html"

    def get(self, request, customer_public_id):
        orders = order_service.list_customer_orders(self.customer)
        return render(
            request,
            self.template_name,
            {
                "customer": self.customer,
                "orders": orders,
                "nav_mode": "client",
                "nav_key": "client-orders",
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class ClientOrderContextMixin(ScopedCustomerMixin):
    def get_order_or_404(self, order_public_id):
        order = order_service.get_customer_order(
            customer=self.customer,
            order_public_id=order_public_id,
        )
        if order is None:
            raise Http404
        return order


class ClientOrderDetailView(ClientOrderContextMixin, View):
    template_name = "portal/client/order_detail.html"

    def get(self, request, customer_public_id, order_public_id):
        order = self.get_order_or_404(order_public_id)
        return render(
            request,
            self.template_name,
            {
                "customer": self.customer,
                "order": order,
                "nav_mode": "client",
                "nav_key": "client-orders",
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class ClientOrderPanelUploadsView(ClientOrderContextMixin, View):
    template_name = "portal/client/panels/uploads.html"

    def get(self, request, customer_public_id, order_public_id):
        order = self.get_order_or_404(order_public_id)
        _order, uploads = upload_service.list_customer_order_uploads(
            customer=self.customer,
            order_public_id=order.public_id,
        )
        return render(
            request,
            self.template_name,
            {
                "customer": self.customer,
                "order": order,
                "uploads": uploads,
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class ClientOrderPanelInspectionView(ClientOrderContextMixin, View):
    template_name = "portal/client/panels/inspection.html"

    def get(self, request, customer_public_id, order_public_id):
        order = self.get_order_or_404(order_public_id)
        _order, uploads = upload_service.list_customer_order_uploads(
            customer=self.customer,
            order_public_id=order.public_id,
        )
        inspections = [upload.inspection for upload in uploads if hasattr(upload, "inspection")]
        inspection_counter = Counter(inspection.status for inspection in inspections)
        return render(
            request,
            self.template_name,
            {
                "order": order,
                "uploads": uploads,
                "inspections": inspections,
                "inspection_counter": inspection_counter,
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class ClientOrderPanelProductionView(ClientOrderContextMixin, View):
    template_name = "portal/client/panels/production.html"

    def get(self, request, customer_public_id, order_public_id):
        order = self.get_order_or_404(order_public_id)
        stage = "Traitement en cours"
        detail = "Votre commande est en cours de suivi par notre equipe."
        production_job = None
        try:
            production_job = order.production_job
        except ObjectDoesNotExist:
            production_job = None

        if production_job is not None:
            map_stage = {
                "queued": (
                    "Commande planifiee",
                    "Vos fichiers sont valides et la production est en file atelier.",
                ),
                "in_progress": (
                    "Commande en production",
                    "La production est en cours. Prochaine etape: preparation expedition.",
                ),
                "ready_to_ship": (
                    "Commande prete a expedier",
                    "La production est terminee. Expedition imminente.",
                ),
                "blocked": (
                    "Commande en attente d'action",
                    "Un point est en attente de resolution avant reprise.",
                ),
                "completed": (
                    "Production terminee",
                    "La commande est finalisee cote atelier.",
                ),
            }
            stage, detail = map_stage.get(
                production_job.status,
                ("Traitement en cours", "La commande progresse dans notre workflow."),
            )
        elif order.status == "draft":
            stage = "En attente de validation"
            detail = "Finalisez la commande pour lancer la production."
        elif order.status == "submitted":
            stage = "Commande en file de traitement"
            detail = "Votre commande est bien recue et sera traitee rapidement."

        return render(
            request,
            self.template_name,
            {
                "order": order,
                "stage": stage,
                "detail": detail,
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class ClientOrderPanelShippingView(ClientOrderContextMixin, View):
    template_name = "portal/client/panels/shipping.html"

    def get(self, request, customer_public_id, order_public_id):
        order = self.get_order_or_404(order_public_id)
        shipment = None
        try:
            shipment = order.shipment
        except ObjectDoesNotExist:
            shipment = None
        return render(
            request,
            self.template_name,
            {
                "order": order,
                "shipment": shipment,
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class ClientOrderPanelBillingView(ClientOrderContextMixin, View):
    template_name = "portal/client/panels/billing.html"

    def get(self, request, customer_public_id, order_public_id):
        order, payment, invoice = billing_service.get_customer_billing(
            customer=self.customer,
            order_public_id=order_public_id,
        )
        if order is None:
            raise Http404
        return render(
            request,
            self.template_name,
            {
                "order": order,
                "payment": payment,
                "invoice": invoice,
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class ClientCheckoutView(ScopedCustomerMixin, View):
    template_name = "portal/client/checkout.html"

    def get(self, request, customer_public_id):
        return render(
            request,
            self.template_name,
            self._build_context(request=request),
        )

    def post(self, request, customer_public_id):
        customer_note = request.POST.get("customer_note", "").strip()

        try:
            order = order_service.create_b2b_deferred_order(
                customer=self.customer,
                actor=request.user,
                customer_membership=self.customer_membership,
                customer_note=customer_note,
                source="client_checkout",
            )
        except ValidationError as exc:
            context = self._build_context(
                request=request,
                creation_error="; ".join(exc.messages),
            )
            return render(request, self.template_name, context, status=400)

        checkout_url = reverse(
            "portal:client-checkout",
            kwargs={"customer_public_id": self.customer.public_id},
        )
        return HttpResponseRedirect(f"{checkout_url}?order={order.public_id}")

    def _resolve_order(self, request):
        raw_order_public_id = str(request.GET.get("order", "")).strip()
        if not raw_order_public_id:
            return None
        try:
            order_public_id = UUID(raw_order_public_id)
        except ValueError:
            return None
        return order_service.get_customer_order(
            customer=self.customer,
            order_public_id=order_public_id,
        )

    def _build_context(self, *, request, creation_error: str = ""):
        order = self._resolve_order(request)
        uploads = []
        if order is not None:
            _order, uploads_qs = upload_service.list_customer_order_uploads(
                customer=self.customer,
                order_public_id=order.public_id,
            )
            uploads = list(uploads_qs)
        return {
            "customer": self.customer,
            "selected_order": order,
            "uploads": uploads,
            "creation_error": creation_error,
            "submit_error": request.GET.get("submit_error", ""),
            "nav_mode": "client",
            "nav_key": "client-checkout",
            "badge_tone_for_status": badge_tone_for_status,
            "status_label": status_label,
        }


class ClientCheckoutUploadPartialView(ScopedCustomerMixin, View):
    template_name = "portal/client/partials/checkout_uploads.html"

    def post(self, request, customer_public_id):
        order_public_id = request.POST.get("order_public_id", "").strip()
        try:
            order_public_id = UUID(order_public_id)
        except ValueError as exc:
            raise Http404 from exc
        upload_error = ""
        order = order_service.get_customer_order(
            customer=self.customer,
            order_public_id=order_public_id,
        )
        if order is None:
            raise Http404

        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            upload_error = "Selectionnez un fichier avant envoi."
        else:
            try:
                raw_qty = request.POST.get("quantity", "1").strip()
                try:
                    qty = int(raw_qty) if raw_qty else 1
                except ValueError as exc:
                    raise ValidationError("Quantité invalide.") from exc
                upload_service.create_upload(
                    customer=self.customer,
                    actor=request.user,
                    uploaded_file=uploaded_file,
                    customer_membership=self.customer_membership,
                    order_public_id=order.public_id,
                    source="client_checkout",
                    quantity=qty,
                    support_color_hex=request.POST.get("support_color_hex", "").strip(),
                )
            except ValidationError as exc:
                upload_error = "; ".join(exc.messages)

        _order, uploads_qs = upload_service.list_customer_order_uploads(
            customer=self.customer,
            order_public_id=order.public_id,
        )
        response = render(
            request,
            self.template_name,
            {
                "customer": self.customer,
                "order": order,
                "uploads": list(uploads_qs),
                "upload_error": upload_error,
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
            status=400 if upload_error else 200,
        )
        if upload_error:
            with_toast(response, upload_error, "error")
        else:
            response["HX-Trigger"] = "checkoutUploadsUpdated"
            with_toast(response, "Fichier ajoute.", "success")
        return response


class ClientCheckoutSummaryPartialView(ScopedCustomerMixin, View):
    template_name = "portal/client/partials/checkout_summary.html"

    def get(self, request, customer_public_id):
        raw_order_public_id = str(request.GET.get("order", "")).strip()
        try:
            order_public_id = UUID(raw_order_public_id)
        except ValueError as exc:
            raise Http404 from exc
        order = order_service.get_customer_order(
            customer=self.customer,
            order_public_id=order_public_id,
        )
        if order is None:
            raise Http404
        _order, uploads_qs = upload_service.list_customer_order_uploads(
            customer=self.customer,
            order_public_id=order.public_id,
        )
        return render(
            request,
            self.template_name,
            {
                "customer": self.customer,
                "order": order,
                "uploads": list(uploads_qs),
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class ClientCheckoutSubmitView(ScopedCustomerMixin, View):
    def post(self, request, customer_public_id):
        raw_order_public_id = str(request.POST.get("order_public_id", "")).strip()
        try:
            order_public_id = UUID(raw_order_public_id)
        except ValueError as exc:
            raise Http404 from exc
        checkout_url = reverse(
            "portal:client-checkout",
            kwargs={"customer_public_id": self.customer.public_id},
        )
        if request.POST.get("confirm_checkout") != "on":
            q = f"{checkout_url}?order={order_public_id}&submit_error=confirm"
            return HttpResponseRedirect(q)

        try:
            order_service.submit_b2b_deferred_order(
                customer=self.customer,
                actor=request.user,
                customer_membership=self.customer_membership,
                order_public_id=order_public_id,
                source="client_checkout",
            )
        except ValidationError:
            q = f"{checkout_url}?order={order_public_id}&submit_error=validation"
            return HttpResponseRedirect(q)

        detail_url = reverse(
            "portal:client-order-detail",
            kwargs={
                "customer_public_id": self.customer.public_id,
                "order_public_id": order_public_id,
            },
        )
        return HttpResponseRedirect(detail_url)


class StaffOrderPriceView(StaffPortalMixin, View):
    def post(self, request, order_public_id):
        if not request.user.has_perm("orders.change_order"):
            raise PermissionDenied
        order = order_service.get_staff_order(order_public_id)
        if order is None:
            raise Http404
        try:
            order_pricing_service.compute_and_persist_order_pricing(
                order=order,
                actor=request.user,
                source="staff_portal",
            )
        except ValidationError as exc:
            messages = getattr(exc, "messages", None) or [str(exc)]
            detail_url = reverse(
                "portal:staff-order-detail",
                kwargs={"order_public_id": order_public_id},
            )
            return HttpResponseRedirect(f"{detail_url}?price_error={' '.join(messages)[:200]}")
        detail_url = reverse(
            "portal:staff-order-detail",
            kwargs={"order_public_id": order_public_id},
        )
        return HttpResponseRedirect(f"{detail_url}?priced=1")


class StaffDashboardView(StaffPortalMixin, View):
    template_name = "portal/staff/dashboard.html"

    def get(self, request):
        can_read_orders = request.user.has_perm("orders.view_order")
        recent_orders = order_service.list_staff_orders()[:8] if can_read_orders else []
        access_label = "Autorise" if can_read_orders else "Refuse"
        kpi_rows = [
            {"label": "Acces commandes", "value": access_label, "hint": None},
            {
                "label": "Commandes affichees",
                "value": str(len(recent_orders)),
                "hint": None,
            },
        ]
        return render(
            request,
            self.template_name,
            {
                "recent_orders": recent_orders,
                "can_read_orders": can_read_orders,
                "kpi_rows": kpi_rows,
                "nav_mode": "staff",
                "nav_key": "staff-dashboard",
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class StaffOrderListView(StaffDomainPermissionMixin, View):
    template_name = "portal/staff/orders_list.html"
    required_permission = "orders.view_order"

    def get(self, request):
        orders = order_service.list_staff_orders()
        return render(
            request,
            self.template_name,
            {
                "orders": orders,
                "nav_mode": "staff",
                "nav_key": "staff-orders",
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class StaffOrderContextMixin(StaffDomainPermissionMixin):
    required_permission = "orders.view_order"
    order = None

    def dispatch(self, request, *args, **kwargs):
        order = order_service.get_staff_order(kwargs.get("order_public_id"))
        if order is None:
            raise Http404
        self.order = order
        return super().dispatch(request, *args, **kwargs)


class StaffOrderDetailView(StaffOrderContextMixin, View):
    template_name = "portal/staff/order_detail.html"

    def get(self, request, order_public_id):
        can_price = request.user.has_perm("orders.change_order")
        deferred = self.order.billing_mode == Order.BillingMode.DEFERRED
        try:
            production_job = self.order.production_job
        except ProductionJob.DoesNotExist:
            production_job = None
        drive_folder = OrderDriveFolder.objects.filter(order_id=self.order.pk).only(
            "order_folder_id"
        ).first()
        order_drive_url = (
            drive_folder.google_drive_folder_url() if drive_folder is not None else None
        )
        return render(
            request,
            self.template_name,
            {
                "order": self.order,
                "production_job": production_job,
                "order_drive_url": order_drive_url,
                "can_price_order": can_price and deferred,
                "price_error": request.GET.get("price_error", ""),
                "priced_ok": request.GET.get("priced") == "1",
                "nav_mode": "staff",
                "nav_key": "staff-orders",
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class StaffOrderPanelUploadsView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/uploads.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("uploads.view_orderupload"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def _staff_uploads_context(self, request):
        return {
            "order": self.order,
            "upload_rows": _staff_order_upload_rows(self.order),
            "badge_tone_for_status": badge_tone_for_status,
            "status_label": status_label,
        }

    def get(self, request, order_public_id):
        return render(
            request,
            self.template_name,
            self._staff_uploads_context(request),
        )


class StaffOrderPanelInspectionView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/inspection.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("uploads.view_orderuploadinspection"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, order_public_id):
        uploads = upload_service.list_order_uploads(order=self.order)
        flagged = [
            upload
            for upload in uploads
            if hasattr(upload, "inspection")
            and upload.inspection.status in {"warning", "error"}
        ]
        return render(
            request,
            self.template_name,
            {
                "order": self.order,
                "uploads": uploads,
                "flagged_uploads": flagged,
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


def _upload_needs_drive_attention(upload) -> bool:
    """True si pas de synchro, synchro non OK, ou erreur résiduelle."""
    sync = getattr(upload, "drive_sync", None)
    if sync is None:
        return True
    if sync.status != OrderUploadDriveSync.Status.SYNCED:
        return True
    if (sync.last_error or "").strip():
        return True
    return False


class StaffOrderPanelDriveSyncView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/drive_sync.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("uploads.view_orderuploaddrivesync"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, order_public_id):
        uploads = list(upload_service.list_order_uploads(order=self.order))
        drive_sync_problems = [u for u in uploads if _upload_needs_drive_attention(u)]
        return render(
            request,
            self.template_name,
            {
                "order": self.order,
                "uploads": uploads,
                "drive_sync_problems": drive_sync_problems,
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class StaffOrderPanelProductionView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/production.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("production.view_productionjob"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def _production_panel_context(self, request, job, transition_error: str = ""):
        meterage = _meterage_context_for_order(request, self.order, "")
        return {
            "order": self.order,
            "job": job,
            "allowed_statuses": [
                status for status in ProductionJob.Status.values if status != job.status
            ],
            "transition_error": transition_error,
            "meterage_hx_target": "#staff-order-meterage-slot-production",
            **meterage,
            "badge_tone_for_status": badge_tone_for_status,
            "status_label": status_label,
        }

    def get(self, request, order_public_id):
        _, job = production_workflow_service.get_staff_job(
            order_public_id=self.order.public_id,
            actor=request.user,
            source="staff_portal",
        )
        if job is None:
            raise Http404
        self.order.refresh_from_db()
        return render(
            request,
            self.template_name,
            self._production_panel_context(request, job, ""),
        )

    def post(self, request, order_public_id):
        if not request.user.has_perm("production.transition_productionjob"):
            raise PermissionDenied
        transition_error = ""
        try:
            _, job, _transition = production_workflow_service.transition_job(
                order_public_id=self.order.public_id,
                to_status=request.POST.get("to_status", ""),
                actor=request.user,
                reason=request.POST.get("reason", ""),
                source="staff_portal",
            )
        except ValidationError as exc:
            job = production_workflow_service.get_or_create_for_order(order=self.order)
            transition_error = "; ".join(exc.messages)
        self.order.refresh_from_db()
        response = render(
            request,
            self.template_name,
            self._production_panel_context(request, job, transition_error),
        )
        if transition_error:
            return with_toast(response, transition_error, "error")
        return with_toast(response, "Transition enregistree.", "success")


class StaffOrderPanelShippingView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/shipping.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("shipping.view_shipment"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, order_public_id):
        _order, shipment = shipment_service.get_staff_shipment(
            order_public_id=self.order.public_id,
            actor=request.user,
            source="staff_portal",
        )
        return render(
            request,
            self.template_name,
            {
                "order": self.order,
                "shipment": shipment,
                "form_error": "",
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )

    def post(self, request, order_public_id):
        if not request.user.has_perm("shipping.create_shipment"):
            raise PermissionDenied

        payload = {
            "shipping_option_code": request.POST.get("shipping_option_code", ""),
            "contract_id": request.POST.get("contract_id") or None,
            "recipient": {
                "name": request.POST.get("recipient_name", ""),
                "address_line_1": request.POST.get("recipient_address_line_1", ""),
                "house_number": request.POST.get("recipient_house_number", ""),
                "postal_code": request.POST.get("recipient_postal_code", ""),
                "city": request.POST.get("recipient_city", ""),
                "country_code": request.POST.get("recipient_country_code", ""),
                "email": request.POST.get("recipient_email", ""),
                "company_name": request.POST.get("recipient_company_name", ""),
                "address_line_2": request.POST.get("recipient_address_line_2", ""),
                "phone_number": request.POST.get("recipient_phone_number", ""),
            },
            "parcel": {
                "weight": {
                    "value": request.POST.get("parcel_weight_value", ""),
                    "unit": "kg",
                }
            },
            "label_details": {"mime_type": "application/pdf", "dpi": 72},
        }
        form_error = ""
        try:
            _order, shipment = shipment_service.create_shipment(
                order_public_id=self.order.public_id,
                actor=request.user,
                source="staff_portal",
                payload=payload,
            )
        except ValidationError as exc:
            _order, shipment = shipment_service.get_staff_shipment(
                order_public_id=self.order.public_id,
                actor=request.user,
                source="staff_portal",
            )
            form_error = "; ".join(exc.messages)

        response = render(
            request,
            self.template_name,
            {
                "order": self.order,
                "shipment": shipment,
                "form_error": form_error,
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )
        if form_error:
            return with_toast(response, form_error, "error")
        return with_toast(response, "Expedition creee.", "success")


class StaffOrderPanelShippingSyncView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/shipping.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("shipping.view_shipment"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, order_public_id):
        try:
            _order, shipment = shipment_service.sync_shipment_tracking_from_sendcloud(
                order_public_id=self.order.public_id,
                actor=request.user,
                source="staff_portal",
            )
        except ValidationError as exc:
            _order, shipment = shipment_service.get_staff_shipment(
                order_public_id=self.order.public_id,
                actor=request.user,
                source="staff_portal",
            )
            form_error = "; ".join(exc.messages)
            response = render(
                request,
                self.template_name,
                {
                    "order": self.order,
                    "shipment": shipment,
                    "form_error": form_error,
                    "badge_tone_for_status": badge_tone_for_status,
                    "status_label": status_label,
                },
            )
            return with_toast(response, form_error, "error")

        if _order is None or shipment is None:
            raise Http404

        response = render(
            request,
            self.template_name,
            {
                "order": self.order,
                "shipment": shipment,
                "form_error": "",
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )
        return with_toast(response, "Suivi Sendcloud actualise.", "success")


class StaffOrderPanelScanView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/scan.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("production.scan_productionjob"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, order_public_id):
        return render(
            request,
            self.template_name,
            {
                "order": self.order,
                "scan_result": None,
                "scan_error": "",
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )

    def post(self, request, order_public_id):
        scan_error = ""
        scan_result = None
        scan_identifier = request.POST.get("scan_identifier", "")
        to_status = request.POST.get("to_status", "").strip()
        reason = request.POST.get("reason", "")

        try:
            if to_status:
                if not request.user.has_perm("production.scan_transition_productionjob"):
                    raise PermissionDenied
                job, _transition = production_scan_service.transition_by_scan(
                    scan_identifier=scan_identifier,
                    to_status=to_status,
                    actor=request.user,
                    reason=reason,
                    source="staff_portal",
                )
                scan_result = {"job": job, "mode": "transition"}
            else:
                job = production_scan_service.resolve_scan(
                    scan_identifier=scan_identifier,
                    actor=request.user,
                    source="staff_portal",
                )
                scan_result = {"job": job, "mode": "resolve"}
        except ValidationError as exc:
            scan_error = "; ".join(exc.messages)

        response = render(
            request,
            self.template_name,
            {
                "order": self.order,
                "scan_result": scan_result,
                "scan_error": scan_error,
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )
        if scan_error:
            return with_toast(response, scan_error, "error")
        return with_toast(response, "Scan enregistre.", "success")


class StaffOrderPanelBillingView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/billing.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("billing.view_payment"):
            raise PermissionDenied
        if not request.user.has_perm("billing.view_invoice"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def _billing_context(self, request):
        _order, payment, invoice = billing_service.get_staff_billing(
            order_public_id=self.order.public_id,
            actor=request.user,
            source="staff_portal",
        )
        upload_rows = _staff_order_upload_rows(self.order)
        customer = self.order.customer
        can_mark_invoice_paid = (
            request.user.has_perm("billing.mark_invoice_paid")
            and invoice is not None
            and invoice.paid_at is None
            and customer.preferred_settlement_method == "wire_transfer"
        )
        return {
            "order": self.order,
            "payment": payment,
            "invoice": invoice,
            "upload_rows": upload_rows,
            "can_mark_invoice_paid": can_mark_invoice_paid,
            "badge_tone_for_status": badge_tone_for_status,
            "status_label": status_label,
        }

    def get(self, request, order_public_id):
        return render(
            request,
            self.template_name,
            self._billing_context(request),
        )

    def post(self, request, order_public_id):
        if not request.user.has_perm("orders.change_order"):
            raise PermissionDenied
        raw = request.POST.get("order_meterage_override_linear_m", "")
        tid = _htmx_target_id(request)
        slot_partial = tid.startswith("staff-order-meterage-slot")
        try:
            upload_service.set_staff_order_meterage_linear_override(
                order=self.order,
                actor=request.user,
                raw_value=raw,
            )
        except ValidationError as exc:
            msg = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            ctx = self._meterage_partial_context(request, form_error=msg, hx_target_id=tid)
            tpl = (
                "components/portal/staff_meterage_section.html"
                if slot_partial
                else self.template_name
            )
            response = render(request, tpl, ctx)
            return with_toast(response, msg, "error")
        self.order.refresh_from_db()
        ctx = self._meterage_partial_context(request, form_error="", hx_target_id=tid)
        if slot_partial:
            response = render(request, "components/portal/staff_meterage_section.html", ctx)
        else:
            response = render(request, self.template_name, self._billing_context(request))
        return with_toast(response, "Métrage linéaire commande enregistré.", "success")

    def _meterage_partial_context(self, request, *, form_error: str, hx_target_id: str):
        """Contexte pour le fragment métrage (HTMX) : cible du formulaire
        selon l’onglet d’origine.
        """
        base = _meterage_context_for_order(request, self.order, form_error)
        if hx_target_id and hx_target_id.startswith("staff-order-meterage-slot"):
            base["meterage_hx_target"] = f"#{hx_target_id}"
        else:
            base["meterage_hx_target"] = "#staff-order-panel"
        return {**self._billing_context(request), **base}


class StaffInvoiceMarkPaidView(StaffOrderContextMixin, View):
    """Marque la facture de la commande comme payée (virement reçu)."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("billing.view_invoice"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, order_public_id):
        if not request.user.has_perm("billing.mark_invoice_paid"):
            raise PermissionDenied
        invoice = Invoice.objects.filter(order=self.order).first()
        if invoice is None:
            raise Http404
        panel = StaffOrderPanelBillingView()
        panel.order = self.order
        try:
            invoice_domain_service.mark_invoice_paid_by_staff(
                invoice=invoice,
                actor=request.user,
                source="staff_portal.billing",
            )
        except ValidationError as exc:
            msg = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            response = render(request, panel.template_name, panel._billing_context(request))
            return with_toast(response, msg, "error")
        response = render(request, panel.template_name, panel._billing_context(request))
        return with_toast(response, "Facture marquée comme payée (virement reçu).", "success")
