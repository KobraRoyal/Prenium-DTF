from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.inventory.services import WarehouseLayoutService
from apps.pod.models import BlankPlacementCapability
from apps.pod.services import BlankCatalogService, PrintTechniqueService
from apps.pod.services.validation import validation_message
from apps.portal.views_common import StaffPortalMixin, access_scope_service

print_technique_service = PrintTechniqueService()
blank_catalog_service = BlankCatalogService()
warehouse_layout_service = WarehouseLayoutService()


class StaffPodPermissionMixin(StaffPortalMixin):
    required_permission = "pod.access_pod_atelier"
    rejection_action = "pod.atelier.permission_rejected"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and (
            not access_scope_service.can_access_staff_portal(request.user)
            or not request.user.has_perm(self.required_permission)
        ):
            record_event(
                action=self.rejection_action,
                actor=request.user,
                status=AuditLogEntry.Status.FAILURE,
                message="Accès atelier POD refusé.",
                metadata={"source": "staff_pod", "reason": "permission_denied"},
            )
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def _nav():
    return {"nav_mode": "staff", "nav_key": "staff-pod"}


def _render_error(request, template_name, context, exc: ValidationError):
    return render(
        request,
        template_name,
        {**context, "form_error": validation_message(exc), **_nav()},
        status=400,
    )


class StaffPodTechniqueListView(StaffPodPermissionMixin, View):
    template_name = "portal/staff/pod/techniques.html"

    def get(self, request):
        print_technique_service.ensure_dtf_technique(actor=request.user)
        return render(
            request,
            self.template_name,
            {
                **_nav(),
                "techniques": print_technique_service.list_techniques(actor=request.user),
                "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
                "form_error": "",
            },
        )

    def post(self, request):
        try:
            print_technique_service.create_technique(
                actor=request.user,
                source="staff_pod",
                data=request.POST,
            )
        except PermissionDenied:
            raise
        except ValidationError as exc:
            return _render_error(
                request,
                self.template_name,
                {
                    "techniques": print_technique_service.list_techniques(actor=request.user),
                    "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
                },
                exc,
            )
        return HttpResponseRedirect(reverse("portal:staff-pod-techniques"))


class StaffPodBlankListView(StaffPodPermissionMixin, View):
    template_name = "portal/staff/pod/blanks.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            {
                **_nav(),
                "blanks": blank_catalog_service.list_blanks(actor=request.user),
                "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
                "form_error": "",
            },
        )

    def post(self, request):
        try:
            blank_catalog_service.create_blank(
                actor=request.user, source="staff_pod", data=request.POST
            )
        except PermissionDenied:
            raise
        except ValidationError as exc:
            return _render_error(
                request,
                self.template_name,
                {
                    "blanks": blank_catalog_service.list_blanks(actor=request.user),
                    "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
                },
                exc,
            )
        return HttpResponseRedirect(reverse("portal:staff-pod-blanks"))


class StaffPodBlankDetailView(StaffPodPermissionMixin, View):
    template_name = "portal/staff/pod/blank_detail.html"

    def _context(self, request, blank):
        zones = warehouse_layout_service.list_zones(actor=request.user)
        locations = [location for zone in zones for location in zone.locations.all()]
        return {
            **_nav(),
            "blank": blank,
            "placements": BlankPlacementCapability.Placement.choices,
            "techniques": print_technique_service.list_techniques(actor=request.user),
            "locations": locations,
            "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
            "can_manage_warehouse": request.user.has_perm("inventory.manage_warehouse"),
            "form_error": "",
        }

    def get(self, request, blank_public_id):
        try:
            blank = blank_catalog_service.get_blank(
                actor=request.user, blank_public_id=blank_public_id
            )
        except ValidationError as exc:
            raise Http404(validation_message(exc)) from exc
        return render(request, self.template_name, self._context(request, blank))

    def post(self, request, blank_public_id):
        try:
            blank = blank_catalog_service.get_blank(
                actor=request.user, blank_public_id=blank_public_id
            )
            intent = request.POST.get("intent", "")
            if intent == "variant":
                blank_catalog_service.create_variant(
                    actor=request.user,
                    source="staff_pod",
                    blank_public_id=blank_public_id,
                    data=request.POST,
                )
            elif intent == "blank_photo":
                blank_catalog_service.set_blank_photo(
                    actor=request.user,
                    source="staff_pod",
                    blank_public_id=blank_public_id,
                    uploaded_file=request.FILES.get("photo"),
                )
            elif intent == "variant_photo":
                blank_catalog_service.set_variant_photo(
                    actor=request.user,
                    source="staff_pod",
                    blank_public_id=blank_public_id,
                    variant_public_id=request.POST.get("variant_public_id"),
                    uploaded_file=request.FILES.get("photo"),
                )
            elif intent == "clear_variant_photo":
                blank_catalog_service.clear_variant_photo(
                    actor=request.user,
                    source="staff_pod",
                    blank_public_id=blank_public_id,
                    variant_public_id=request.POST.get("variant_public_id"),
                )
            elif intent == "capability":
                blank_catalog_service.add_capability(
                    actor=request.user,
                    source="staff_pod",
                    blank_public_id=blank_public_id,
                    data={
                        **request.POST.dict(),
                        "is_required": request.POST.get("is_required") == "on",
                    },
                )
            elif intent == "default_location":
                warehouse_layout_service.set_blank_default_location(
                    actor=request.user,
                    source="staff_pod",
                    variant_public_id=request.POST.get("variant_public_id"),
                    location_public_id=request.POST.get("location_public_id"),
                )
            else:
                raise ValidationError("Action inconnue.")
        except PermissionDenied:
            raise
        except ValidationError as exc:
            try:
                blank = blank_catalog_service.get_blank(
                    actor=request.user, blank_public_id=blank_public_id
                )
            except ValidationError as missing:
                raise Http404(validation_message(missing)) from missing
            return _render_error(request, self.template_name, self._context(request, blank), exc)
        return HttpResponseRedirect(
            reverse("portal:staff-pod-blank-detail", kwargs={"blank_public_id": blank_public_id})
        )


class StaffPodBlankPhotoView(StaffPodPermissionMixin, View):
    """Sert les photos blank/variante via public_id (pas d’URL media brute)."""

    def get(self, request, blank_public_id, variant_public_id=None):
        try:
            blank = blank_catalog_service.get_blank(
                actor=request.user, blank_public_id=blank_public_id
            )
        except ValidationError as exc:
            raise Http404(validation_message(exc)) from exc
        size = (request.GET.get("size") or "thumb").strip().lower()
        use_thumb = size != "full"
        field = None
        if variant_public_id:
            variant = blank.variants.filter(public_id=variant_public_id).first()
            if variant is None:
                raise Http404("Variante introuvable.")
            if use_thumb and variant.photo_thumb:
                field = variant.photo_thumb
            elif variant.photo:
                field = variant.photo
            elif use_thumb and blank.photo_thumb:
                field = blank.photo_thumb
            elif blank.photo:
                field = blank.photo
        else:
            if use_thumb and blank.photo_thumb:
                field = blank.photo_thumb
            elif blank.photo:
                field = blank.photo
        if field is None or not field.name:
            raise Http404("Photo introuvable.")
        return FileResponse(field.open("rb"), content_type="image/webp")


class StaffPodWarehouseView(StaffPodPermissionMixin, View):
    template_name = "portal/staff/pod/warehouse.html"

    def get(self, request):
        zones = warehouse_layout_service.list_zones(actor=request.user)
        return render(
            request,
            self.template_name,
            {
                **_nav(),
                "zones": zones,
                "can_manage_warehouse": request.user.has_perm("inventory.manage_warehouse"),
                "form_error": "",
            },
        )

    def post(self, request):
        try:
            warehouse_layout_service.create_location(
                actor=request.user, source="staff_pod", data=request.POST
            )
        except PermissionDenied:
            raise
        except ValidationError as exc:
            return _render_error(
                request,
                self.template_name,
                {
                    "zones": warehouse_layout_service.list_zones(actor=request.user),
                    "can_manage_warehouse": request.user.has_perm("inventory.manage_warehouse"),
                },
                exc,
            )
        return HttpResponseRedirect(reverse("portal:staff-pod-warehouse"))


class StaffPodLocationDetailView(StaffPodPermissionMixin, View):
    template_name = "portal/staff/pod/location_detail.html"

    def get(self, request, location_public_id):
        try:
            location = warehouse_layout_service.get_location(
                actor=request.user, location_public_id=location_public_id
            )
        except ValidationError as exc:
            raise Http404(validation_message(exc)) from exc
        contents = warehouse_layout_service.location_contents(actor=request.user, location=location)
        return render(
            request,
            self.template_name,
            {**_nav(), "location": location, **contents},
        )
