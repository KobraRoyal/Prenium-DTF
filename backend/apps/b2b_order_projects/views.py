from django.conf import settings
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.b2b_order_projects.permissions import (
    HasB2BOrderProjectFeatureAccess,
    HasStaffB2BOrderProjectReadAccess,
)
from apps.b2b_order_projects.services import B2BOrderProjectService, ProjectDomainError
from apps.customers.permissions import HasScopedCustomerAccess
from apps.uploads.services.assets import AssetDomainError, AssetService

project_service = B2BOrderProjectService()
asset_service = AssetService()


def serialize_asset(item) -> dict[str, object] | None:
    asset = getattr(item, "asset", None)
    version = getattr(asset, "current_version", None) if asset else None
    if version is None:
        return None
    analysis = getattr(version, "analysis", None)
    return {
        "public_id": str(asset.public_id),
        "version_public_id": str(version.public_id),
        "version_number": version.version_number,
        "original_filename": version.original_filename,
        "mime_type": version.mime_type,
        "size_bytes": version.size_bytes,
        "analysis_status": version.analysis_status,
        "analysis_error": version.analysis_error,
        "replace_allowed": asset_service.can_replace_project_item_file(item=item),
        "effective_dpi": asset_service.effective_dpi_for_item(item=item),
        "technical_review": asset_service.technical_review_for_item(item=item),
        "analysis": (
            {
                "image_width": analysis.image_width,
                "image_height": analysis.image_height,
                "dpi_x": _decimal(analysis.dpi_x),
                "dpi_y": _decimal(analysis.dpi_y),
                "has_alpha": analysis.has_alpha,
                "probable_white_background": analysis.probable_white_background,
                "warnings": analysis.warnings,
                "analyzed_at": analysis.analyzed_at.isoformat() if analysis.analyzed_at else None,
            }
            if analysis
            else None
        ),
    }


def serialize_item(item) -> dict[str, object]:
    return {
        "public_id": str(item.public_id),
        "name": item.name,
        "customer_reference": item.customer_reference,
        "placement": item.placement,
        "width_mm": f"{item.width_mm:.2f}",
        "height_mm": f"{item.height_mm:.2f}",
        "quantity": item.quantity,
        "rotation_allowed": item.rotation_allowed,
        "individual_cutting": item.individual_cutting,
        "support_color_hex": item.support_color_hex,
        "support_color_label": item.support_color_label,
        "support_color_is_multicolor": item.support_color_is_multicolor,
        "customer_comment": item.customer_comment,
        "status": item.status,
        "sort_order": item.sort_order,
        "client_confirmed_asset_version_public_id": (
            str(item.client_confirmed_asset_version.public_id)
            if item.client_confirmed_asset_version_id
            else None
        ),
        "client_confirmed_at": (
            item.client_confirmed_at.isoformat() if item.client_confirmed_at else None
        ),
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "asset": serialize_asset(item),
    }


def serialize_project(project, *, include_customer=False, include_items=True) -> dict[str, object]:
    payload = {
        "public_id": str(project.public_id),
        "project_number": project.project_number,
        "customer_public_id": str(project.customer.public_id),
        "name": project.name,
        "customer_reference": project.customer_reference,
        "end_customer_reference": project.end_customer_reference,
        "order_mode": project.order_mode,
        "status": project.status,
        "requested_date": project.requested_date.isoformat() if project.requested_date else None,
        "delivery_method": project.delivery_method,
        "shipping_address": project.shipping_address,
        "customer_comment": project.customer_comment,
        "estimated_length_mm": project.estimated_length_mm,
        "confirmed_length_mm": project.confirmed_length_mm,
        "estimated_subtotal": _decimal(project.estimated_subtotal),
        "estimated_tax": _decimal(project.estimated_tax),
        "estimated_total": _decimal(project.estimated_total),
        "confirmed_subtotal": _decimal(project.confirmed_subtotal),
        "confirmed_tax": _decimal(project.confirmed_tax),
        "confirmed_total": _decimal(project.confirmed_total),
        "price_confirmation_required": project.price_confirmation_required,
        "submitted_at": project.submitted_at.isoformat() if project.submitted_at else None,
        "converted_order_public_id": (
            str(project.converted_order.public_id) if project.converted_order else None
        ),
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }
    if include_items:
        payload["items"] = [serialize_item(item) for item in project.items.all()]
    if include_customer:
        payload["customer"] = {
            "public_id": str(project.customer.public_id),
            "name": project.customer.name,
        }
    return payload


def _decimal(value):
    return f"{value:.2f}" if value is not None else None


def domain_error_response(error: ProjectDomainError | AssetDomainError):
    return Response(
        {"code": error.code, "message": error.message, "details": error.details or {}},
        status=status.HTTP_400_BAD_REQUEST,
    )


def pagination_payload(page):
    return {
        "page": page.number,
        "page_size": page.paginator.per_page,
        "num_pages": page.paginator.num_pages,
        "total_items": page.paginator.count,
        "has_next": page.has_next(),
        "has_previous": page.has_previous(),
    }


class ClientProjectMixin:
    permission_classes = [IsAuthenticated, HasScopedCustomerAccess, HasB2BOrderProjectFeatureAccess]

    def get_project(self, project_public_id):
        project = project_service.get_customer_project(
            customer=self.customer,
            project_public_id=project_public_id,
        )
        if project is None:
            raise Http404
        return project


class ClientB2BOrderProjectListCreateView(ClientProjectMixin, APIView):
    def get(self, request, customer_public_id):
        page = Paginator(
            project_service.list_customer_projects(self.customer),
            settings.B2B_ORDER_PROJECT_LIST_PAGE_SIZE,
        ).get_page(request.query_params.get("page"))
        return Response(
            {
                "projects": [serialize_project(project, include_items=False) for project in page],
                "pagination": pagination_payload(page),
            }
        )

    def post(self, request, customer_public_id):
        try:
            project = project_service.create_project(
                customer=self.customer,
                actor=request.user,
                data=request.data,
                source="client_api",
            )
        except ProjectDomainError as error:
            return domain_error_response(error)
        return Response(serialize_project(project), status=status.HTTP_201_CREATED)


class ClientB2BOrderProjectDetailView(ClientProjectMixin, APIView):
    def get(self, request, customer_public_id, project_public_id):
        return Response(serialize_project(self.get_project(project_public_id)))

    def patch(self, request, customer_public_id, project_public_id):
        try:
            project = project_service.update_project(
                project=self.get_project(project_public_id),
                actor=request.user,
                data=request.data,
                source="client_api",
            )
        except ProjectDomainError as error:
            return domain_error_response(error)
        return Response(serialize_project(project))

    def delete(self, request, customer_public_id, project_public_id):
        try:
            project_service.delete_project(
                project=self.get_project(project_public_id),
                actor=request.user,
                source="client_api",
            )
        except ProjectDomainError as error:
            return domain_error_response(error)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ClientB2BOrderProjectItemCreateView(ClientProjectMixin, APIView):
    def post(self, request, customer_public_id, project_public_id):
        try:
            item = project_service.add_item(
                project=self.get_project(project_public_id),
                actor=request.user,
                data=request.data,
                source="client_api",
            )
        except ProjectDomainError as error:
            return domain_error_response(error)
        return Response(serialize_item(item), status=status.HTTP_201_CREATED)


class ClientB2BOrderProjectItemDetailView(ClientProjectMixin, APIView):
    def patch(self, request, customer_public_id, project_public_id, item_public_id):
        try:
            item = project_service.update_item(
                project=self.get_project(project_public_id),
                item_public_id=item_public_id,
                actor=request.user,
                data=request.data,
                source="client_api",
            )
        except ProjectDomainError as error:
            return domain_error_response(error)
        return Response(serialize_item(item))

    def delete(self, request, customer_public_id, project_public_id, item_public_id):
        try:
            project_service.delete_item(
                project=self.get_project(project_public_id),
                item_public_id=item_public_id,
                actor=request.user,
                source="client_api",
            )
        except ProjectDomainError as error:
            return domain_error_response(error)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ClientB2BOrderProjectItemDuplicateView(ClientProjectMixin, APIView):
    def post(self, request, customer_public_id, project_public_id, item_public_id):
        try:
            item = project_service.duplicate_item(
                project=self.get_project(project_public_id),
                item_public_id=item_public_id,
                actor=request.user,
                source="client_api",
            )
        except ProjectDomainError as error:
            return domain_error_response(error)
        return Response(serialize_item(item), status=status.HTTP_201_CREATED)


class ClientB2BOrderProjectItemAnalysisConfirmView(ClientProjectMixin, APIView):
    def post(self, request, customer_public_id, project_public_id, item_public_id):
        if request.data.get("confirmed") is not True:
            return Response(
                {
                    "code": "CONFIRMATION_REQUIRED",
                    "message": "Confirmez avoir vérifié les dimensions et alertes.",
                    "details": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            item = project_service.confirm_item_analysis(
                project=self.get_project(project_public_id),
                item_public_id=item_public_id,
                actor=request.user,
                data=request.data,
                source="client_api.analysis_confirmation",
            )
        except ProjectDomainError as error:
            return domain_error_response(error)
        return Response(serialize_item(item))


class ClientB2BOrderProjectItemReorderView(ClientProjectMixin, APIView):
    def post(self, request, customer_public_id, project_public_id):
        try:
            items = project_service.reorder_items(
                project=self.get_project(project_public_id),
                ordered_public_ids=request.data.get("item_public_ids", []),
                actor=request.user,
                source="client_api",
            )
        except ProjectDomainError as error:
            return domain_error_response(error)
        return Response({"items": [serialize_item(item) for item in items]})


class ClientB2BOrderProjectItemAssetView(ClientProjectMixin, APIView):
    def get(self, request, customer_public_id, project_public_id, item_public_id):
        item, version = asset_service.get_project_item_version(
            project=self.get_project(project_public_id),
            item_public_id=item_public_id,
        )
        if item is None:
            raise Http404
        return Response({"asset": serialize_asset(item) if version else None})

    def post(self, request, customer_public_id, project_public_id, item_public_id):
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response(
                {"code": "FILE_REQUIRED", "message": "Le fichier est obligatoire.", "details": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            asset_service.attach_project_item_file(
                project=self.get_project(project_public_id),
                item_public_id=item_public_id,
                actor=request.user,
                uploaded_file=uploaded_file,
                source="client_api",
            )
        except AssetDomainError as error:
            return domain_error_response(error)
        item, _version = asset_service.get_project_item_version(
            project=self.get_project(project_public_id), item_public_id=item_public_id
        )
        return Response({"asset": serialize_asset(item)}, status=status.HTTP_201_CREATED)


class ClientB2BOrderProjectItemAssetReplaceView(ClientProjectMixin, APIView):
    def post(self, request, customer_public_id, project_public_id, item_public_id):
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response(
                {"code": "FILE_REQUIRED", "message": "Le fichier est obligatoire.", "details": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            asset_service.replace_project_item_file(
                project=self.get_project(project_public_id),
                item_public_id=item_public_id,
                actor=request.user,
                uploaded_file=uploaded_file,
                source="client_api",
            )
        except AssetDomainError as error:
            return domain_error_response(error)
        item, _version = asset_service.get_project_item_version(
            project=self.get_project(project_public_id), item_public_id=item_public_id
        )
        return Response({"asset": serialize_asset(item)})


class ClientB2BOrderProjectItemAssetDownloadView(ClientProjectMixin, APIView):
    def get(self, request, customer_public_id, project_public_id, item_public_id):
        version = asset_service.prepare_project_download(
            project=self.get_project(project_public_id),
            item_public_id=item_public_id,
            actor=request.user,
            source="client_api",
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


class ClientB2BOrderProjectSubmitView(ClientProjectMixin, APIView):
    def post(self, request, customer_public_id, project_public_id):
        try:
            project = project_service.submit(
                project=self.get_project(project_public_id),
                actor=request.user,
                source="client_api",
            )
        except ProjectDomainError as error:
            return domain_error_response(error)
        return Response(serialize_project(project))


class ClientB2BOrderProjectCancelView(ClientB2BOrderProjectDetailView):
    def post(self, request, customer_public_id, project_public_id):
        return self.delete(request, customer_public_id, project_public_id)


class StaffB2BOrderProjectListView(APIView):
    permission_classes = [IsAuthenticated, HasStaffB2BOrderProjectReadAccess]

    def get(self, request):
        queryset = project_service.list_staff_projects().filter(
            status__in=["submitted", "under_review", "changes_requested"]
        )
        page = Paginator(queryset, settings.STAFF_B2B_ORDER_PROJECT_LIST_PAGE_SIZE).get_page(
            request.query_params.get("page")
        )
        return Response(
            {
                "projects": [
                    serialize_project(project, include_customer=True, include_items=False)
                    for project in page
                ],
                "pagination": pagination_payload(page),
            }
        )


class StaffB2BOrderProjectDetailView(APIView):
    permission_classes = [IsAuthenticated, HasStaffB2BOrderProjectReadAccess]

    def get(self, request, project_public_id):
        project = project_service.get_staff_project(project_public_id=project_public_id)
        if project is None:
            raise Http404
        return Response(serialize_project(project, include_customer=True))


class StaffB2BOrderProjectItemAssetDownloadView(APIView):
    permission_classes = [IsAuthenticated, HasStaffB2BOrderProjectReadAccess]

    def get(self, request, project_public_id, item_public_id):
        project = project_service.get_staff_project(project_public_id=project_public_id)
        if project is None:
            raise Http404
        version = asset_service.prepare_project_download(
            project=project,
            item_public_id=item_public_id,
            actor=request.user,
            source="staff_api",
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
