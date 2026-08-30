from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.auditlog.services import record_event
from apps.pod.models import Blank, BlankPlacementCapability, BlankVariant, PrintTechnique
from apps.pod.services.validation import (
    clean_hex_color,
    clean_sku,
    require_staff_perm,
    validation_message,
)

DTF_TECHNIQUE_CODE = "dtf"


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
            if not rip_directory.startswith("02_"):
                raise ValidationError("Le répertoire RIP doit commencer par 02_.")
            if not export_extension.startswith("."):
                export_extension = f".{export_extension}"
            with transaction.atomic():
                technique = PrintTechnique.objects.create(
                    code=code,
                    name=name,
                    rip_directory=rip_directory,
                    export_extension=export_extension,
                    is_active=True,
                )
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
                blank = Blank.objects.create(sku=sku, name=name, brand=brand)
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
                variant = BlankVariant.objects.create(
                    blank=blank,
                    sku=clean_sku(data.get("sku", ""), field_label="SKU variante"),
                    size_label=(data.get("size_label") or "").strip() or "U",
                    color_name=(data.get("color_name") or "").strip() or "Standard",
                    color_hex=clean_hex_color(data.get("color_hex", "")),
                )
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
            technique = PrintTechnique.objects.filter(
                public_id=data.get("technique_public_id"),
                is_active=True,
            ).first()
            if technique is None:
                raise ValidationError("Technique introuvable.")
            with transaction.atomic():
                blank = Blank.objects.select_for_update().filter(public_id=blank_public_id).first()
                if blank is None:
                    raise ValidationError("Support vierge introuvable.")
                capability, created = BlankPlacementCapability.objects.update_or_create(
                    blank=blank,
                    placement=placement,
                    technique=technique,
                    defaults={
                        "is_required": bool(data.get("is_required")),
                        "is_active": True,
                    },
                )
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
