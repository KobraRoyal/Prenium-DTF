from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import render
from django.views import View

from apps.pod.services import ShopifyCatalogService, VariantConfigService
from apps.pod.services.validation import validation_message
from apps.pod.services.variant_config_contract import VariantConfigPayload
from apps.portal.htmx import with_toast
from apps.portal.views_staff_pod import StaffPodPermissionMixin, _nav

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


class StaffPodCatalogListView(StaffPodPermissionMixin, View):
    template_name = "portal/staff/pod/catalogue.html"

    def get(self, request):
        products = shopify_catalog_service.list_products(actor=request.user)
        if not products.exists() and request.user.has_perm("pod.manage_pod_catalog"):
            shopify_catalog_service.ensure_demo_catalog(actor=request.user)
            products = shopify_catalog_service.list_products(actor=request.user)
        rows = []
        for product in products:
            variant_rows = []
            for variant in product.variants.all():
                config = variant_config_service.get_or_create_config(variant)
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
                "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
            },
        )


class StaffPodVariantConfigDrawerView(StaffPodPermissionMixin, View):
    template_name = "portal/staff/pod/_variant_config_drawer.html"

    def get(self, request, variant_public_id):
        try:
            variant = shopify_catalog_service.get_variant(
                actor=request.user, variant_public_id=variant_public_id
            )
            context = variant_config_service.drawer_context(actor=request.user, variant=variant)
        except ValidationError as exc:
            raise Http404(validation_message(exc)) from exc
        return render(
            request,
            self.template_name,
            {
                **context,
                "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
                "form_error": "",
            },
        )

    def post(self, request, variant_public_id):
        try:
            variant = shopify_catalog_service.get_variant(
                actor=request.user, variant_public_id=variant_public_id
            )
            intent = request.POST.get("intent", "save")
            if intent == "apply_template":
                variant_config_service.apply_template(
                    actor=request.user,
                    variant_public_id=variant_public_id,
                    template_public_id=request.POST.get("template_public_id"),
                    source="staff_pod_drawer",
                )
                message, variant_name = "Template appliqué.", "success"
            else:
                slots = []
                placements = request.POST.getlist("slot_placement")
                techniques = request.POST.getlist("slot_technique_public_id")
                references = request.POST.getlist("slot_print_reference")
                enabled_flags = set(request.POST.getlist("slot_enabled"))
                for index, placement in enumerate(placements):
                    technique_id = techniques[index] if index < len(techniques) else ""
                    reference = references[index] if index < len(references) else ""
                    key = f"{placement}:{technique_id}"
                    slots.append(
                        {
                            "placement": placement,
                            "technique_public_id": technique_id,
                            "print_reference": reference,
                            "is_enabled": key in enabled_flags or request.POST.get(
                                f"slot_required_{index}"
                            )
                            == "1",
                            "display_order": index,
                        }
                    )
                payload = VariantConfigPayload.from_mapping(
                    {
                        "mode": request.POST.get("mode"),
                        "blank_variant_public_id": request.POST.get("blank_variant_public_id"),
                        "finished_sku": request.POST.get("finished_sku"),
                        "staff_locked": request.POST.get("staff_locked") == "on",
                        "slots": slots,
                    }
                )
                variant_config_service.save_config(
                    actor=request.user,
                    variant_public_id=variant_public_id,
                    payload=payload,
                    source="staff_pod_drawer",
                )
                message, variant_name = "Configuration enregistrée.", "success"
            context = variant_config_service.drawer_context(actor=request.user, variant=variant)
            response = render(
                request,
                self.template_name,
                {
                    **context,
                    "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
                    "form_error": "",
                },
            )
            return with_toast(response, message, variant_name)
        except PermissionDenied:
            raise
        except ValidationError as exc:
            try:
                variant = shopify_catalog_service.get_variant(
                    actor=request.user, variant_public_id=variant_public_id
                )
                context = variant_config_service.drawer_context(actor=request.user, variant=variant)
            except ValidationError as missing:
                raise Http404(validation_message(missing)) from missing
            response = render(
                request,
                self.template_name,
                {
                    **context,
                    "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
                    "form_error": validation_message(exc),
                },
                status=400,
            )
            return with_toast(response, validation_message(exc), "error")


class StaffPodCatalogProductView(StaffPodPermissionMixin, View):
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
            config = variant_config_service.get_or_create_config(variant)
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
