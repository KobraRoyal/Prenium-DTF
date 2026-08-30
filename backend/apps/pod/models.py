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


class ShopifyStore(BaseModel):
    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=160)
    shop_domain = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class ShopifyProduct(BaseModel):
    store = models.ForeignKey(ShopifyStore, on_delete=models.CASCADE, related_name="products")
    external_id = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    handle = models.SlugField(max_length=255, blank=True)

    class Meta:
        ordering = ("title",)
        constraints = [
            models.UniqueConstraint(
                fields=("store", "external_id"),
                name="pod_shopify_product_store_external_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("store", "title")),
        ]

    def __str__(self) -> str:
        return self.title


class ShopifyVariant(BaseModel):
    product = models.ForeignKey(ShopifyProduct, on_delete=models.CASCADE, related_name="variants")
    external_id = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    sku = models.CharField(max_length=80, blank=True)
    option1 = models.CharField(max_length=120, blank=True)
    option2 = models.CharField(max_length=120, blank=True)
    option3 = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ("title", "sku")
        constraints = [
            models.UniqueConstraint(
                fields=("product", "external_id"),
                name="pod_shopify_variant_product_external_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("product", "sku")),
        ]

    def __str__(self) -> str:
        return self.title or self.sku or str(self.public_id)


class IdsVariantConfig(BaseModel):
    class Mode(models.TextChoices):
        UNMANAGED = "unmanaged", "Non géré"
        POD = "pod", "POD"
        ON_STOCK = "on_stock", "Produit fini"
        VIRTUAL = "virtual", "Virtuel"
        DISABLED = "disabled", "Désactivé"

    variant = models.OneToOneField(
        ShopifyVariant,
        on_delete=models.CASCADE,
        related_name="ids_config",
    )
    mode = models.CharField(
        max_length=16,
        choices=Mode.choices,
        default=Mode.UNMANAGED,
    )
    blank_variant = models.ForeignKey(
        BlankVariant,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="variant_configs",
    )
    finished_sku = models.CharField(max_length=80, blank=True, default="")
    staff_locked = models.BooleanField(
        default=False,
        help_text="Si actif, le marchand Shopify ne peut pas modifier la config.",
    )

    class Meta:
        indexes = [
            models.Index(fields=("mode",)),
        ]

    def __str__(self) -> str:
        return f"{self.variant} → {self.mode}"


class PodRecipe(BaseModel):
    variant_config = models.OneToOneField(
        IdsVariantConfig,
        on_delete=models.CASCADE,
        related_name="recipe",
    )

    def __str__(self) -> str:
        return f"Recette {self.variant_config.variant_id}"


class PodRecipeSlot(BaseModel):
    recipe = models.ForeignKey(PodRecipe, on_delete=models.CASCADE, related_name="slots")
    placement = models.CharField(max_length=32, choices=BlankPlacementCapability.Placement.choices)
    technique = models.ForeignKey(
        PrintTechnique,
        on_delete=models.PROTECT,
        related_name="recipe_slots",
    )
    is_enabled = models.BooleanField(default=True)
    print_reference = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Référence fichier HD (nom RIP ou public_id AssetVersion).",
    )
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("display_order", "placement", "technique_id")
        constraints = [
            models.UniqueConstraint(
                fields=("recipe", "placement", "technique"),
                name="pod_recipe_slot_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.placement}:{self.technique.code}"


class PodRecipeTemplate(BaseModel):
    name = models.CharField(max_length=160)
    blank = models.ForeignKey(Blank, on_delete=models.PROTECT, related_name="recipe_templates")
    store = models.ForeignKey(
        ShopifyStore,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="recipe_templates",
    )
    description = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=("name", "blank", "store"),
                name="pod_recipe_template_name_blank_store_uniq",
                nulls_distinct=False,
            ),
        ]

    def __str__(self) -> str:
        return self.name


class PodRecipeTemplateSlot(BaseModel):
    template = models.ForeignKey(
        PodRecipeTemplate,
        on_delete=models.CASCADE,
        related_name="slots",
    )
    placement = models.CharField(max_length=32, choices=BlankPlacementCapability.Placement.choices)
    technique = models.ForeignKey(
        PrintTechnique,
        on_delete=models.PROTECT,
        related_name="template_slots",
    )
    print_reference = models.CharField(max_length=255, blank=True, default="")
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("display_order", "placement", "technique_id")
        constraints = [
            models.UniqueConstraint(
                fields=("template", "placement", "technique"),
                name="pod_recipe_template_slot_uniq",
            ),
        ]
