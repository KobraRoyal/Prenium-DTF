from django.db import models

from apps.core.models import BaseModel


class PrintTechniqueQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class BlankQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class PrintTechnique(BaseModel):
    code = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=120)
    rip_directory = models.CharField(max_length=64, default="02_rip")
    export_extension = models.CharField(max_length=16, default=".png")
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    objects = PrintTechniqueQuerySet.as_manager()

    class Meta:
        ordering = ("display_order", "name")
        indexes = [
            models.Index(fields=("is_active", "display_order")),
        ]
        permissions = [
            ("access_pod_atelier", "Can access POD atelier catalog and warehouse"),
            ("manage_pod_catalog", "Can manage POD techniques and blanks"),
        ]

    def __str__(self) -> str:
        return self.name


class Blank(BaseModel):
    sku = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=160)
    brand = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)

    objects = BlankQuerySet.as_manager()

    class Meta:
        ordering = ("name", "sku")
        indexes = [
            models.Index(fields=("is_active", "name")),
        ]

    def __str__(self) -> str:
        return f"{self.sku} — {self.name}"


class BlankVariant(BaseModel):
    blank = models.ForeignKey(Blank, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField(max_length=80, unique=True)
    size_label = models.CharField(max_length=32)
    color_name = models.CharField(max_length=64)
    color_hex = models.CharField(max_length=7, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("size_label", "color_name", "sku")
        indexes = [
            models.Index(fields=("blank", "is_active")),
        ]

    def __str__(self) -> str:
        return self.sku


class BlankPlacementCapability(BaseModel):
    class Placement(models.TextChoices):
        FRONT = "front", "Devant"
        BACK = "back", "Dos"
        LEFT_CHEST = "left_chest", "Cœur"
        RIGHT_CHEST = "right_chest", "Poitrine droite"
        SLEEVE_LEFT = "sleeve_left", "Manche gauche"
        SLEEVE_RIGHT = "sleeve_right", "Manche droite"
        COLLAR = "collar", "Col"
        OTHER = "other", "Autre"

    blank = models.ForeignKey(
        Blank,
        on_delete=models.CASCADE,
        related_name="placement_capabilities",
    )
    technique = models.ForeignKey(
        PrintTechnique,
        on_delete=models.PROTECT,
        related_name="blank_capabilities",
    )
    placement = models.CharField(max_length=32, choices=Placement.choices)
    is_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("blank_id", "placement", "technique_id")
        constraints = [
            models.UniqueConstraint(
                fields=("blank", "placement", "technique"),
                name="pod_blank_placement_technique_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("blank", "is_active")),
        ]

    def __str__(self) -> str:
        return f"{self.blank.sku}:{self.placement}:{self.technique.code}"
