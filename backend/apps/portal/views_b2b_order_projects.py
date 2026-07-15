from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.b2b_order_projects.models import B2BOrderProject
from apps.b2b_order_projects.permissions import b2b_order_projects_enabled_for_customer
from apps.b2b_order_projects.services import (
    B2BOrderProjectCheckoutService,
    B2BOrderProjectConfiguratorService,
    B2BOrderProjectService,
    ProjectDomainError,
)
from apps.orders.references import project_client_reference
from apps.portal.htmx import with_toast
from apps.portal.views_common import (
    StaffDomainPermissionMixin,
    access_scope_service,
    status_label,
)
from apps.uploads.services.assets import AssetDomainError, AssetService

project_service = B2BOrderProjectService()
checkout_service = B2BOrderProjectCheckoutService()
asset_service = AssetService()
configurator_service = B2BOrderProjectConfiguratorService()


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
        for item in project.items.all():
            item.effective_dpi = asset_service.effective_dpi_for_item(item=item)
            item.technical_review = asset_service.technical_review_for_item(item=item)
            item.can_replace_asset = asset_service.can_replace_project_item_file(item=item)
        project.can_delete = project_service.can_client_delete(project)
        return project

    @staticmethod
    def attach_can_delete(projects):
        return project_service.attach_can_delete(projects)

    def context(self, **extra):
        project = extra.get("project")
        analysis_pending = False
        if project is not None:
            analysis_pending = any(
                item.asset_id
                and item.asset.current_version_id
                and item.asset.current_version.analysis_status in {"pending", "processing"}
                for item in project.items.all()
            )
        ctx = {
            "customer": self.customer,
            "membership": self.customer_membership,
            "nav_mode": "client",
            "nav_key": "client-checkout",
            "status_label": status_label,
            "analysis_pending": analysis_pending,
            **extra,
        }
        if project is not None:
            ctx["project_client_label"] = project_client_reference(project)
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
        return render(
            request,
            self.template_name,
            self.context(order_modes=B2BOrderProject.OrderMode.choices, form_error=""),
        )

    def post(self, request, customer_public_id):
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
        return HttpResponseRedirect(
            reverse(
                "portal:client-order-project-detail",
                kwargs={
                    "customer_public_id": self.customer.public_id,
                    "project_public_id": project.public_id,
                },
            )
        )


class ClientOrderProjectDetailView(ClientProjectFeatureMixin, View):
    template_name = "portal/client/order_project_detail.html"

    def get(self, request, customer_public_id, project_public_id):
        return render(
            request,
            self.template_name,
            self.context(
                project=self.get_project_or_404(project_public_id),
                order_modes=B2BOrderProject.OrderMode.choices,
                form_error="",
            ),
        )


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
                raise Http404
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
        form_error = ""
        active_validation_item = None
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            form_error = "Sélectionnez le fichier du visuel."
        else:
            try:
                item, _version = configurator_service.add_visual(
                    project=project,
                    actor=request.user,
                    data=request.POST,
                    uploaded_file=uploaded_file,
                    source="client_portal.configurator",
                )
                active_validation_item = item
            except (ProjectDomainError, AssetDomainError) as error:
                form_error = error.message
        project = self.get_project_or_404(project_public_id)
        if active_validation_item is not None:
            active_validation_item = next(
                entry
                for entry in project.items.all()
                if entry.public_id == active_validation_item.public_id
            )
        response = render(
            request,
            self.template_name,
            self.context(
                project=project,
                form_error=form_error,
                active_validation_item=active_validation_item,
            ),
            status=400 if form_error else 200,
        )
        return with_toast(
            response,
            form_error or "Visuel ajouté — contrôle technique en cours dans la fenêtre.",
            "error" if form_error else "success",
        )


class ClientOrderProjectItemActionView(ClientProjectFeatureMixin, View):
    template_name = "portal/client/partials/order_project_items_response.html"

    def post(self, request, customer_public_id, project_public_id, item_public_id, action):
        project = self.get_project_or_404(project_public_id)
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
                    source="client_portal",
                )
                message = "Ligne mise à jour."
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
        version = asset_service.prepare_project_download(
            project=self.get_project_or_404(project_public_id),
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
