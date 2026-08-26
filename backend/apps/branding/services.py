from __future__ import annotations

from dataclasses import asdict, dataclass

from django.core.exceptions import PermissionDenied
from django.db import OperationalError, ProgrammingError, transaction

from apps.auditlog.services import record_event
from apps.branding.models import BrandThemeSettings

DEFAULT_PRIMARY_COLOR = "#FF8775"
DEFAULT_SECONDARY_COLOR = "#A83BC4"

PAPER_COLOR = "#F4F0E6"
PAPER_ACCENT_COLOR = "#ECE7D8"
CARD_COLOR = "#FBF6EE"
CARD_RAISED_COLOR = "#FFFDF8"
INK_COLOR = "#1A1815"
INK_SECONDARY_COLOR = "#3A372F"
MUTED_COLOR = "#6B675C"
LINE_COLOR = "#E2DCCB"


@dataclass(frozen=True)
class BrandTheme:
    theme_key: str
    version: int
    primary: str
    primary_strong: str
    primary_soft: str
    primary_ink: str
    secondary: str
    secondary_strong: str
    secondary_soft: str
    secondary_ink: str
    paper: str = PAPER_COLOR
    paper_accent: str = PAPER_ACCENT_COLOR
    card: str = CARD_COLOR
    card_raised: str = CARD_RAISED_COLOR
    ink: str = INK_COLOR
    ink_secondary: str = INK_SECONDARY_COLOR
    muted: str = MUTED_COLOR
    line: str = LINE_COLOR

    def as_context(self) -> dict[str, str | int]:
        return asdict(self)


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{channel:02X}" for channel in rgb)


def _mix(foreground: str, background: str, foreground_weight: float) -> str:
    weight = min(1.0, max(0.0, foreground_weight))
    foreground_rgb = _rgb(foreground)
    background_rgb = _rgb(background)
    return _hex(
        tuple(
            round(foreground_channel * weight + background_channel * (1 - weight))
            for foreground_channel, background_channel in zip(
                foreground_rgb, background_rgb, strict=True
            )
        )
    )


def _relative_luminance(hex_color: str) -> float:
    def linearize(channel: int) -> float:
        value = channel / 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (linearize(channel) for channel in _rgb(hex_color))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(first: str, second: str) -> float:
    first_luminance = _relative_luminance(first)
    second_luminance = _relative_luminance(second)
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def _readable_ink(background: str) -> str:
    candidates = (INK_COLOR, "#FFFFFF", "#000000")
    return max(candidates, key=lambda candidate: contrast_ratio(candidate, background))


def build_brand_theme(
    *,
    primary: str = DEFAULT_PRIMARY_COLOR,
    secondary: str = DEFAULT_SECONDARY_COLOR,
    theme_key: str = BrandThemeSettings.ThemeKey.OCTOSTITCH_LIGHT,
    version: int = 1,
) -> BrandTheme:
    primary = primary.strip().upper()
    secondary = secondary.strip().upper()
    primary_strong = (
        "#E65944" if primary == DEFAULT_PRIMARY_COLOR else _mix(primary, INK_COLOR, 0.78)
    )
    secondary_strong = (
        "#770176" if secondary == DEFAULT_SECONDARY_COLOR else _mix(secondary, INK_COLOR, 0.78)
    )
    return BrandTheme(
        theme_key=theme_key,
        version=version,
        primary=primary,
        primary_strong=primary_strong,
        primary_soft=_mix(primary, CARD_RAISED_COLOR, 0.16),
        primary_ink=_readable_ink(primary),
        secondary=secondary,
        secondary_strong=secondary_strong,
        secondary_soft=_mix(secondary, CARD_RAISED_COLOR, 0.14),
        secondary_ink=_readable_ink(secondary),
    )


class BrandThemeService:
    change_permission = "branding.change_brandthemesettings"

    def current_settings(self) -> BrandThemeSettings | None:
        try:
            return BrandThemeSettings.objects.filter(singleton_key=1).first()
        except (OperationalError, ProgrammingError):
            return None

    def get_effective_theme(self) -> BrandTheme:
        row = self.current_settings()
        if row is None:
            return build_brand_theme()
        return build_brand_theme(
            primary=row.primary_color,
            secondary=row.secondary_color,
            theme_key=row.theme_key,
            version=row.version,
        )

    def _require_change_permission(self, actor) -> None:
        if not getattr(actor, "is_authenticated", False) or not actor.has_perm(
            self.change_permission
        ):
            raise PermissionDenied

    @transaction.atomic
    def update(
        self,
        *,
        primary_color: str,
        secondary_color: str,
        actor,
        source: str,
        ip_address: str | None = None,
    ) -> BrandThemeSettings:
        self._require_change_permission(actor)
        row, created = BrandThemeSettings.objects.select_for_update().get_or_create(singleton_key=1)
        before = {
            "theme_key": row.theme_key,
            "primary_color": row.primary_color,
            "secondary_color": row.secondary_color,
            "version": row.version,
        }
        row.primary_color = primary_color.strip().upper()
        row.secondary_color = secondary_color.strip().upper()
        row.updated_by = actor
        row.version = 1 if created else row.version + 1
        row.full_clean()
        row.save(
            update_fields=[
                "theme_key",
                "primary_color",
                "secondary_color",
                "version",
                "updated_by",
                "updated_at",
            ]
        )
        after = {
            "theme_key": row.theme_key,
            "primary_color": row.primary_color,
            "secondary_color": row.secondary_color,
            "version": row.version,
        }
        record_event(
            action="branding.theme.updated",
            actor=actor,
            target=row,
            ip_address=ip_address,
            metadata={
                "scope": "global",
                "source": source,
                "before": before,
                "after": after,
            },
        )
        return row

    def restore_defaults(self, *, actor, source: str, ip_address: str | None = None):
        return self.update(
            primary_color=DEFAULT_PRIMARY_COLOR,
            secondary_color=DEFAULT_SECONDARY_COLOR,
            actor=actor,
            source=source,
            ip_address=ip_address,
        )


brand_theme_service = BrandThemeService()
