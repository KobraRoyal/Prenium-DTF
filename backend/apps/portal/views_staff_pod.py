from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.inventory.services import WarehouseLayoutService
from apps.pod.services import BlankCatalogService, PrintTechniqueService
from apps.pod.services.blank_marking_options import BlankMarkingOptionsService
from apps.pod.services.validation import validation_message
from apps.portal.views_common import StaffPortalMixin, access_scope_service

print_technique_service = PrintTechniqueService()
blank_catalog_service = BlankCatalogService()
blank_marking_options_service = BlankMarkingOptionsService()
warehouse_layout_service = WarehouseLayoutService()


class StaffPodPermissionMixin(StaffPortalMixin):
    required_permissions = ("pod.access_pod_atelier",)
    any_required_permissions: tuple[str, ...] = ()
    rejection_action = "pod.atelier.permission_rejected"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and (
            not access_scope_service.can_access_staff_portal(request.user)
            or any(
                not request.user.has_perm(permission) for permission in self.required_permissions
            )
            or (
                self.any_required_permissions
                and not any(
                    request.user.has_perm(permission)
                    for permission in self.any_required_permissions
                )
            )
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


class StaffPodCatalogManagerMixin(StaffPodPermissionMixin):
    required_permissions = (
        *StaffPodPermissionMixin.required_permissions,
        "pod.manage_pod_catalog",
    )


class StaffPodWarehouseManagerMixin(StaffPodPermissionMixin):
    required_permissions = (
        *StaffPodPermissionMixin.required_permissions,
        "inventory.manage_warehouse",
    )


class StaffPodSettingsManagerMixin(StaffPodPermissionMixin):
    any_required_permissions = (
        "pod.manage_pod_catalog",
        "inventory.manage_warehouse",
    )


def _nav():
    return {"nav_mode": "staff", "nav_key": "staff-pod"}


def _render_error(request, template_name, context, exc: ValidationError):
    forbidden_fragments = ("password", "secret", "token", "credential")
    form_data = {
        key: value
        for key, value in request.POST.items()
        if not any(fragment in key.lower() for fragment in forbidden_fragments)
    }
    return render(
        request,
        template_name,
        {
            **context,
            "form_error": validation_message(exc),
            "form_data": form_data,
            "submitted_intent": request.POST.get("intent", ""),
            **_nav(),
        },
        status=400,
    )


def _techniques_context(request):
    query = (request.GET.get("q") or "").strip()
    techniques = print_technique_service.list_techniques(actor=request.user)
    if query:
        techniques = techniques.filter(Q(code__icontains=query) | Q(name__icontains=query))
    page_obj = Paginator(techniques, 30).get_page(request.GET.get("page"))
    return {
        **_nav(),
        "techniques": page_obj,
        "page_obj": page_obj,
        "search_query": query,
        "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
        "form_error": "",
    }


def _blanks_context(request):
    query = (request.GET.get("q") or "").strip()
    blanks = blank_catalog_service.list_blanks(actor=request.user)
    if query:
        blanks = blanks.filter(
            Q(sku__icontains=query) | Q(name__icontains=query) | Q(brand__icontains=query)
        )
    page_obj = Paginator(blanks, 30).get_page(request.GET.get("page"))
    return {
        **_nav(),
        "blanks": page_obj,
        "page_obj": page_obj,
        "search_query": query,
        "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
        "form_error": "",
    }


class StaffPodTechniqueListView(StaffPodCatalogManagerMixin, View):
    template_name = "portal/staff/pod/techniques.html"

    def get(self, request):
        return render(request, self.template_name, _techniques_context(request))

    def post(self, request):
        try:
            intent = request.POST.get("intent") or "create"
            if intent == "create":
                print_technique_service.create_technique(
                    actor=request.user,
                    source="staff_pod",
                    data=request.POST,
                )
                success_message = "Technique créée."
            elif intent == "update":
                print_technique_service.update_technique(
                    actor=request.user,
                    source="staff_pod",
                    technique_public_id=request.POST.get("technique_public_id"),
                    data={
                        "name": request.POST.get("name", ""),
                        "is_active": request.POST.get("is_active") == "on",
                    },
                )
                success_message = "Technique enregistrée."
            else:
                raise ValidationError("Action inconnue.")
        except PermissionDenied:
            raise
        except ValidationError as exc:
            return _render_error(
                request,
                self.template_name,
                _techniques_context(request),
                exc,
            )
        messages.success(request, success_message)
        return HttpResponseRedirect(reverse("portal:staff-pod-techniques"))


class StaffPodBlankListView(StaffPodCatalogManagerMixin, View):
    template_name = "portal/staff/pod/blanks.html"

    def get(self, request):
        return render(request, self.template_name, _blanks_context(request))

    def post(self, request):
        try:
            if (request.POST.get("intent") or "create") != "create":
                raise ValidationError("Action inconnue.")
            blank_catalog_service.create_blank(
                actor=request.user, source="staff_pod", data=request.POST
            )
        except PermissionDenied:
            raise
        except ValidationError as exc:
            return _render_error(
                request,
                self.template_name,
                _blanks_context(request),
                exc,
            )
        messages.success(request, "Support vierge créé.")
        return HttpResponseRedirect(reverse("portal:staff-pod-blanks"))


class StaffPodBlankDetailView(StaffPodCatalogManagerMixin, View):
    template_name = "portal/staff/pod/blank_detail.html"

    def _context(self, request, blank):
        can_manage_warehouse = request.user.has_perm("inventory.manage_warehouse")
        locations = []
        if can_manage_warehouse:
            zones = warehouse_layout_service.list_zones(actor=request.user)
            locations = [
                location
                for zone in zones
                if zone.is_active and zone.warehouse.is_active
                for location in zone.locations.all()
                if location.is_active
            ]
        marking_context = blank_marking_options_service.selection_context(blank)
        if request.method == "POST" and request.POST.get("intent") == "marking_options":
            marking_context.update(
                selected_marking_zones=request.POST.getlist("zone_public_ids"),
                selected_marking_techniques=request.POST.getlist("technique_public_ids"),
            )
        return {
            **_nav(),
            "blank": blank,
            **marking_context,
            "locations": locations,
            "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
            "can_manage_warehouse": can_manage_warehouse,
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
            if intent == "update_blank":
                blank_catalog_service.update_blank(
                    actor=request.user,
                    source="staff_pod",
                    blank_public_id=blank_public_id,
                    data={
                        "name": request.POST.get("name", ""),
                        "brand": request.POST.get("brand", ""),
                        "is_active": request.POST.get("is_active") == "on",
                    },
                )
                success_message = "Support vierge enregistré."
            elif intent == "variant":
                blank_catalog_service.create_variant(
                    actor=request.user,
                    source="staff_pod",
                    blank_public_id=blank_public_id,
                    data=request.POST,
                )
                success_message = "Variante créée."
            elif intent == "update_variant":
                blank_catalog_service.update_variant(
                    actor=request.user,
                    source="staff_pod",
                    blank_public_id=blank_public_id,
                    variant_public_id=request.POST.get("variant_public_id"),
                    data={
                        "size_label": request.POST.get("size_label", ""),
                        "color_name": request.POST.get("color_name", ""),
                        "color_hex": request.POST.get("color_hex", ""),
                        "is_active": request.POST.get("is_active") == "on",
                    },
                )
                success_message = "Variante enregistrée."
            elif intent == "blank_photo":
                blank_catalog_service.set_blank_photo(
                    actor=request.user,
                    source="staff_pod",
                    blank_public_id=blank_public_id,
                    uploaded_file=request.FILES.get("photo"),
                )
                success_message = "Photo du support enregistrée."
            elif intent == "variant_photo":
                blank_catalog_service.set_variant_photo(
                    actor=request.user,
                    source="staff_pod",
                    blank_public_id=blank_public_id,
                    variant_public_id=request.POST.get("variant_public_id"),
                    uploaded_file=request.FILES.get("photo"),
                )
                success_message = "Photo de la variante enregistrée."
            elif intent == "clear_variant_photo":
                blank_catalog_service.clear_variant_photo(
                    actor=request.user,
                    source="staff_pod",
                    blank_public_id=blank_public_id,
                    variant_public_id=request.POST.get("variant_public_id"),
                )
                success_message = "Photo de la variante retirée."
            elif intent == "marking_options":
                blank_marking_options_service.save(
                    actor=request.user,
                    source="staff_pod",
                    blank_public_id=blank_public_id,
                    zone_public_ids=request.POST.getlist("zone_public_ids"),
                    technique_public_ids=request.POST.getlist("technique_public_ids"),
                )
                success_message = "Zones et techniques possibles enregistrées."
            elif intent == "default_location":
                warehouse_layout_service.set_blank_default_location(
                    actor=request.user,
                    source="staff_pod",
                    blank_public_id=blank_public_id,
                    variant_public_id=request.POST.get("variant_public_id"),
                    location_public_id=request.POST.get("location_public_id"),
                )
                success_message = "Emplacement par défaut enregistré."
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
        messages.success(request, success_message)
        return HttpResponseRedirect(
            reverse("portal:staff-pod-blank-detail", kwargs={"blank_public_id": blank_public_id})
        )


class StaffPodWarehouseView(StaffPodWarehouseManagerMixin, View):
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
            if (request.POST.get("intent") or "create") != "create":
                raise ValidationError("Action inconnue.")
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
        messages.success(request, "Emplacement créé.")
        return HttpResponseRedirect(reverse("portal:staff-pod-warehouse"))


class StaffPodLocationDetailView(StaffPodWarehouseManagerMixin, View):
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

    def post(self, request, location_public_id):
        try:
            if request.POST.get("intent") != "update":
                raise ValidationError("Action inconnue.")
            warehouse_layout_service.update_location(
                actor=request.user,
                source="staff_pod",
                location_public_id=location_public_id,
                data={
                    "label": request.POST.get("label", ""),
                    "is_active": request.POST.get("is_active") == "on",
                },
            )
        except PermissionDenied:
            raise
        except ValidationError as exc:
            try:
                location = warehouse_layout_service.get_location(
                    actor=request.user, location_public_id=location_public_id
                )
            except ValidationError as missing:
                raise Http404(validation_message(missing)) from missing
            contents = warehouse_layout_service.location_contents(
                actor=request.user, location=location
            )
            return _render_error(
                request,
                self.template_name,
                {"location": location, **contents},
                exc,
            )
        messages.success(request, "Emplacement enregistré.")
        return HttpResponseRedirect(
            reverse(
                "portal:staff-pod-location-detail",
                kwargs={"location_public_id": location_public_id},
            )
        )
