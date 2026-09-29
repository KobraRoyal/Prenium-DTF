from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.pod.models import (
    Blank,
    MarkingZone,
    PodRecipeSlot,
    PodRipWorkItem,
    PrintTechnique,
)
from apps.pod.services.validation import require_staff_perm, validation_message


@dataclass(frozen=True)
class BlankMarkingCapability:
    placement: str
    placement_label: str
    technique: PrintTechnique
    is_required: bool = False

    @property
    def technique_id(self) -> int:
        return self.technique.pk

    def get_placement_display(self) -> str:
        return self.placement_label


def capabilities_for_blank(blank: Blank) -> tuple[BlankMarkingCapability, ...]:
    """Expose the legacy capability interface during the normalized-options transition."""
    if not blank.marking_options_configured:
        return tuple(
            BlankMarkingCapability(
                placement=capability.placement,
                placement_label=capability.get_placement_display(),
                technique=capability.technique,
                is_required=capability.is_required,
            )
            for capability in blank.placement_capabilities.filter(
                is_active=True,
                technique__is_active=True,
            ).select_related("technique")
        )

    zones = blank.allowed_zones.filter(is_active=True).order_by("display_order", "name")
    techniques = blank.allowed_techniques.filter(is_active=True).order_by(
        "display_order", "name"
    )
    return tuple(
        BlankMarkingCapability(
            placement=zone.code,
            placement_label=zone.name,
            technique=technique,
        )
        for zone in zones
        for technique in techniques
    )


def _strict_uuid(value, *, label: str) -> UUID:
    if isinstance(value, UUID):
        return value
    raw = str(value or "").strip()
    try:
        parsed = UUID(raw)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValidationError(f"{label} invalide.") from exc
    if raw.lower() != str(parsed):
        raise ValidationError(f"{label} invalide.")
    return parsed


def _normalized_uuid_list(values, *, label: str) -> tuple[UUID, ...]:
    result = []
    seen = set()
    for value in values or ():
        parsed = _strict_uuid(value, label=label)
        if parsed not in seen:
            seen.add(parsed)
            result.append(parsed)
    return tuple(result)


class BlankMarkingOptionsService:
    manage_permission = "pod.manage_pod_catalog"

    def selection_context(self, blank: Blank) -> dict:
        zones = list(MarkingZone.objects.filter(is_active=True))
        techniques = list(PrintTechnique.objects.filter(is_active=True))
        if blank.marking_options_configured:
            selected_zone_ids = {
                str(public_id)
                for public_id in blank.allowed_zones.filter(is_active=True).values_list(
                    "public_id", flat=True
                )
            }
            selected_technique_ids = {
                str(public_id)
                for public_id in blank.allowed_techniques.filter(is_active=True).values_list(
                    "public_id", flat=True
                )
            }
        else:
            capabilities = list(
                blank.placement_capabilities.filter(
                    is_active=True,
                    technique__is_active=True,
                ).select_related("technique")
            )
            zone_ids_by_code = {zone.code: str(zone.public_id) for zone in zones}
            selected_zone_ids = {
                zone_ids_by_code[capability.placement]
                for capability in capabilities
                if capability.placement in zone_ids_by_code
            }
            selected_technique_ids = {
                str(capability.technique.public_id) for capability in capabilities
            }
        return {
            "marking_zones": zones,
            "marking_techniques": techniques,
            "selected_marking_zones": sorted(selected_zone_ids),
            "selected_marking_techniques": sorted(selected_technique_ids),
        }

    def save(
        self,
        *,
        actor,
        source: str,
        blank_public_id,
        zone_public_ids,
        technique_public_ids,
    ) -> Blank:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.blank_marking_options.permission_rejected",
        )
        blank_uuid = None
        zone_uuids = ()
        technique_uuids = ()
        target = None
        try:
            blank_uuid = _strict_uuid(blank_public_id, label="Support vierge")
            zone_uuids = _normalized_uuid_list(zone_public_ids, label="Zone de marquage")
            technique_uuids = _normalized_uuid_list(
                technique_public_ids,
                label="Technique de marquage",
            )
            with transaction.atomic():
                target = Blank.objects.select_for_update().filter(public_id=blank_uuid).first()
                if target is None:
                    raise ValidationError("Support vierge introuvable.")

                zones = list(
                    MarkingZone.objects.filter(public_id__in=zone_uuids, is_active=True)
                )
                techniques = list(
                    PrintTechnique.objects.filter(
                        public_id__in=technique_uuids,
                        is_active=True,
                    )
                )
                if len(zones) != len(zone_uuids):
                    raise ValidationError("Zone de marquage inactive ou introuvable.")
                if len(techniques) != len(technique_uuids):
                    raise ValidationError("Technique de marquage inactive ou introuvable.")

                if target.marking_options_configured:
                    old_zones = list(target.allowed_zones.all())
                    old_techniques = list(target.allowed_techniques.all())
                else:
                    legacy_capabilities = list(
                        target.placement_capabilities.filter(
                            is_active=True,
                            technique__is_active=True,
                        ).select_related("technique")
                    )
                    old_zones = list(
                        MarkingZone.objects.filter(
                            code__in={cap.placement for cap in legacy_capabilities}
                        )
                    )
                    old_techniques = list(
                        {
                            capability.technique.pk: capability.technique
                            for capability in legacy_capabilities
                        }.values()
                    )
                removed_zone_codes = {zone.code for zone in old_zones} - {
                    zone.code for zone in zones
                }
                removed_technique_ids = {
                    technique.pk for technique in old_techniques
                } - {technique.pk for technique in techniques}
                self._reject_used_removals(
                    blank=target,
                    removed_zone_codes=removed_zone_codes,
                    removed_technique_ids=removed_technique_ids,
                )

                previous = {
                    "zones": sorted(str(zone.public_id) for zone in old_zones),
                    "techniques": sorted(
                        str(technique.public_id) for technique in old_techniques
                    ),
                    "configured": target.marking_options_configured,
                }
                target.allowed_zones.set(zones)
                target.allowed_techniques.set(techniques)
                target.marking_options_configured = True
                target.save(update_fields=["marking_options_configured", "updated_at"])
                changes = {
                    "zones": sorted(str(zone.public_id) for zone in zones),
                    "techniques": sorted(str(technique.public_id) for technique in techniques),
                    "configured": True,
                }
                record_event(
                    action="pod.blank_marking_options.saved",
                    actor=actor,
                    target=target,
                    metadata={"source": source, "previous": previous, "changes": changes},
                )
                return target
        except ValidationError as exc:
            record_event(
                action="pod.blank_marking_options.save_rejected",
                actor=actor,
                target=target,
                status=AuditLogEntry.Status.FAILURE,
                message=validation_message(exc),
                metadata={
                    "source": source,
                    "blank": str(blank_uuid or blank_public_id),
                    "zones": [str(value) for value in zone_uuids],
                    "techniques": [str(value) for value in technique_uuids],
                },
            )
            raise

    def _reject_used_removals(
        self,
        *,
        blank: Blank,
        removed_zone_codes: set[str],
        removed_technique_ids: set[int],
    ) -> None:
        if not removed_zone_codes and not removed_technique_ids:
            return
        removed_filter = Q()
        if removed_zone_codes:
            removed_filter |= Q(placement__in=removed_zone_codes)
        if removed_technique_ids:
            removed_filter |= Q(technique_id__in=removed_technique_ids)
        used_slots = PodRecipeSlot.objects.filter(
            removed_filter,
            is_enabled=True,
            recipe__variant_config__blank_variant__blank=blank,
        )
        if not used_slots.exists():
            return
        queued_count = (
            PodRipWorkItem.objects.filter(
                status=PodRipWorkItem.Status.QUEUED,
                variant__ids_config__blank_variant__blank=blank,
                variant__ids_config__recipe__slots__in=used_slots,
            )
            .distinct()
            .count()
        )
        if queued_count:
            raise ValidationError(
                "Suppression impossible : cette option est utilisée par une recette POD "
                f"et {queued_count} travail(aux) sont en file de production."
            )
        raise ValidationError(
            "Suppression impossible : cette option est utilisée par une recette POD active."
        )
