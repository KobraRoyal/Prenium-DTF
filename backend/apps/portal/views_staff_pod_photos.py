from __future__ import annotations

from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404
from django.views import View

from apps.pod.services.validation import validation_message
from apps.portal.views_staff_pod import StaffPodCatalogManagerMixin, blank_catalog_service


class StaffPodBlankPhotoView(StaffPodCatalogManagerMixin, View):
    """Serve blank/variant photos by public ID, never a raw media URL."""

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
