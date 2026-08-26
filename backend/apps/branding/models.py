from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

from apps.core.models import BaseModel

hex_color_validator = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="Saisissez une couleur hexadécimale complète, par exemple #FF8775.",
)


class BrandThemeSettings(BaseModel):
    """Identité visuelle globale du mono-Atelier, partagée par tous les clients."""

    class ThemeKey(models.TextChoices):
        OCTOSTITCH_LIGHT = "octostitch_light", "Clair chaleureux"

    singleton_key = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)
    theme_key = models.CharField(
        "Univers visuel",
        max_length=32,
        choices=ThemeKey.choices,
        default=ThemeKey.OCTOSTITCH_LIGHT,
        editable=False,
    )
    primary_color = models.CharField(
        "Couleur primaire",
        max_length=7,
        default="#FF8775",
        validators=[hex_color_validator],
    )
    secondary_color = models.CharField(
        "Couleur secondaire",
        max_length=7,
        default="#A83BC4",
        validators=[hex_color_validator],
    )
    version = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_brand_theme_settings",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(singleton_key=1),
                name="brand_theme_singleton_key_one",
            ),
            models.CheckConstraint(
                condition=models.Q(theme_key="octostitch_light"),
                name="brand_theme_key_supported",
            ),
            models.CheckConstraint(
                condition=models.Q(primary_color__regex=r"^#[0-9A-F]{6}$"),
                name="brand_theme_primary_hex",
            ),
            models.CheckConstraint(
                condition=models.Q(secondary_color__regex=r"^#[0-9A-F]{6}$"),
                name="brand_theme_secondary_hex",
            ),
            models.CheckConstraint(
                condition=~models.Q(primary_color=models.F("secondary_color")),
                name="brand_theme_colors_distinct",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="brand_theme_version_positive",
            ),
        ]
        verbose_name = "Identité visuelle du site"
        verbose_name_plural = "Identité visuelle du site"

    def clean(self):
        super().clean()
        self.primary_color = str(self.primary_color or "").strip().upper()
        self.secondary_color = str(self.secondary_color or "").strip().upper()
        if self.primary_color and self.primary_color == self.secondary_color:
            raise ValidationError(
                {"secondary_color": "Choisissez une couleur secondaire différente."}
            )

    def __str__(self) -> str:
        return "Identité visuelle du site"
