from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.b2b_order_projects.models import B2BOrderProject
from apps.b2b_order_projects.permissions import (
    b2b_order_projects_enabled_for_customer,
    client_new_order_url,
    customer_requires_gang_sheet_orders,
)
from apps.b2b_order_projects.services import (
    B2BOrderProjectCheckoutService,
    B2BOrderProjectConfiguratorService,
    B2BOrderProjectService,
    ProjectDomainError,
)
from apps.gang_sheets.models import GangSheet
from apps.orders.models import Order
from apps.orders.references import project_client_reference
from apps.orders.services.pricing import OrderPricingService
from apps.portal.htmx import with_toast
from apps.portal.views_common import (
    StaffDomainPermissionMixin,
    access_scope_service,
    status_label,
)
from apps.uploads.models import AssetVersion
from apps.uploads.services.assets import AssetDomainError, AssetService

project_service = B2BOrderProjectService()
checkout_service = B2BOrderProjectCheckoutService()
asset_service = AssetService()
configurator_service = B2BOrderProjectConfiguratorService()
order_pricing_service = OrderPricingService()

ANALYSIS_POLL_TIMEOUT = timedelta(minutes=2)
B2B_VISUAL_BATCH_MAX_FILES = 5
B2B_VISUAL_BATCH_PROXY_SAFE_BYTES = 60 * 1024 * 1024


def _format_upload_size(size_bytes: int) -> str:
    size_mb = max(0, int(size_bytes or 0)) / (1024 * 1024)
    return f"{size_mb:g} Mio"


def _safe_upload_name(uploaded_file) -> str:
    name = Path(str(getattr(uploaded_file, "name", "Visuel") or "Visuel")).name
    return name.replace("\r", " ").replace("\n", " ")[:120] or "Visuel"


def _client_upload_error_message(error) -> str:
    message = str(getattr(error, "message", "") or "")
    translations = {
        "File content does not match the declared file type.": (
            "Le contenu ne correspond pas au format annoncé. Réexportez le fichier puis réessayez."
        ),
        "File type is not allowed.": (
            "Ce format n’est pas accepté. Utilisez PNG, JPG, PDF, PSD, TIFF, EPS ou AI."
        ),
        "SVG files are not allowed.": (
            "Le format SVG n’est pas accepté. Exportez le visuel en PNG ou PDF."
        ),
        "File exceeds the maximum allowed size.": (
            "Ce fichier dépasse la taille autorisée. Réduisez-le ou compressez-le puis réessayez."
        ),
        "Empty files are not allowed.": "Ce fichier est vide. Réexportez-le puis réessayez.",
        "A valid MIME type is required.": (
            "Le format du fichier n’a pas pu être identifié. Réexportez-le puis réessayez."
        ),
        "File content could not be validated.": (
            "Le contenu du fichier n’a pas pu être contrôlé. Réexportez-le puis réessayez."
        ),
    }
    return translations.get(message, message or "Ce fichier n’a pas pu être ajouté.")


def _visual_batch_request_error(uploaded_files) -> str:
    if len(uploaded_files) > B2B_VISUAL_BATCH_MAX_FILES:
        return f"Sélectionnez au maximum {B2B_VISUAL_BATCH_MAX_FILES} fichiers à la fois."
    total_bytes = sum(
        int(getattr(uploaded_file, "size", 0) or 0) for uploaded_file in uploaded_files
    )
    # Garde une marge pour l'enveloppe multipart sous client_max_body_size 64m.
    max_total_bytes = min(
        B2B_VISUAL_BATCH_MAX_FILES * settings.ORDER_UPLOAD_MAX_BYTES,
        B2B_VISUAL_BATCH_PROXY_SAFE_BYTES,
    )
    if total_bytes > max_total_bytes:
        return (
            "La sélection dépasse la limite de "
            f"{_format_upload_size(max_total_bytes)} par envoi. "
            "Réduisez le nombre de fichiers puis réessayez."
        )
    return ""


def _add_visual_batch(*, project, actor, uploaded_files, quantity, source):
    """Orchestre un lot; chaque fichier garde la transaction isolée du service existant."""
    created_items = []
    upload_errors = []
    for uploaded_file in uploaded_files:
        display_name = _safe_upload_name(uploaded_file)
        try:
            item, _version = configurator_service.add_visual(
                project=project,
                actor=actor,
                data={"name": "", "quantity": quantity or "1"},
                uploaded_file=uploaded_file,
                source=source,
            )
            created_items.append(item)
        except (ProjectDomainError, AssetDomainError) as error:
            upload_errors.append(
                {"filename": display_name, "message": _client_upload_error_message(error)}
            )
    return created_items, upload_errors


def build_gang_sheet_project_quote(
    *,
    project,
    customer,
    shipping_method_code: str | None = None,
    billing_mode: str | None = None,
):
    """Devis produit + port + TVA (si comptant) pour Gang Sheet ou réassort."""
    if project is None:
        return None
    resolved_billing = billing_mode or getattr(
        customer, "default_billing_mode", Order.BillingMode.DEFERRED
    )
    if project.order_mode == B2BOrderProject.OrderMode.REORDER:
        items = list(
            project.items.order_by("sort_order", "created_at").only(
                "width_mm", "height_mm", "quantity"
            )
        )
        if not items:
            return None
        try:
            return order_pricing_service.estimate_reorder_quote(
                customer=customer,
                items=[
                    {
                        "width_mm": item.width_mm,
                        "height_mm": item.height_mm,
                        "quantity": item.quantity,
                    }
                    for item in items
                ],
                shipping_method_code=shipping_method_code,
                billing_mode=resolved_billing,
            )
        except ValidationError:
            return None
    if project.order_mode != B2BOrderProject.OrderMode.READY_GANG_SHEET:
        return None
    sheet = (
        GangSheet.objects.filter(project_id=project.pk)
        .order_by("-created_at")
        .only("surface_sqm")
        .first()
    )
    if sheet is None or sheet.surface_sqm is None or sheet.surface_sqm <= 0:
        return None
    item = project.items.order_by("sort_order", "created_at").only("quantity").first()
    quantity = item.quantity if item is not None else 1
    try:
        return order_pricing_service.estimate_gang_sheet_quote(
            customer=customer,
            surface_sqm=sheet.surface_sqm,
            quantity=quantity,
            file_count=1,
            shipping_method_code=shipping_method_code,
            billing_mode=resolved_billing,
        )
    except ValidationError:
        return None


class ClientProjectFeatureMixin(LoginRequiredMixin):
    customer = None
    customer_membership = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        membership = access_scope_service.get_customer_membership(
            request.user, kwargs.get("customer_public_id")
        )
        if membership is None:
            raise PermissionDenied
        self.customer_membership = membership
        self.customer = membership.customer
        if not b2b_order_projects_enabled_for_customer(self.customer):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_project_or_404(self, project_public_id):
        project = project_service.get_customer_project(
            customer=self.customer,
            project_public_id=project_public_id,
        )
        if project is None:
            raise Http404
        items = list(project.items.all())
        if project.order_mode == B2BOrderProject.OrderMode.READY_GANG_SHEET:
            production_asset_ids = {item.asset_id for item in items if item.asset_id}
        else:
            production_asset_ids = set(
                GangSheet.objects.filter(
                    customer=project.customer,
                    production_asset_id__in={item.asset_id for item in items if item.asset_id},
                ).values_list("production_asset_id", flat=True)
            )
        project.has_locked_gang_sheet_output = bool(production_asset_ids)
        for item in items:
            item.is_production_gang_sheet_asset = item.asset_id in production_asset_ids
            version = getattr(getattr(item, "asset", None), "current_version", None)
            item.analysis_pending = bool(
                version and version.analysis_status in {"pending", "processing"}
            )
            if item.is_production_gang_sheet_asset:
                item.technical_review = asset_service.production_review_for_item(item=item)
                item.effective_dpi = item.technical_review["effective_dpi"]
            else:
                item.effective_dpi = asset_service.effective_dpi_for_item(item=item)
                item.technical_review = asset_service.technical_review_for_item(item=item)
            item.can_replace_asset = (
                not item.is_production_gang_sheet_asset
                and asset_service.can_replace_project_item_file(item=item)
            )
        project.can_edit_items = project_service.transitions.is_editable(project.status)
        project.can_delete = project_service.can_client_delete(project)
        project.has_unconfirmed_analysis = any(
            item.technical_review.get("can_confirm") and not item.technical_review.get("confirmed")
            for item in items
        )
        project.can_confirm_all_analyses = bool(items) and all(
            item.technical_review.get("can_confirm") and item.support_color_hex for item in items
        )
        return project

    @staticmethod
    def attach_can_delete(projects):
        return project_service.attach_can_delete(projects)

    def context(self, **extra):
        project = extra.get("project")
        analysis_pending = False
        if project is not None:
            analysis_pending = any(
                getattr(
                    item,
                    "analysis_pending",
                    bool(
                        item.asset_id
                        and item.asset.current_version_id
                        and item.asset.current_version.analysis_status in {"pending", "processing"}
                    ),
                )
                for item in project.items.all()
            )
        ctx = {
            "customer": self.customer,
            "membership": self.customer_membership,
            "nav_mode": "client",
            "nav_key": "client-checkout",
            "status_label": status_label,
            "analysis_pending": analysis_pending,
            "b2b_visual_batch_max_files": B2B_VISUAL_BATCH_MAX_FILES,
            "b2b_visual_batch_max_file_bytes": settings.ORDER_UPLOAD_MAX_BYTES,
            "b2b_visual_batch_max_total_bytes": (
                min(
                    B2B_VISUAL_BATCH_MAX_FILES * settings.ORDER_UPLOAD_MAX_BYTES,
                    B2B_VISUAL_BATCH_PROXY_SAFE_BYTES,
                )
            ),
            "b2b_visual_batch_max_file_label": _format_upload_size(settings.ORDER_UPLOAD_MAX_BYTES),
            "b2b_visual_batch_max_total_label": _format_upload_size(
                min(
                    B2B_VISUAL_BATCH_MAX_FILES * settings.ORDER_UPLOAD_MAX_BYTES,
                    B2B_VISUAL_BATCH_PROXY_SAFE_BYTES,
                )
            ),
            **extra,
        }
        if project is not None:
            ctx["project_client_label"] = project_client_reference(project)
            shipping_method_code = extra.get("shipping_method_code")
            billing_mode = extra.get(
                "billing_mode",
                getattr(self.customer, "default_billing_mode", Order.BillingMode.DEFERRED),
            )
            quote = extra.get("gang_sheet_quote")
            if quote is None and "gang_sheet_quote" not in extra:
                quote = build_gang_sheet_project_quote(
                    project=project,
                    customer=self.customer,
                    shipping_method_code=shipping_method_code,
                    billing_mode=billing_mode,
                )
            ctx["gang_sheet_quote"] = quote
            from apps.shipping.services.methods import ShippingMethodService

            shipping_service = ShippingMethodService()
            shipping_service.ensure_default_methods()
            locks_pickup = shipping_service.customer_locks_shipping_to_pickup(self.customer)
            if locks_pickup:
                selected_shipping_code = "pickup"
                show_shipping_choice = False
                shipping_choice_widget = "hidden"
            else:
                if shipping_method_code:
                    selected_shipping_code = str(shipping_method_code).strip().lower()
                else:
                    selected_shipping_code = shipping_service.resolve_default_code_for_customer(
                        self.customer
                    )
                shipping_choice_widget = "radios"
                show_shipping_choice = True
            # Recalcule le devis avec le code réellement applicable (ex. verrou retrait).
            if quote is not None and (
                locks_pickup
                or str(quote.get("shipping_method_code") or "") != selected_shipping_code
            ):
                quote = build_gang_sheet_project_quote(
                    project=project,
                    customer=self.customer,
                    shipping_method_code=selected_shipping_code,
                    billing_mode=billing_mode,
                )
                ctx["gang_sheet_quote"] = quote
            ctx["shipping_methods"] = shipping_service.list_active_methods()
            ctx["selected_shipping_method_code"] = selected_shipping_code
            ctx["show_shipping_choice"] = show_shipping_choice
            ctx["shipping_choice_widget"] = shipping_choice_widget
            ctx["shipping_locked_to_pickup"] = locks_pickup
            ctx["cash_checkout_requires_gang_sheet"] = customer_requires_gang_sheet_orders(
                self.customer
            )
        return ctx


class ClientOrderProjectListView(ClientProjectFeatureMixin, View):
    template_name = "portal/client/order_projects_list.html"

    def get(self, request, customer_public_id):
        page = Paginator(
            project_service.list_customer_projects_in_progress(self.customer),
            settings.B2B_ORDER_PROJECT_LIST_PAGE_SIZE,
        ).get_page(request.GET.get("page"))
        projects = project_service.attach_can_delete(list(page.object_list))
        return render(
            request,
            self.template_name,
            self.context(projects=projects, page_obj=page),
        )


class ClientOrderProjectCreateView(ClientProjectFeatureMixin, View):
    template_name = "portal/client/order_project_form.html"

    def get(self, request, customer_public_id):
        if customer_requires_gang_sheet_orders(self.customer):
            return HttpResponseRedirect(client_new_order_url(customer=self.customer))
        return render(
            request,
            self.template_name,
            self.context(order_modes=B2BOrderProject.OrderMode.choices, form_error=""),
        )

    def post(self, request, customer_public_id):
        if customer_requires_gang_sheet_orders(self.customer):
            return HttpResponseRedirect(client_new_order_url(customer=self.customer))
        uploaded_files = request.FILES.getlist("file")
        batch_error = _visual_batch_request_error(uploaded_files)
        if batch_error:
            return render(
                request,
                self.template_name,
                self.context(
                    order_modes=B2BOrderProject.OrderMode.choices,
                    form_error=batch_error,
                    submitted=request.POST,
                ),
                status=400,
            )
        try:
            project = project_service.create_project(
                customer=self.customer,
                actor=request.user,
                data=request.POST,
                source="client_portal",
            )
        except ProjectDomainError as error:
            return render(
                request,
                self.template_name,
                self.context(
                    order_modes=B2BOrderProject.OrderMode.choices,
                    form_error=error.message,
                    submitted=request.POST,
                ),
                status=400,
            )

        detail_kwargs = {
            "customer_public_id": self.customer.public_id,
            "project_public_id": project.public_id,
        }
        detail_url = reverse("portal:client-order-project-detail", kwargs=detail_kwargs)
        if uploaded_files:
            created_items, upload_errors = _add_visual_batch(
                project=project,
                actor=request.user,
                uploaded_files=uploaded_files,
                quantity=request.POST.get("quantity") or "1",
                source="client_portal.create_visual_batch",
            )
            request.session[f"b2b_upload_batch:{project.public_id}"] = {
                "added": len(created_items),
                "errors": upload_errors,
            }
        return HttpResponseRedirect(detail_url)


class ClientOrderProjectDetailView(ClientProjectFeatureMixin, View):
    template_name = "portal/client/order_project_detail.html"

    def get(self, request, customer_public_id, project_public_id):
        project = self.get_project_or_404(project_public_id)
        upload_batch_result = request.session.pop(
            f"b2b_upload_batch:{project.public_id}",
            {},
        )
        active_validation_item = None
        validate_missing = False
        validate_id = (request.GET.get("validate") or "").strip()
        if validate_id:
            active_validation_item = next(
                (item for item in project.items.all() if str(item.public_id) == validate_id),
                None,
            )
            if active_validation_item is None:
                validate_missing = True
        response = render(
            request,
            self.template_name,
            self.context(
                project=project,
                order_modes=B2BOrderProject.OrderMode.choices,
                form_error="",
                active_validation_item=active_validation_item,
                validate_missing=validate_missing,
                upload_batch_added=upload_batch_result.get("added", 0),
                upload_batch_failed=len(upload_batch_result.get("errors", [])),
                upload_errors=upload_batch_result.get("errors", []),
                shipping_method_code=(
                    request.GET.get("shipping_method")
                    or request.GET.get("shipping_method_code")
                    or ""
                ).strip()
                or None,
            ),
        )
        if validate_missing:
            # Header utile pour HTMX ; le toast visible au full-page load
            # est déclenché côté template (voir order_project_detail.html).
            return with_toast(
                response,
                "Ce visuel n’est plus disponible pour la validation.",
                "warning",
            )
        return response


class ClientOrderProjectAutosaveView(ClientProjectFeatureMixin, View):
    template_name = "portal/client/partials/order_project_fields.html"

    def post(self, request, customer_public_id, project_public_id):
        project = self.get_project_or_404(project_public_id)
        form_error = ""
        try:
            project = project_service.update_project(
                project=project,
                actor=request.user,
                data=request.POST,
                source="client_portal.autosave",
            )
        except ProjectDomainError as error:
            form_error = error.message
            project.refresh_from_db()
        response = render(
            request,
            self.template_name,
            self.context(
                project=project,
                order_modes=B2BOrderProject.OrderMode.choices,
                form_error=form_error,
            ),
            status=400 if form_error else 200,
        )
        return with_toast(
            response,
            form_error or "Brouillon enregistré.",
            "error" if form_error else "success",
        )


class ClientOrderProjectItemCreateView(ClientProjectFeatureMixin, View):
    template_name = "portal/client/partials/order_project_items_response.html"

    def get(self, request, customer_public_id, project_public_id):
        project = self.get_project_or_404(project_public_id)
        item_public_id = request.GET.get("item")
        if item_public_id:
            item = next(
                (entry for entry in project.items.all() if str(entry.public_id) == item_public_id),
                None,
            )
            if item is None:
                # Ne pas renvoyer 404 : le poll HTMX laisserait sinon le spinner « Analyse… »
                # bloqué dans la modal (pas de swap sur erreur).
                return render(
                    request,
                    "portal/client/partials/order_project_add_visual_validation_interrupted.html",
                    self.context(
                        project=project,
                        title="Visuel introuvable",
                        message=(
                            "Ce fichier a été retiré ou n’est plus disponible. "
                            "Fermez la fenêtre pour continuer."
                        ),
                    ),
                )
            version = getattr(getattr(item, "asset", None), "current_version", None)
            if version is not None:
                version.refresh_from_db(
                    fields=[
                        "analysis_status",
                        "analysis_error",
                        "updated_at",
                        "auto_size_requested",
                    ]
                )
                item.analysis_pending = version.analysis_status in {
                    AssetVersion.AnalysisStatus.PENDING,
                    AssetVersion.AnalysisStatus.PROCESSING,
                }
                poll_deadline = timezone.now() - ANALYSIS_POLL_TIMEOUT
                if item.analysis_pending and version.updated_at <= poll_deadline:
                    AssetVersion.objects.filter(pk=version.pk).update(
                        analysis_status=AssetVersion.AnalysisStatus.FAILED,
                        analysis_error="Analyse trop longue — réessayez ou remplacez le fichier.",
                        updated_at=timezone.now(),
                    )
                    version.refresh_from_db(
                        fields=["analysis_status", "analysis_error", "updated_at"]
                    )
                    item.analysis_pending = False
                    item.technical_review = asset_service.technical_review_for_item(item=item)
                    return render(
                        request,
                        "portal/client/partials/order_project_add_visual_validation_interrupted.html",
                        self.context(
                            project=project,
                            item=item,
                            title="Analyse trop longue",
                            message=(
                                "Le contrôle technique n’a pas abouti. "
                                "Fermez, puis renvoyez le fichier ou contactez l’atelier."
                            ),
                        ),
                    )
            return render(
                request,
                "portal/client/partials/order_project_add_visual_validation_panel.html",
                self.context(project=project, item=item, form_error=""),
            )
        return render(
            request,
            self.template_name,
            self.context(project=project, form_error=""),
        )

    def post(self, request, customer_public_id, project_public_id):
        project = self.get_project_or_404(project_public_id)
        uploaded_files = request.FILES.getlist("file")
        form_error = _visual_batch_request_error(uploaded_files)
        upload_errors = []
        created_items = []
        if not uploaded_files:
            form_error = "Sélectionnez au moins un fichier."
        elif not form_error:
            created_items, upload_errors = _add_visual_batch(
                project=project,
                actor=request.user,
                uploaded_files=uploaded_files,
                quantity=request.POST.get("quantity") or "1",
                source="client_portal.configurator_batch",
            )
        project = self.get_project_or_404(project_public_id)
        response = render(
            request,
            self.template_name,
            self.context(
                project=project,
                form_error=form_error,
                upload_errors=upload_errors,
                upload_batch_added=len(created_items),
            ),
            status=400 if form_error else 200,
        )
        if form_error:
            message = form_error
            variant = "error"
        elif upload_errors:
            message = (
                f"{len(created_items)} visuel(s) ajouté(s), "
                f"{len(upload_errors)} fichier(s) refusé(s)."
            )
            variant = "warning"
        else:
            message = f"{len(created_items)} visuel(s) ajouté(s) — analyses en cours."
            variant = "success"
        return with_toast(
            response,
            message,
            variant,
        )


class ClientOrderProjectItemActionView(ClientProjectFeatureMixin, View):
    template_name = "portal/client/partials/order_project_items_response.html"

    def post(self, request, customer_public_id, project_public_id, item_public_id, action):
        project = self.get_project_or_404(project_public_id)
        is_autosave = request.POST.get("_autosave") == "1"
        try:
            if action == "confirm-analysis":
                if request.POST.get("confirm_analysis") != "on":
                    raise ProjectDomainError(
                        "CONFIRMATION_REQUIRED",
                        "Cochez la confirmation après avoir vérifié les dimensions et alertes.",
                    )
                project_service.confirm_item_analysis(
                    project=project,
                    item_public_id=item_public_id,
                    actor=request.user,
                    data=request.POST,
                    source="client_portal.analysis_confirmation",
                )
                message = "Dimensions et contrôle technique validés."
            elif action == "delete":
                project_service.delete_item(
                    project=project,
                    item_public_id=item_public_id,
                    actor=request.user,
                    source="client_portal",
                )
                message = "Ligne supprimée."
            elif action == "duplicate":
                project_service.duplicate_item(
                    project=project,
                    item_public_id=item_public_id,
                    actor=request.user,
                    source="client_portal",
                )
                message = "Ligne dupliquée."
            elif action == "update":
                project_service.update_item(
                    project=project,
                    item_public_id=item_public_id,
                    actor=request.user,
                    data=request.POST,
                    source="client_portal.autosave" if is_autosave else "client_portal",
                )
                message = "" if is_autosave else "Ligne mise à jour."
            else:
                raise Http404
            form_error = ""
        except ProjectDomainError as error:
            form_error = error.message
            message = form_error
        project = self.get_project_or_404(project_public_id)
        reset_add_visual_dialog = action == "confirm-analysis" and not form_error
        response = render(
            request,
            self.template_name,
            self.context(
                project=project,
                form_error=form_error,
                reset_add_visual_dialog=reset_add_visual_dialog,
            ),
            status=400 if form_error else 200,
        )
        if is_autosave and not form_error:
            return response
        return with_toast(response, message, "error" if form_error else "success")


class ClientOrderProjectConfirmAllAnalysesView(ClientProjectFeatureMixin, View):
    template_name = "portal/client/partials/order_project_items_response.html"

    def post(self, request, customer_public_id, project_public_id):
        project = self.get_project_or_404(project_public_id)
        try:
            confirmed_items = project_service.confirm_all_item_analyses(
                project=project,
                actor=request.user,
                source="client_portal.analysis_confirmation_all",
            )
            form_error = ""
            message = f"{len(confirmed_items)} visuel(s) validé(s) pour la commande."
        except ProjectDomainError as error:
            form_error = error.message
            message = form_error
        project = self.get_project_or_404(project_public_id)
        response = render(
            request,
            self.template_name,
            self.context(project=project, form_error=form_error),
            status=400 if form_error else 200,
        )
        return with_toast(response, message, "error" if form_error else "success")


class ClientOrderProjectItemAssetView(ClientProjectFeatureMixin, View):
    template_name = "portal/client/partials/order_project_items_response.html"

    def post(self, request, customer_public_id, project_public_id, item_public_id, action):
        project = self.get_project_or_404(project_public_id)
        uploaded_file = request.FILES.get("file")
        form_error = ""
        if uploaded_file is None:
            form_error = "Sélectionnez un fichier."
        else:
            try:
                if action == "attach":
                    configurator_service.complete_visual(
                        project=project,
                        item_public_id=item_public_id,
                        actor=request.user,
                        data=request.POST,
                        uploaded_file=uploaded_file,
                        source="client_portal.configurator",
                    )
                    message = "Fichier ajouté et analyse lancée."
                elif action == "replace":
                    asset_service.replace_project_item_file(
                        project=project,
                        item_public_id=item_public_id,
                        actor=request.user,
                        uploaded_file=uploaded_file,
                        source="client_portal",
                    )
                    message = "Nouvelle version ajoutée et analyse lancée."
                else:
                    raise Http404
            except (ProjectDomainError, AssetDomainError) as error:
                form_error = error.message
        if form_error:
            message = form_error
        project = self.get_project_or_404(project_public_id)
        response = render(
            request,
            self.template_name,
            self.context(project=project, form_error=form_error),
            status=400 if form_error else 200,
        )
        return with_toast(response, message, "error" if form_error else "success")


class ClientOrderProjectItemAssetDownloadView(ClientProjectFeatureMixin, View):
    def get(self, request, customer_public_id, project_public_id, item_public_id):
        project = self.get_project_or_404(project_public_id)
        item, _version = asset_service.get_project_item_version(
            project=project,
            item_public_id=item_public_id,
        )
        if (
            item is not None
            and GangSheet.objects.filter(
                customer=project.customer,
                production_asset=item.asset,
            ).exists()
        ):
            raise Http404
        version = asset_service.prepare_project_download(
            project=project,
            item_public_id=item_public_id,
            actor=request.user,
            source="client_portal",
        )
        if version is None:
            raise Http404
        version.file.open("rb")
        return FileResponse(
            version.file,
            as_attachment=True,
            filename=version.original_filename,
            content_type=version.mime_type,
        )


class ClientOrderProjectItemAssetPreviewView(ClientProjectFeatureMixin, View):
    def get(self, request, customer_public_id, project_public_id, item_public_id):
        preview = asset_service.prepare_project_preview(
            project=self.get_project_or_404(project_public_id),
            item_public_id=item_public_id,
        )
        if preview is None:
            raise Http404
        preview_file, content_type = preview
        preview_file.open("rb")
        response = FileResponse(preview_file, content_type=content_type)
        response["Content-Disposition"] = "inline"
        response["Cache-Control"] = "private, max-age=300"
        return response


class ClientOrderProjectItemThinZoneOverlayView(ClientProjectFeatureMixin, View):
    def get(self, request, customer_public_id, project_public_id, item_public_id):
        overlay = asset_service.prepare_project_thin_zone_overlay(
            project=self.get_project_or_404(project_public_id),
            item_public_id=item_public_id,
        )
        if overlay is None:
            raise Http404
        overlay_file, content_type = overlay
        overlay_file.open("rb")
        response = FileResponse(overlay_file, content_type=content_type)
        response["Content-Disposition"] = "inline"
        response["Cache-Control"] = "private, max-age=300"
        return response


class ClientOrderProjectItemSemiTransparencyOverlayView(ClientProjectFeatureMixin, View):
    def get(self, request, customer_public_id, project_public_id, item_public_id):
        overlay = asset_service.prepare_project_semi_transparency_overlay(
            project=self.get_project_or_404(project_public_id),
            item_public_id=item_public_id,
        )
        if overlay is None:
            raise Http404
        overlay_file, content_type = overlay
        overlay_file.open("rb")
        response = FileResponse(overlay_file, content_type=content_type)
        response["Content-Disposition"] = "inline"
        response["Cache-Control"] = "private, max-age=300"
        return response


class ClientOrderProjectSubmitView(ClientProjectFeatureMixin, View):
    def post(self, request, customer_public_id, project_public_id):
        project = self.get_project_or_404(project_public_id)
        if project.converted_order_id:
            return HttpResponseRedirect(
                reverse(
                    "portal:client-order-detail",
                    kwargs={
                        "customer_public_id": self.customer.public_id,
                        "order_public_id": project.converted_order.public_id,
                    },
                )
            )
        try:
            order = checkout_service.checkout_project(
                project=project,
                actor=request.user,
                customer_membership=self.customer_membership,
                source="client_portal.b2b_checkout",
                billing_mode=str(
                    request.POST.get("billing_mode")
                    or getattr(self.customer, "default_billing_mode", "deferred")
                ).strip(),
                shipping_method_code=(request.POST.get("shipping_method_code") or "").strip()
                or None,
            )
        except ProjectDomainError as error:
            project.refresh_from_db()
            submit_error = error.code.lower()
            if error.code == "INVALID_PROJECT_TRANSITION":
                submit_error = project.status
            elif error.code == "PROJECT_ALREADY_CONVERTED" and project.converted_order_id:
                return HttpResponseRedirect(
                    reverse(
                        "portal:client-order-detail",
                        kwargs={
                            "customer_public_id": self.customer.public_id,
                            "order_public_id": project.converted_order.public_id,
                        },
                    )
                )
            detail = reverse(
                "portal:client-order-project-detail",
                kwargs={
                    "customer_public_id": self.customer.public_id,
                    "project_public_id": project.public_id,
                },
            )
            if error.code == "GANG_SHEET_DRIVE_SYNC_REQUIRED":
                from urllib.parse import quote

                from apps.gang_sheets.services.drive import GangSheetDriveSyncService

                drive_service = GangSheetDriveSyncService()
                for sheet in GangSheet.objects.for_project(project).filter(
                    status=GangSheet.Status.VALIDATED
                ):
                    if sheet.final_file:
                        drive_service.schedule_sync(
                            sheet=sheet,
                            actor=request.user,
                            source="client_portal.checkout_retry",
                        )
                message = quote(error.message or "")
                return HttpResponseRedirect(
                    f"{detail}?submit_error={submit_error}&submit_message={message}"
                )
            return HttpResponseRedirect(f"{detail}?submit_error={submit_error}")
        except ValidationError as error:
            project.refresh_from_db()
            detail = reverse(
                "portal:client-order-project-detail",
                kwargs={
                    "customer_public_id": self.customer.public_id,
                    "project_public_id": project.public_id,
                },
            )
            messages = "; ".join(getattr(error, "messages", []) or [str(error)])
            from urllib.parse import quote

            return HttpResponseRedirect(
                f"{detail}?submit_error=validation&submit_message={quote(messages)}"
            )
        if (
            order.billing_mode == Order.BillingMode.IMMEDIATE
            and order.pricing_status == Order.PricingStatus.PRICED
        ):
            from apps.portal.views_common import billing_service
            from apps.portal.views_payments import available_payment_providers

            providers = available_payment_providers()
            if len(providers) == 1:
                provider = providers[0]["id"]
                success_path = reverse(
                    "portal:client-order-payment-return",
                    kwargs={
                        "customer_public_id": self.customer.public_id,
                        "order_public_id": order.public_id,
                    },
                )
                from django.conf import settings as dj_settings

                base = dj_settings.PUBLIC_BASE_URL.rstrip("/")
                if provider == "stripe":
                    success_url = (
                        f"{base}{success_path}?status=success&session_id={{CHECKOUT_SESSION_ID}}"
                    )
                else:
                    success_url = f"{base}{success_path}?status=success"
                cancel_url = f"{base}{success_path}?status=cancel"
                try:
                    _order, payment = billing_service.initiate_payment_for_customer_order(
                        customer=self.customer,
                        order_public_id=order.public_id,
                        actor=request.user,
                        provider=provider,
                        success_url=success_url,
                        cancel_url=cancel_url,
                        source="client_portal.b2b_checkout_pay",
                    )
                    if payment is not None and payment.approval_url:
                        return HttpResponseRedirect(payment.approval_url)
                except ValidationError:
                    pass
            return HttpResponseRedirect(
                reverse(
                    "portal:client-order-detail",
                    kwargs={
                        "customer_public_id": self.customer.public_id,
                        "order_public_id": order.public_id,
                    },
                )
                + "?panel=billing&checkout=success&pay=1"
            )
        return HttpResponseRedirect(
            reverse(
                "portal:client-order-detail",
                kwargs={
                    "customer_public_id": self.customer.public_id,
                    "order_public_id": order.public_id,
                },
            )
            + "?checkout=success"
        )


class ClientOrderProjectCancelView(ClientProjectFeatureMixin, View):
    def post(self, request, customer_public_id, project_public_id):
        project = self.get_project_or_404(project_public_id)
        list_url = reverse(
            "portal:client-order-project-list",
            kwargs={"customer_public_id": self.customer.public_id},
        )
        try:
            project_service.delete_project(
                project=project,
                actor=request.user,
                source="client_portal",
            )
        except ProjectDomainError as error:
            detail_url = reverse(
                "portal:client-order-project-detail",
                kwargs={
                    "customer_public_id": self.customer.public_id,
                    "project_public_id": project.public_id,
                },
            )
            return with_toast(HttpResponseRedirect(detail_url), error.message, "error")
        return with_toast(
            HttpResponseRedirect(list_url),
            "Commande supprimée.",
            "success",
        )


class StaffOrderProjectListView(StaffDomainPermissionMixin, View):
    required_permission = "b2b_order_projects.view_b2borderproject"
    template_name = "portal/staff/order_projects_list.html"

    def dispatch(self, request, *args, **kwargs):
        if not getattr(settings, "B2B_DTF_ORDER_PROJECT_ENABLED", False):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        page = Paginator(
            project_service.list_staff_projects().filter(
                status__in=[
                    B2BOrderProject.Status.SUBMITTED,
                    B2BOrderProject.Status.UNDER_REVIEW,
                    B2BOrderProject.Status.CHANGES_REQUESTED,
                ]
            ),
            settings.STAFF_B2B_ORDER_PROJECT_LIST_PAGE_SIZE,
        ).get_page(request.GET.get("page"))
        return render(
            request,
            self.template_name,
            {
                "projects": page.object_list,
                "page_obj": page,
                "nav_mode": "staff",
                "nav_key": "staff-order-projects",
                "status_label": status_label,
            },
        )


class StaffOrderProjectDetailView(StaffOrderProjectListView):
    template_name = "portal/staff/order_project_detail.html"

    def get(self, request, project_public_id):
        project = project_service.get_staff_project(project_public_id=project_public_id)
        if project is None:
            raise Http404
        return render(
            request,
            self.template_name,
            {
                "project": project,
                "nav_mode": "staff",
                "nav_key": "staff-order-projects",
                "status_label": status_label,
            },
        )


class StaffOrderProjectItemAssetDownloadView(StaffOrderProjectListView):
    def get(self, request, project_public_id, item_public_id):
        project = project_service.get_staff_project(project_public_id=project_public_id)
        if project is None:
            raise Http404
        version = asset_service.prepare_project_download(
            project=project,
            item_public_id=item_public_id,
            actor=request.user,
            source="staff_portal",
        )
        if version is None:
            raise Http404
        version.file.open("rb")
        return FileResponse(
            version.file,
            as_attachment=True,
            filename=version.original_filename,
            content_type=version.mime_type,
        )
