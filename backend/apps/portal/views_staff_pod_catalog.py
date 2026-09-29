from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import render
from django.views import View

from apps.pod.models import IdsVariantConfig
from apps.pod.services import ShopifyCatalogService, VariantConfigService
from apps.pod.services.validation import validation_message
from apps.pod.services.variant_config_contract import VariantConfigPayload
from apps.portal.htmx import with_toast
from apps.portal.views_staff_pod import StaffPodCatalogManagerMixin, _nav

shopify_catalog_service = ShopifyCatalogService()
variant_config_service = VariantConfigService()


def _status_badge_tone(status: str) -> str:
    return {
        "pod": "is-success",
        "on_stock": "is-success",
        "virtual": "is-neutral",
        "disabled": "is-warning",
        "needs_config": "is-warning",
        "unmanaged": "is-neutral",
    }.get(status, "is-neutral")


class StaffPodCatalogListView(StaffPodCatalogManagerMixin, View):
    template_name = "portal/staff/pod/catalogue.html"

    def get(self, request):
        products = shopify_catalog_service.list_products(actor=request.user)
        search_query = request.GET.get("q", "").strip()[:160]
        if search_query:
            products = products.filter(
                Q(title__icontains=search_query)
                | Q(store__name__icontains=search_query)
                | Q(variants__sku__icontains=search_query)
                | Q(variants__title__icontains=search_query)
            ).distinct()
        page_obj = Paginator(products, 30).get_page(request.GET.get("page"))
        rows = []
        for product in page_obj:
            variant_rows = []
            for variant in product.variants.all():
                config = variant_config_service.get_config(variant)
                status = variant_config_service.configuration_status(config)
                variant_rows.append(
                    {
                        "variant": variant,
                        "status": status,
                        "badge_tone": _status_badge_tone(status),
                    }
                )
            rows.append({"product": product, "variants": variant_rows})
        return render(
            request,
            self.template_name,
            {
                **_nav(),
                "rows": rows,
                "page_obj": page_obj,
                "search_query": search_query,
                "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
            },
        )


class StaffPodVariantConfigDrawerView(StaffPodCatalogManagerMixin, View):
    template_name = "portal/staff/pod/_variant_config_drawer.html"

    @staticmethod
    def _payload_from_post(request) -> VariantConfigPayload:
        slots = []
        placements = request.POST.getlist("slot_placement")
        techniques = request.POST.getlist("slot_technique_public_id")
        references = request.POST.getlist("slot_print_reference")
        source_versions = request.POST.getlist("slot_source_asset_version_public_id")
        source_drive_file_ids = request.POST.getlist("slot_source_drive_file_id")
        enabled_flags = set(request.POST.getlist("slot_enabled"))
        for index, placement in enumerate(placements):
            technique_id = techniques[index] if index < len(techniques) else ""
            reference = references[index] if index < len(references) else ""
            source_version = source_versions[index] if index < len(source_versions) else ""
            source_drive_file_id = (
                source_drive_file_ids[index] if index < len(source_drive_file_ids) else ""
            )
            key = f"{placement}:{technique_id}"
            slots.append(
                {
                    "placement": placement,
                    "technique_public_id": technique_id,
                    "print_reference": reference,
                    "source_asset_version_public_id": source_version,
                    "source_drive_file_id": source_drive_file_id,
                    "is_enabled": key in enabled_flags
                    or request.POST.get(f"slot_required_{index}") == "1",
                    "display_order": index,
                }
            )
        return VariantConfigPayload.from_mapping(
            {
                "mode": request.POST.get("mode"),
                "blank_variant_public_id": request.POST.get("blank_variant_public_id"),
                "finished_sku": request.POST.get("finished_sku", ""),
                "staff_locked": request.POST.get("staff_locked") == "on",
                "slots": slots,
            }
        )

    def _draft_context(
        self, *, request, variant, payload, strict_blank=True, refresh_drive=False
    ):
        if payload.mode not in IdsVariantConfig.Mode.values:
            raise ValidationError("Mode variante invalide.")
        preview_blank_public_id = payload.blank_variant_public_id
        try:
            context = variant_config_service.drawer_context(
                actor=request.user,
                variant=variant,
                preview_blank_public_id=preview_blank_public_id or "",
                refresh_drive=refresh_drive,
            )
        except ValidationError:
            if strict_blank:
                raise
            context = variant_config_service.drawer_context(
                actor=request.user, variant=variant, refresh_drive=refresh_drive
            )
            preview_blank_public_id = ""

        config = context["config"]
        config.mode = payload.mode
        config.finished_sku = payload.finished_sku
        config.staff_locked = payload.staff_locked
        if payload.mode != IdsVariantConfig.Mode.POD or not preview_blank_public_id:
            if not preview_blank_public_id:
                config.blank_variant = None
            context["slot_rows"] = []
            context["templates"] = context["templates"].none()
        else:
            draft_slots = {
                (slot.placement, slot.technique_public_id): slot for slot in payload.slots
            }
            for row in context["slot_rows"]:
                key = (row["placement"], str(row["technique"].public_id))
                slot = draft_slots.get(key)
                if slot is None:
                    row["is_enabled"] = row["is_required"]
                    continue
                row["is_enabled"] = row["is_required"] or slot.is_enabled
                row["print_reference"] = slot.print_reference
                allowed_versions = {str(version.public_id) for version in row["asset_options"]}
                row["source_asset_version_public_id"] = (
                    slot.source_asset_version_public_id
                    if slot.source_asset_version_public_id in allowed_versions
                    else ""
                )
                allowed_drive_file_ids = {
                    str(option.file_id) for option in row.get("drive_options", ())
                }
                row["source_drive_file_id"] = (
                    slot.source_drive_file_id
                    if slot.source_drive_file_id in allowed_drive_file_ids
                    else ""
                )
        context["status"] = variant_config_service.configuration_status(config)
        context["draft_slots"] = payload.slots
        return context

    def _render_drawer(self, request, context, *, form_error="", status=200):
        context = variant_config_service.mapping_choices(
            context,
            placement=request.POST.get("mapping_placement", ""),
            technique_id=request.POST.get("mapping_technique", ""),
        )
        return render(
            request,
            self.template_name,
            {
                **context,
                "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
                "form_error": form_error,
            },
            status=status,
        )

    def get(self, request, variant_public_id):
        try:
            variant = shopify_catalog_service.get_variant(
                actor=request.user, variant_public_id=variant_public_id
            )
            context = variant_config_service.drawer_context(
                actor=request.user,
                variant=variant,
                preview_blank_public_id=request.GET.get("blank_variant_public_id", ""),
            )
        except ValidationError as exc:
            raise Http404(validation_message(exc)) from exc
        return self._render_drawer(request, context)

    def post(self, request, variant_public_id):
        try:
            variant = shopify_catalog_service.get_variant(
                actor=request.user, variant_public_id=variant_public_id
            )
            intent = request.POST.get("intent", "save")
            payload = None
            if intent in ("preview", "add_slot", "remove_slot", "refresh_drive"):
                payload = self._payload_from_post(request)
                context = self._draft_context(
                    request=request,
                    variant=variant,
                    payload=payload,
                    refresh_drive=intent == "refresh_drive",
                )
                if intent != "preview":
                    variant_config_service.mapping_choices(
                        context,
                        placement=request.POST.get("mapping_placement", ""),
                        technique_id=request.POST.get("mapping_technique", ""),
                        action=intent,
                        slot_key=request.POST.get("slot_key", ""),
                    )
                return self._render_drawer(request, context)
            if intent == "apply_template":
                variant_config_service.apply_template(
                    actor=request.user,
                    variant_public_id=variant_public_id,
                    template_public_id=request.POST.get("template_public_id"),
                    source="staff_pod_drawer",
                )
                message, variant_name = "Template appliqué.", "success"
            elif intent == "save":
                payload = self._payload_from_post(request)
                variant_config_service.save_config(
                    actor=request.user,
                    variant_public_id=variant_public_id,
                    payload=payload,
                    source="staff_pod_drawer",
                )
                message, variant_name = "Configuration enregistrée.", "success"
            else:
                raise ValidationError("Action de configuration inconnue.")
            context = variant_config_service.drawer_context(actor=request.user, variant=variant)
            response = self._render_drawer(request, context)
            response["HX-Trigger"] = "pod-config-saved"
            return with_toast(response, message, variant_name)
        except PermissionDenied:
            raise
        except ValidationError as exc:
            try:
                variant = shopify_catalog_service.get_variant(
                    actor=request.user, variant_public_id=variant_public_id
                )
                if (
                    "payload" in locals()
                    and payload is not None
                    and payload.mode in IdsVariantConfig.Mode.values
                ):
                    context = self._draft_context(
                        request=request,
                        variant=variant,
                        payload=payload,
                        strict_blank=False,
                    )
                else:
                    context = variant_config_service.drawer_context(
                        actor=request.user, variant=variant
                    )
            except ValidationError as missing:
                raise Http404(validation_message(missing)) from missing
            response = self._render_drawer(
                request,
                context,
                form_error=validation_message(exc),
                status=400,
            )
            return with_toast(response, validation_message(exc), "error")


class StaffPodCatalogProductView(StaffPodCatalogManagerMixin, View):
    template_name = "portal/staff/pod/catalogue_product.html"

    def get(self, request, product_public_id):
        try:
            product = shopify_catalog_service.get_product(
                actor=request.user, product_public_id=product_public_id
            )
        except ValidationError as exc:
            raise Http404(validation_message(exc)) from exc
        variant_rows = []
        for variant in product.variants.all():
            config = variant_config_service.get_config(variant)
            status = variant_config_service.configuration_status(config)
            variant_rows.append(
                {
                    "variant": variant,
                    "status": status,
                    "badge_tone": _status_badge_tone(status),
                }
            )
        return render(
            request,
            self.template_name,
            {
                **_nav(),
                "product": product,
                "variant_rows": variant_rows,
                "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
            },
        )
