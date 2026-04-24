from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404, HttpResponse
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import (
    HasStaffProductionReadAccess,
    HasStaffProductionScanResolveAccess,
    HasStaffProductionScanTransitionAccess,
    HasStaffProductionTransitionAccess,
)
from apps.production.services.manufacturing_order_pdf import render_manufacturing_order_pdf_bytes
from apps.production.services.scans import ProductionScanService
from apps.production.services.workflow import ProductionWorkflowService

production_scan_service = ProductionScanService()
production_workflow_service = ProductionWorkflowService()


def raise_api_validation_error(error: DjangoValidationError):
    if hasattr(error, "message_dict"):
        raise DRFValidationError(error.message_dict)
    raise DRFValidationError({"detail": error.messages})


def serialize_job(job, *, order, manufacturing_order) -> dict[str, object]:
    transitions = [
        production_workflow_service.serialize_transition(transition)
        for transition in job.transitions.all()
    ]
    recent_scan_logs = [
        production_scan_service.serialize_scan_log(scan_log)
        for scan_log in job.scan_logs.all()[:10]
    ]
    return {
        "public_id": str(job.public_id),
        "order_public_id": str(order.public_id),
        "customer": {
            "public_id": str(order.customer.public_id),
            "name": order.customer.name,
        },
        "status": job.status,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "last_transition_at": job.last_transition_at.isoformat()
        if job.last_transition_at
        else None,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "scan": production_workflow_service.build_scan_payload(production_job=job),
        "transitions": transitions,
        "history": transitions,
        "recent_scan_logs": recent_scan_logs,
        "manufacturing_order": manufacturing_order,
    }


class StaffManufacturingOrderPdfView(APIView):
    permission_classes = [IsAuthenticated, HasStaffProductionReadAccess]

    def get(self, request, order_public_id):
        order, job = production_workflow_service.get_staff_job_for_document(
            order_public_id=order_public_id,
        )
        if order is None or job is None:
            raise Http404
        pdf_bytes = render_manufacturing_order_pdf_bytes(order=order, production_job=job)
        filename = f"{job.manufacturing_order_number}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class StaffProductionJobDetailView(APIView):
    permission_classes = [IsAuthenticated, HasStaffProductionReadAccess]

    def get(self, request, order_public_id):
        order, job = production_workflow_service.get_staff_job(
            order_public_id=order_public_id,
            actor=request.user,
            source="staff_api",
        )
        if order is None or job is None:
            raise Http404
        return Response(
            serialize_job(
                job,
                order=order,
                manufacturing_order=production_workflow_service.build_manufacturing_order(
                    order=order,
                    production_job=job,
                ),
            )
        )


class StaffProductionJobTransitionView(APIView):
    permission_classes = [IsAuthenticated, HasStaffProductionTransitionAccess]

    def post(self, request, order_public_id):
        try:
            order, job, _transition = production_workflow_service.transition_job(
                order_public_id=order_public_id,
                to_status=request.data.get("to_status", ""),
                actor=request.user,
                reason=request.data.get("reason", ""),
                source="staff_api",
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        if order is None or job is None:
            raise Http404

        return Response(
            serialize_job(
                job,
                order=order,
                manufacturing_order=production_workflow_service.build_manufacturing_order(
                    order=order,
                    production_job=job,
                ),
            )
        )


class StaffProductionScanResolveView(APIView):
    permission_classes = [
        IsAuthenticated,
        HasStaffProductionReadAccess,
        HasStaffProductionScanResolveAccess,
    ]

    def post(self, request):
        try:
            job = production_scan_service.resolve_scan(
                scan_identifier=request.data.get("scan_identifier", ""),
                actor=request.user,
                source="staff_scan_api",
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)
        if job is None:
            raise Http404

        return Response(
            serialize_job(
                job,
                order=job.order,
                manufacturing_order=production_workflow_service.build_manufacturing_order(
                    order=job.order,
                    production_job=job,
                ),
            )
        )


class StaffProductionScanTransitionView(APIView):
    permission_classes = [
        IsAuthenticated,
        HasStaffProductionReadAccess,
        HasStaffProductionTransitionAccess,
        HasStaffProductionScanTransitionAccess,
    ]

    def post(self, request):
        try:
            job, _transition = production_scan_service.transition_by_scan(
                scan_identifier=request.data.get("scan_identifier", ""),
                to_status=request.data.get("to_status", ""),
                actor=request.user,
                reason=request.data.get("reason", ""),
                source="staff_scan_api",
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        if job is None:
            raise Http404

        return Response(
            serialize_job(
                job,
                order=job.order,
                manufacturing_order=production_workflow_service.build_manufacturing_order(
                    order=job.order,
                    production_job=job,
                ),
            )
        )
