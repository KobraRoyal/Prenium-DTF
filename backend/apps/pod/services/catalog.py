from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.auditlog.services import record_event
from apps.inventory.models import StockBalance
from apps.pod.models import (
    Blank,
    BlankPlacementCapability,
    BlankVariant,
    PodRipWorkItem,
    PrintTechnique,
)
from apps.pod.services.catalog_images import process_catalog_photo
from apps.pod.services.validation import (
    clean_hex_color,
    clean_sku,
    require_staff_perm,
    validation_message,
)

DTF_TECHNIQUE_CODE = "dtf"
RIP_DIRECTORY_PATTERN = re.compile(r"02_[a-z0-9_-]+\Z")


def validate_rip_directory(value: str) -> str:
    if not RIP_DIRECTORY_PATTERN.fullmatch(value or ""):
        raise ValidationError("Le répertoire RIP doit être un nom plat de type 02_nom.")
    return value


def _is_checked(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "on", "yes"}


def _locked_count(queryset) -> int:
    return len(list(queryset.select_for_update().values_list("pk", flat=True)))


def _queued_for_technique(technique: PrintTechnique) -> int:
    return _locked_count(
        PodRipWorkItem.objects.filter(
            status=PodRipWorkItem.Status.QUEUED,
            variant__ids_config__recipe__slots__technique=technique,
            variant__ids_config__recipe__slots__is_enabled=True,
        ).distinct()
    )


def _queued_for_blank(blank: Blank) -> int:
    return _locked_count(
        PodRipWorkItem.objects.filter(
            status=PodRipWorkItem.Status.QUEUED,
            variant__ids_config__blank_variant__blank=blank,
        ).distinct()
    )


def _queued_for_variant(variant: BlankVariant) -> int:
    return _locked_count(
        PodRipWorkItem.objects.filter(
            status=PodRipWorkItem.Status.QUEUED,
            variant__ids_config__blank_variant=variant,
        ).distinct()
    )


def _queued_for_capability(capability: BlankPlacementCapability) -> int:
    return _locked_count(
        PodRipWorkItem.objects.filter(
            status=PodRipWorkItem.Status.QUEUED,
            variant__ids_config__blank_variant__blank=capability.blank,
            variant__ids_config__recipe__slots__placement=capability.placement,
            variant__ids_config__recipe__slots__technique=capability.technique,
            variant__ids_config__recipe__slots__is_enabled=True,
        ).distinct()
    )


def _reserved_for_blank(blank: Blank) -> int:
    balances = StockBalance.objects.select_for_update().filter(
        blank_variant__blank=blank,
        qty_reserved__gt=0,
    )
    return sum(balance.qty_reserved for balance in balances)


def _reserved_for_variant(variant: BlankVariant) -> int:
    balances = StockBalance.objects.select_for_update().filter(
        blank_variant=variant,
        qty_reserved__gt=0,
    )
    return sum(balance.qty_reserved for balance in balances)


class PrintTechniqueService:
    view_permission = "pod.access_pod_atelier"
    manage_permission = "pod.manage_pod_catalog"

    def list_techniques(self, *, actor):
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.techniques",
            action="pod.technique.permission_rejected",
        )
        return PrintTechnique.objects.all()

    def ensure_dtf_technique(self, *, actor) -> PrintTechnique:
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.techniques",
            action="pod.technique.permission_rejected",
        )
        technique, _created = PrintTechnique.objects.get_or_create(
            code=DTF_TECHNIQUE_CODE,
            defaults={
                "name": "DTF",
                "rip_directory": "02_rip",
                "export_extension": ".png",
                "display_order": 10,
                "is_active": True,
            },
        )
        PrintTechnique.objects.get_or_create(
            code="embroidery",
            defaults={
                "name": "Broderie",
                "rip_directory": "02_embroidery",
                "export_extension": ".png",
                "display_order": 20,
                "is_active": True,
            },
        )
        return technique

    def create_technique(self, *, actor, source: str, data: dict) -> PrintTechnique:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.technique.permission_rejected",
        )
        try:
            code = (data.get("code") or "").strip().lower()
            name = (data.get("name") or "").strip()
            rip_directory = (data.get("rip_directory") or "02_rip").strip()
            export_extension = (data.get("export_extension") or ".png").strip().lower()
            if not code or not name:
                raise ValidationError("Code et nom sont obligatoires.")
            validate_rip_directory(rip_directory)
            if not export_extension.startswith("."):
                export_extension = f".{export_extension}"
            if export_extension != ".png":
                raise ValidationError(
                    "Seul l'export PNG analysé est disponible en production automatique."
                )
            with transaction.atomic():
                technique = PrintTechnique(
                    code=code,
                    name=name,
                    rip_directory=rip_directory,
                    export_extension=export_extension,
                    is_active=True,
                )
                technique.full_clean()
                technique.save()
                record_event(
                    action="pod.technique.created",
                    actor=actor,
                    target=technique,
                    metadata={"source": source, "code": technique.code},
                )
                return technique
        except IntegrityError as exc:
            error = ValidationError("Ce code technique existe déjà.")
            record_event(
                action="pod.technique.create_rejected",
                actor=actor,
                status="failure",
                message=validation_message(error),
                metadata={"source": source},
            )
            raise error from exc
        except ValidationError as exc:
            record_event(
                action="pod.technique.create_rejected",
                actor=actor,
                status="failure",
                message=validation_message(exc),
                metadata={"source": source},
            )
            raise

    def update_technique(
        self, *, actor, source: str, technique_public_id, data: dict
    ) -> PrintTechnique:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.technique.permission_rejected",
        )
        try:
            with transaction.atomic():
                technique = (
                    PrintTechnique.objects.select_for_update()
                    .filter(public_id=technique_public_id)
                    .first()
                )
                if technique is None:
                    raise ValidationError("Technique introuvable.")
                requested_active = _is_checked(data.get("is_active"))
                name = (data.get("name") or "").strip()
                if technique.name != name or technique.is_active != requested_active:
                    queued_count = _queued_for_technique(technique)
                    if queued_count:
                        raise ValidationError(
                            "Modification impossible : "
                            f"{queued_count} commande(s) POD en cours utilisent cette technique."
                        )
                previous = {"name": technique.name, "is_active": technique.is_active}
                technique.name = name
                technique.is_active = requested_active
                technique.full_clean()
                technique.save(update_fields=["name", "is_active", "updated_at"])
                record_event(
                    action="pod.technique.updated",
                    actor=actor,
                    target=technique,
                    metadata={
                        "source": source,
                        "previous": previous,
                        "changes": {
                            "name": technique.name,
                            "is_active": technique.is_active,
                        },
                    },
                )
                return technique
        except ValidationError as exc:
            record_event(
                action="pod.technique.update_rejected",
                actor=actor,
                status="failure",
                message=validation_message(exc),
                metadata={"source": source},
            )
            raise


class BlankCatalogService:
    view_permission = "pod.access_pod_atelier"
    manage_permission = "pod.manage_pod_catalog"

    def list_blanks(self, *, actor):
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.blanks",
            action="pod.blank.permission_rejected",
        )
        return Blank.objects.prefetch_related(
            "variants__location_rules__location",
            "placement_capabilities__technique",
            "allowed_zones",
            "allowed_techniques",
        )

    def get_blank(self, *, actor, blank_public_id):
        blank = self.list_blanks(actor=actor).filter(public_id=blank_public_id).first()
        if blank is None:
            raise ValidationError("Support vierge introuvable.")
        return blank

    def create_blank(self, *, actor, source: str, data: dict) -> Blank:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.blank.permission_rejected",
        )
        try:
            sku = clean_sku(data.get("sku", ""))
            name = (data.get("name") or "").strip()
            brand = (data.get("brand") or "").strip()
            if not name:
                raise ValidationError("Le nom du support est obligatoire.")
            with transaction.atomic():
                blank = Blank(sku=sku, name=name, brand=brand)
                blank.full_clean()
                blank.save()
                record_event(
                    action="pod.blank.created",
                    actor=actor,
                    target=blank,
                    metadata={"source": source, "sku": blank.sku},
                )
                return blank
        except IntegrityError as exc:
            error = ValidationError("Ce SKU support existe déjà.")
            record_event(
                action="pod.blank.create_rejected",
                actor=actor,
                status="failure",
                message=validation_message(error),
                metadata={"source": source},
            )
            raise error from exc
        except ValidationError as exc:
            record_event(
                action="pod.blank.create_rejected",
                actor=actor,
                status="failure",
                message=validation_message(exc),
                metadata={"source": source},
            )
            raise

    def update_blank(self, *, actor, source: str, blank_public_id, data: dict) -> Blank:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.blank.permission_rejected",
        )
        try:
            with transaction.atomic():
                blank = Blank.objects.select_for_update().filter(public_id=blank_public_id).first()
                if blank is None:
                    raise ValidationError("Support vierge introuvable.")
                requested_active = _is_checked(data.get("is_active"))
                name = (data.get("name") or "").strip()
                brand = (data.get("brand") or "").strip()
                if (
                    blank.name != name
                    or blank.brand != brand
                    or blank.is_active != requested_active
                ):
                    queued_count = _queued_for_blank(blank)
                    if queued_count:
                        raise ValidationError(
                            "Modification impossible : "
                            f"{queued_count} commande(s) POD en cours utilisent ce support."
                        )
                if blank.is_active and not requested_active:
                    reserved_qty = _reserved_for_blank(blank)
                    if reserved_qty:
                        raise ValidationError(
                            "Désactivation impossible : "
                            f"{reserved_qty} unité(s) réservée(s) utilisent ce support."
                        )
                previous = {
                    "name": blank.name,
                    "brand": blank.brand,
                    "is_active": blank.is_active,
                }
                blank.name = name
                blank.brand = brand
                blank.is_active = requested_active
                blank.full_clean()
                blank.save(update_fields=["name", "brand", "is_active", "updated_at"])
                record_event(
                    action="pod.blank.updated",
                    actor=actor,
                    target=blank,
                    metadata={
                        "source": source,
                        "previous": previous,
                        "changes": {
                            "name": blank.name,
                            "brand": blank.brand,
                            "is_active": blank.is_active,
                        },
                    },
                )
                return blank
        except ValidationError as exc:
            record_event(
                action="pod.blank.update_rejected",
                actor=actor,
                status="failure",
                message=validation_message(exc),
                metadata={"source": source},
            )
            raise

    def create_variant(self, *, actor, source: str, blank_public_id, data: dict) -> BlankVariant:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.blank.permission_rejected",
        )
        try:
            with transaction.atomic():
                blank = Blank.objects.select_for_update().filter(public_id=blank_public_id).first()
                if blank is None:
                    raise ValidationError("Support vierge introuvable.")
                if not blank.is_active:
                    raise ValidationError("Le support vierge est inactif.")
                variant = BlankVariant(
                    blank=blank,
                    sku=clean_sku(data.get("sku", ""), field_label="SKU variante"),
                    size_label=(data.get("size_label") or "").strip() or "U",
                    color_name=(data.get("color_name") or "").strip() or "Standard",
                    color_hex=clean_hex_color(data.get("color_hex", "")),
                )
                variant.full_clean()
                variant.save()
                record_event(
                    action="pod.blank_variant.created",
                    actor=actor,
                    target=variant,
                    metadata={"source": source, "blank": str(blank.public_id)},
                )
                return variant
        except IntegrityError as exc:
            error = ValidationError("Ce SKU variante existe déjà.")
            record_event(
                action="pod.blank_variant.create_rejected",
                actor=actor,
                status="failure",
                message=validation_message(error),
                metadata={"source": source},
            )
            raise error from exc
        except ValidationError as exc:
            record_event(
                action="pod.blank_variant.create_rejected",
                actor=actor,
                status="failure",
                message=validation_message(exc),
                metadata={"source": source},
            )
            raise

    def update_variant(
        self,
        *,
        actor,
        source: str,
        blank_public_id,
        variant_public_id,
        data: dict,
    ) -> BlankVariant:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.blank.permission_rejected",
        )
        try:
            with transaction.atomic():
                blank = Blank.objects.select_for_update().filter(public_id=blank_public_id).first()
                if blank is None:
                    raise ValidationError("Support vierge introuvable.")
                variant = (
                    BlankVariant.objects.select_for_update()
                    .filter(public_id=variant_public_id, blank=blank)
                    .first()
                )
                if variant is None:
                    raise ValidationError("Variante support introuvable.")
                requested_active = _is_checked(data.get("is_active"))
                size_label = (data.get("size_label") or "").strip() or "U"
                color_name = (data.get("color_name") or "").strip() or "Standard"
                color_hex = clean_hex_color(data.get("color_hex", ""))
                if (
                    variant.size_label != size_label
                    or variant.color_name != color_name
                    or variant.color_hex != color_hex
                    or variant.is_active != requested_active
                ):
                    queued_count = _queued_for_variant(variant)
                    if queued_count:
                        raise ValidationError(
                            "Modification impossible : "
                            f"{queued_count} commande(s) POD en cours utilisent cette variante."
                        )
                if variant.is_active and not requested_active:
                    reserved_qty = _reserved_for_variant(variant)
                    if reserved_qty:
                        raise ValidationError(
                            "Désactivation impossible : "
                            f"{reserved_qty} unité(s) réservée(s) utilisent cette variante."
                        )
                previous = {
                    "size_label": variant.size_label,
                    "color_name": variant.color_name,
                    "color_hex": variant.color_hex,
                    "is_active": variant.is_active,
                }
                variant.size_label = size_label
                variant.color_name = color_name
                variant.color_hex = color_hex
                if requested_active and not blank.is_active:
                    raise ValidationError(
                        "Réactivation impossible : le support vierge est inactif."
                    )
                variant.is_active = requested_active
                variant.full_clean()
                variant.save(
                    update_fields=[
                        "size_label",
                        "color_name",
                        "color_hex",
                        "is_active",
                        "updated_at",
                    ]
                )
                record_event(
                    action="pod.blank_variant.updated",
                    actor=actor,
                    target=variant,
                    metadata={
                        "source": source,
                        "blank": str(blank.public_id),
                        "previous": previous,
                        "changes": {
                            "size_label": variant.size_label,
                            "color_name": variant.color_name,
                            "color_hex": variant.color_hex,
                            "is_active": variant.is_active,
                        },
                    },
                )
                return variant
        except ValidationError as exc:
            record_event(
                action="pod.blank_variant.update_rejected",
                actor=actor,
                status="failure",
                message=validation_message(exc),
                metadata={"source": source, "blank": str(blank_public_id)},
            )
            raise

    def set_blank_photo(self, *, actor, source: str, blank_public_id, uploaded_file) -> Blank:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.blank.permission_rejected",
        )
        blank = self.get_blank(actor=actor, blank_public_id=blank_public_id)
        photo, thumb = process_catalog_photo(uploaded_file)
        if blank.photo:
            blank.photo.delete(save=False)
        if blank.photo_thumb:
            blank.photo_thumb.delete(save=False)
        blank.photo.save("photo.webp", photo, save=False)
        blank.photo_thumb.save("thumb.webp", thumb, save=False)
        blank.save(update_fields=["photo", "photo_thumb", "updated_at"])
        record_event(
            action="pod.blank.photo_updated",
            actor=actor,
            target=blank,
            metadata={"source": source},
        )
        return blank

    def set_variant_photo(
        self,
        *,
        actor,
        source: str,
        blank_public_id,
        variant_public_id,
        uploaded_file,
    ) -> BlankVariant:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.blank.permission_rejected",
        )
        blank = self.get_blank(actor=actor, blank_public_id=blank_public_id)
        variant = blank.variants.filter(public_id=variant_public_id).first()
        if variant is None:
            raise ValidationError("Variante support introuvable.")
        photo, thumb = process_catalog_photo(uploaded_file)
        if variant.photo:
            variant.photo.delete(save=False)
        if variant.photo_thumb:
            variant.photo_thumb.delete(save=False)
        variant.photo.save("photo.webp", photo, save=False)
        variant.photo_thumb.save("thumb.webp", thumb, save=False)
        variant.save(update_fields=["photo", "photo_thumb", "updated_at"])
        record_event(
            action="pod.blank_variant.photo_updated",
            actor=actor,
            target=variant,
            metadata={"source": source, "blank": str(blank.public_id)},
        )
        return variant

    def clear_variant_photo(
        self, *, actor, source: str, blank_public_id, variant_public_id
    ) -> BlankVariant:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.blank.permission_rejected",
        )
        blank = self.get_blank(actor=actor, blank_public_id=blank_public_id)
        variant = blank.variants.filter(public_id=variant_public_id).first()
        if variant is None:
            raise ValidationError("Variante support introuvable.")
        if variant.photo:
            variant.photo.delete(save=False)
        if variant.photo_thumb:
            variant.photo_thumb.delete(save=False)
        variant.photo = ""
        variant.photo_thumb = ""
        variant.save(update_fields=["photo", "photo_thumb", "updated_at"])
        record_event(
            action="pod.blank_variant.photo_cleared",
            actor=actor,
            target=variant,
            metadata={"source": source},
        )
        return variant

    def add_capability(self, *, actor, source: str, blank_public_id, data: dict):
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.blank.permission_rejected",
        )
        try:
            placement = (data.get("placement") or "").strip()
            if placement not in BlankPlacementCapability.Placement.values:
                raise ValidationError("Zone de pose invalide.")
            with transaction.atomic():
                blank = Blank.objects.select_for_update().filter(public_id=blank_public_id).first()
                if blank is None:
                    raise ValidationError("Support vierge introuvable.")
                if blank.marking_options_configured:
                    raise ValidationError(
                        "Configurez les zones et techniques dans les listes du support."
                    )
                if not blank.is_active:
                    raise ValidationError("Le support vierge est inactif.")
                technique = (
                    PrintTechnique.objects.select_for_update()
                    .filter(
                        public_id=data.get("technique_public_id"),
                        is_active=True,
                    )
                    .first()
                )
                if technique is None:
                    raise ValidationError("Technique introuvable.")
                capability, created = BlankPlacementCapability.objects.update_or_create(
                    blank=blank,
                    placement=placement,
                    technique=technique,
                    defaults={
                        "is_required": _is_checked(data.get("is_required")),
                        "is_active": True,
                    },
                )
                capability.full_clean()
                record_event(
                    action="pod.blank_capability.saved",
                    actor=actor,
                    target=capability,
                    metadata={"source": source, "created": created},
                )
                return capability
        except IntegrityError as exc:
            error = ValidationError("Cette pose / technique existe déjà.")
            record_event(
                action="pod.blank_capability.save_rejected",
                actor=actor,
                status="failure",
                message=validation_message(error),
                metadata={"source": source},
            )
            raise error from exc
        except ValidationError as exc:
            record_event(
                action="pod.blank_capability.save_rejected",
                actor=actor,
                status="failure",
                message=validation_message(exc),
                metadata={"source": source},
            )
            raise

    def update_capability(
        self,
        *,
        actor,
        source: str,
        blank_public_id,
        capability_public_id,
        data: dict,
    ) -> BlankPlacementCapability:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.blank.permission_rejected",
        )
        try:
            with transaction.atomic():
                blank = Blank.objects.select_for_update().filter(public_id=blank_public_id).first()
                if blank is None:
                    raise ValidationError("Support vierge introuvable.")
                if blank.marking_options_configured:
                    raise ValidationError(
                        "Configurez les zones et techniques dans les listes du support."
                    )
                capability = (
                    BlankPlacementCapability.objects.select_for_update()
                    .filter(public_id=capability_public_id, blank=blank)
                    .first()
                )
                if capability is None:
                    raise ValidationError("Pose autorisée introuvable.")
                requested_required = _is_checked(data.get("is_required"))
                requested_active = _is_checked(data.get("is_active"))
                if (
                    capability.is_active and not requested_active
                ) or capability.is_required != requested_required:
                    queued_count = _queued_for_capability(capability)
                    if queued_count:
                        raise ValidationError(
                            "Modification impossible : "
                            f"{queued_count} commande(s) POD en cours utilisent cette pose."
                        )
                if requested_active and (not blank.is_active or not capability.technique.is_active):
                    raise ValidationError(
                        "Réactivation impossible : le support ou la technique est inactif."
                    )
                previous = {
                    "is_required": capability.is_required,
                    "is_active": capability.is_active,
                }
                capability.is_required = requested_required
                capability.is_active = requested_active
                capability.full_clean()
                capability.save(update_fields=["is_required", "is_active", "updated_at"])
                record_event(
                    action="pod.blank_capability.updated",
                    actor=actor,
                    target=capability,
                    metadata={
                        "source": source,
                        "blank": str(blank.public_id),
                        "previous": previous,
                        "changes": {
                            "is_required": capability.is_required,
                            "is_active": capability.is_active,
                        },
                    },
                )
                return capability
        except ValidationError as exc:
            record_event(
                action="pod.blank_capability.update_rejected",
                actor=actor,
                status="failure",
                message=validation_message(exc),
                metadata={"source": source, "blank": str(blank_public_id)},
            )
            raise
