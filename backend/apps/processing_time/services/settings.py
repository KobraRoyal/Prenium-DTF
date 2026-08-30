from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from apps.auditlog.services import record_event
from apps.processing_time.models import ProcessingTimeOption
from apps.processing_time.services.options import ProcessingTimeOptionService


class ProcessingTimeSettingsService:
    def __init__(self, *, options_service: ProcessingTimeOptionService | None = None):
        self.options_service = options_service or ProcessingTimeOptionService()

    def list_options(self):
        self.options_service.ensure_default_options()
        return list(
            ProcessingTimeOption.objects.all().order_by("display_order", "name")
        )

    @transaction.atomic
    def update(
        self,
        *,
        payloads: list[dict],
        actor: AbstractBaseUser,
        source: str,
    ) -> list[ProcessingTimeOption]:
        updated: list[ProcessingTimeOption] = []
        for payload in payloads:
            option = ProcessingTimeOption.objects.select_for_update().get(code=payload["code"])
            option.name = payload["name"]
            option.eta_label = payload["eta_label"]
            option.disclaimer = payload["disclaimer"]
            option.business_days = payload["business_days"]
            option.markup_percent = payload["markup_percent"]
            option.flat_fee_eur = payload["flat_fee_eur"]
            option.is_default = payload["is_default"]
            option.is_active = payload["is_active"]
            option.display_order = payload["display_order"]
            option.save(
                update_fields=[
                    "name",
                    "eta_label",
                    "disclaimer",
                    "business_days",
                    "markup_percent",
                    "flat_fee_eur",
                    "is_default",
                    "is_active",
                    "display_order",
                    "updated_at",
                ]
            )
            updated.append(option)
        if not ProcessingTimeOption.objects.filter(is_default=True, is_active=True).exists():
            fallback = (
                ProcessingTimeOption.objects.filter(is_active=True)
                .order_by("display_order")
                .first()
            )
            if fallback is not None:
                ProcessingTimeOption.objects.exclude(pk=fallback.pk).update(is_default=False)
                fallback.is_default = True
                fallback.save(update_fields=["is_default", "updated_at"])
        record_event(
            action="processing_time.settings_updated",
            actor=actor,
            target=updated[0] if updated else None,
            metadata={
                "source": source,
                "option_codes": [option.code for option in updated],
            },
        )
        return updated
