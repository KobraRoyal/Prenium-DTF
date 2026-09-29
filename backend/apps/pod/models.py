from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import BaseModel


def _blank_photo_upload_to(instance, _filename: str) -> str:
    return f"pod/blanks/{instance.public_id}/photo.webp"


def _blank_photo_thumb_upload_to(instance, _filename: str) -> str:
    return f"pod/blanks/{instance.public_id}/thumb.webp"


def _blank_variant_photo_upload_to(instance, _filename: str) -> str:
    return f"pod/blanks/{instance.blank.public_id}/variants/{instance.public_id}/photo.webp"


def _blank_variant_photo_thumb_upload_to(instance, _filename: str) -> str:
    return f"pod/blanks/{instance.blank.public_id}/variants/{instance.public_id}/thumb.webp"


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
            ("operate_pod_production", "Can operate POD production floor"),
        ]

    def __str__(self) -> str:
        return self.name


class MarkingZone(BaseModel):
    code = models.SlugField(max_length=32, unique=True, editable=False)
    name = models.CharField(max_length=120)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("display_order", "name")
        indexes = [
            models.Index(
                fields=("is_active", "display_order"),
                name="pod_marking_active_order_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Blank(BaseModel):
    sku = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=160)
    brand = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)
    photo = models.ImageField(upload_to=_blank_photo_upload_to, blank=True, max_length=512)
    photo_thumb = models.ImageField(
        upload_to=_blank_photo_thumb_upload_to, blank=True, max_length=512
    )
    allowed_zones = models.ManyToManyField(
        MarkingZone,
        blank=True,
        related_name="blanks",
    )
    allowed_techniques = models.ManyToManyField(
        PrintTechnique,
        blank=True,
        related_name="allowed_blanks",
    )
    marking_options_configured = models.BooleanField(default=False)

    objects = BlankQuerySet.as_manager()

    class Meta:
        ordering = ("name", "sku")
        indexes = [
            models.Index(fields=("is_active", "name")),
        ]

    def __str__(self) -> str:
        return f"{self.sku} — {self.name}"

    @property
    def has_photo(self) -> bool:
        return bool(self.photo_thumb) or bool(self.photo)


class BlankVariant(BaseModel):
    blank = models.ForeignKey(Blank, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField(max_length=80, unique=True)
    size_label = models.CharField(max_length=32)
    color_name = models.CharField(max_length=64)
    color_hex = models.CharField(max_length=7, blank=True)
    is_active = models.BooleanField(default=True)
    photo = models.ImageField(upload_to=_blank_variant_photo_upload_to, blank=True, max_length=512)
    photo_thumb = models.ImageField(
        upload_to=_blank_variant_photo_thumb_upload_to, blank=True, max_length=512
    )

    class Meta:
        ordering = ("size_label", "color_name", "sku")
        indexes = [
            models.Index(fields=("blank", "is_active")),
        ]

    def __str__(self) -> str:
        return self.sku

    @property
    def has_own_photo(self) -> bool:
        return bool(self.photo_thumb) or bool(self.photo)

    @property
    def has_photo(self) -> bool:
        return self.has_own_photo or self.blank.has_photo


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
    customer = models.ForeignKey(
        "customers.Customer",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pod_shopify_stores",
    )
    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=160)
    shop_domain = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    webhook_secret = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Secret HMAC Shopify (jamais exposé en front).",
    )
    access_token_encrypted = models.TextField(blank=True, default="")
    token_suffix = models.CharField(max_length=8, blank=True, default="")
    oauth_scopes = models.CharField(max_length=255, blank=True, default="")
    connected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class ShopifyWebhookReceipt(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        PROCESSED = "processed", "Traité"
        FAILED = "failed", "À rejouer"

    webhook_id = models.CharField(max_length=128)
    shop_domain = models.CharField(max_length=255)
    topic = models.CharField(max_length=64, default="orders/create")
    raw_body = models.BinaryField(blank=True, default=bytes)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROCESSED)
    attempts = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("webhook_id",),
                name="pod_webhook_receipt_id_uniq",
            ),
        ]

    def __str__(self) -> str:
        return self.webhook_id


class ShopifyProduct(BaseModel):
    store = models.ForeignKey(ShopifyStore, on_delete=models.CASCADE, related_name="products")
    external_id = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    handle = models.SlugField(max_length=255, blank=True)
    image_url = models.URLField(max_length=512, blank=True, default="")
    image_external_id = models.CharField(max_length=64, blank=True, default="")

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

    @property
    def has_image(self) -> bool:
        return bool(self.image_url)


class ShopifyVariant(BaseModel):
    product = models.ForeignKey(ShopifyProduct, on_delete=models.CASCADE, related_name="variants")
    external_id = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    sku = models.CharField(max_length=80, blank=True)
    option1 = models.CharField(max_length=120, blank=True)
    option2 = models.CharField(max_length=120, blank=True)
    option3 = models.CharField(max_length=120, blank=True)
    image_url = models.URLField(max_length=512, blank=True, default="")
    image_external_id = models.CharField(max_length=64, blank=True, default="")

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

    @property
    def has_image(self) -> bool:
        return bool(self.image_url) or bool(self.product.image_url)

    @property
    def resolved_image_url(self) -> str:
        return self.image_url or self.product.image_url or ""


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


class PodDriveHdSourceQuerySet(models.QuerySet):
    def for_customer(self, customer):
        return self.filter(customer=customer)


class PodDriveHdSource(BaseModel):
    """Provenance immuable d'un fichier HD Drive importé pour un Customer."""

    class Status(models.TextChoices):
        PENDING = "pending", "Import en attente"
        IMPORTING = "importing", "Import en cours"
        READY = "ready", "Importé"
        FAILED = "failed", "Échec"

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="pod_drive_hd_sources",
    )
    selected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="selected_pod_drive_hd_sources",
    )
    drive_file_id = models.CharField(max_length=255)
    canonical_url = models.URLField(max_length=512)
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=127)
    size_bytes = models.PositiveBigIntegerField()
    md5_checksum = models.CharField(max_length=32)
    drive_version = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    asset_version = models.ForeignKey(
        "uploads.AssetVersion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pod_drive_hd_sources",
    )
    last_error = models.CharField(max_length=255, blank=True, default="")

    objects = PodDriveHdSourceQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("customer", "drive_file_id", "drive_version"),
                name="pod_drive_hd_source_customer_file_version_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("customer", "status", "created_at"),
                name="pod_hd_customer_status_idx",
            ),
            models.Index(
                fields=("customer", "drive_file_id"),
                name="pod_hd_customer_file_idx",
            ),
        ]

    def clean(self):
        super().clean()
        if self.asset_version_id and self.asset_version.customer_id != self.customer_id:
            raise ValidationError(
                {"asset_version": "La version importée doit appartenir au même client."}
            )

    def __str__(self) -> str:
        return f"{self.customer_id}:{self.original_filename}@{self.drive_version}"


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
    source_asset_version = models.ForeignKey(
        "uploads.AssetVersion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pod_recipe_slots",
    )
    source_drive_hd = models.ForeignKey(
        PodDriveHdSource,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="recipe_slots",
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

    def clean(self):
        super().clean()
        if not self.source_drive_hd_id and not self.source_asset_version_id:
            return
        customer_id = self.recipe.variant_config.variant.product.store.customer_id
        if customer_id is None:
            raise ValidationError(
                "La boutique doit être liée à un client pour référencer un visuel HD."
            )
        if self.source_drive_hd_id and self.source_drive_hd.customer_id != customer_id:
            raise ValidationError(
                {"source_drive_hd": "La source Drive HD doit appartenir au client de la boutique."}
            )
        if self.source_asset_version_id and self.source_asset_version.customer_id != customer_id:
            raise ValidationError(
                {
                    "source_asset_version": (
                        "La version HD doit appartenir au client de la boutique."
                    )
                }
            )
        if (
            self.source_drive_hd_id
            and self.source_asset_version_id
            and self.source_drive_hd.asset_version_id
            and self.source_drive_hd.asset_version_id != self.source_asset_version_id
        ):
            raise ValidationError(
                {"source_asset_version": "La version HD ne correspond pas à la source Drive."}
            )


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


class PodShopifyOrder(BaseModel):
    store = models.ForeignKey(
        ShopifyStore,
        on_delete=models.PROTECT,
        related_name="pod_orders",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pod_shopify_orders",
    )
    external_order_id = models.CharField(max_length=64)
    order_number = models.CharField(max_length=64)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("store", "external_order_id"),
                name="pod_shopify_order_store_external_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("customer", "created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.store.slug} {self.order_number}"


class PodRipWorkItem(BaseModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "En file RIP"
        INCLUDED = "included", "Inclus dans un lot"
        SKIPPED = "skipped", "Ignoré (config incomplète)"
        CANCELLED = "cancelled", "Annulé (Shopify)"

    store = models.ForeignKey(
        "ShopifyStore",
        on_delete=models.CASCADE,
        related_name="rip_work_items",
    )
    variant = models.ForeignKey(
        ShopifyVariant,
        on_delete=models.PROTECT,
        related_name="rip_work_items",
    )
    shopify_order_number = models.CharField(max_length=64)
    shopify_order = models.ForeignKey(
        PodShopifyOrder,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="work_items",
    )
    shopify_line_item_id = models.CharField(max_length=64, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    skip_reason = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("status", "created_at")),
            models.Index(fields=("store", "shopify_order")),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        shopify_order__isnull=True,
                        shopify_line_item_id__isnull=True,
                    )
                    | models.Q(
                        shopify_order__isnull=False,
                        shopify_line_item_id__isnull=False,
                    )
                ),
                name="pod_rip_item_shopify_identity_pair",
            ),
            models.UniqueConstraint(
                fields=("shopify_order", "shopify_line_item_id"),
                condition=models.Q(
                    shopify_order__isnull=False,
                    shopify_line_item_id__isnull=False,
                ),
                name="pod_rip_item_shopify_identity_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.shopify_order_number} {self.variant}"


class PodRipLot(BaseModel):
    class Status(models.TextChoices):
        PREPARED = "prepared", "Prêt RIP"
        FAILED = "failed", "Échec préparation"

    code = models.CharField(max_length=48, unique=True)
    customer = models.ForeignKey(
        "customers.Customer",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pod_rip_lots",
    )
    technique = models.ForeignKey(
        PrintTechnique,
        on_delete=models.PROTECT,
        related_name="rip_lots",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PREPARED)
    nas_relative_path = models.CharField(max_length=255)
    file_count = models.PositiveIntegerField(default=0)
    prepared_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="prepared_pod_rip_lots",
    )
    prepared_at = models.DateTimeField(null=True, blank=True)
    error_message = models.CharField(max_length=255, blank=True, default="")
    drive_folder_id = models.CharField(max_length=128, blank=True, default="")
    drive_file_count = models.PositiveIntegerField(default=0)
    drive_synced_at = models.DateTimeField(null=True, blank=True)
    drive_error = models.CharField(max_length=255, blank=True, default="")
    operator_print_confirmed_at = models.DateTimeField(null=True, blank=True)
    operator_print_confirmed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="confirmed_pod_rip_prints",
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.code


class PodRipLotFile(BaseModel):
    lot = models.ForeignKey(PodRipLot, on_delete=models.CASCADE, related_name="files")
    work_item = models.ForeignKey(
        PodRipWorkItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rip_files",
    )
    variant = models.ForeignKey(
        ShopifyVariant,
        on_delete=models.PROTECT,
        related_name="rip_lot_files",
    )
    placement = models.CharField(max_length=32)
    technique = models.ForeignKey(PrintTechnique, on_delete=models.PROTECT, related_name="+")
    filename = models.CharField(max_length=255)
    source_print_reference = models.CharField(max_length=255)
    source_asset_version = models.ForeignKey(
        "uploads.AssetVersion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pod_rip_files",
    )
    checksum_sha256 = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ("filename",)
        constraints = [
            models.UniqueConstraint(
                fields=("lot", "filename"),
                name="pod_rip_lot_filename_uniq",
            ),
        ]

    def __str__(self) -> str:
        return self.filename


class PodUnit(BaseModel):
    class Status(models.TextChoices):
        WAITING_PRESS = "waiting_press", "Attente pose"
        PRESSED = "pressed", "Posé"
        QC_PASSED = "qc_passed", "Contrôle validé"
        QC_FAILED = "qc_failed", "Contrôle refusé"
        ISSUE = "issue", "Incident"

    lot = models.ForeignKey(PodRipLot, on_delete=models.CASCADE, related_name="units")
    work_item = models.ForeignKey(
        PodRipWorkItem,
        on_delete=models.PROTECT,
        related_name="units",
    )
    variant = models.ForeignKey(
        ShopifyVariant,
        on_delete=models.PROTECT,
        related_name="pod_units",
    )
    sequence = models.PositiveIntegerField(default=1)
    scan_identifier = models.CharField(max_length=32, unique=True, db_index=True)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.WAITING_PRESS,
    )
    of_relative_path = models.CharField(max_length=255, blank=True, default="")
    label_relative_path = models.CharField(max_length=255, blank=True, default="")
    pressed_at = models.DateTimeField(null=True, blank=True)
    pressed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pressed_pod_units",
    )

    class Meta:
        ordering = ("scan_identifier",)
        indexes = [
            models.Index(fields=("status", "created_at"), name="pod_unit_qc_queue_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("work_item", "sequence"),
                name="pod_unit_work_item_sequence_uniq",
            ),
        ]

    def __str__(self) -> str:
        return self.scan_identifier


class PodQualityCheck(BaseModel):
    class Result(models.TextChoices):
        PASS = "pass", "Conforme"
        FAIL = "fail", "Refusé"

    unit = models.ForeignKey(
        PodUnit,
        on_delete=models.PROTECT,
        related_name="quality_checks",
    )
    result = models.CharField(max_length=8, choices=Result.choices)
    defect_code = models.CharField(max_length=80, blank=True, default="")
    note = models.CharField(max_length=500, blank=True, default="")
    checked_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pod_quality_checks",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("unit", "created_at"), name="pod_qc_unit_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.unit.scan_identifier}: {self.get_result_display()}"


class PodPickSession(BaseModel):
    code = models.CharField(max_length=32, unique=True)
    customer = models.ForeignKey(
        "customers.Customer",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pod_pick_sessions",
    )
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pod_pick_sessions",
    )
    piece_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.code


class PodPickSessionLine(BaseModel):
    class ReservationStatus(models.TextChoices):
        UNTRACKED = "untracked", "Non réservé"
        RESERVED = "reserved", "Réservé"
        PICKED = "picked", "Prélevé"
        RELEASED = "released", "Libéré"

    session = models.ForeignKey(
        PodPickSession,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    work_item = models.ForeignKey(
        PodRipWorkItem,
        on_delete=models.PROTECT,
        related_name="pick_lines",
    )
    sequence = models.PositiveIntegerField(default=1)
    scan_identifier = models.CharField(max_length=32, unique=True, db_index=True)
    unit = models.OneToOneField(
        "pod.PodUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pick_line",
    )
    shopify_order_number = models.CharField(max_length=64)
    shopify_sku = models.CharField(max_length=80, blank=True, default="")
    blank_name = models.CharField(max_length=160, blank=True, default="")
    blank_sku = models.CharField(max_length=80, blank=True, default="")
    size_label = models.CharField(max_length=32, blank=True, default="")
    color_name = models.CharField(max_length=64, blank=True, default="")
    location_code = models.CharField(max_length=64, blank=True, default="")
    markings = models.CharField(max_length=255, blank=True, default="")
    reservation_status = models.CharField(
        max_length=16,
        choices=ReservationStatus.choices,
        default=ReservationStatus.UNTRACKED,
        db_index=True,
    )
    stock_balance = models.ForeignKey(
        "inventory.StockBalance",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pod_pick_lines",
    )
    reserved_at = models.DateTimeField(null=True, blank=True)
    reserved_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reserved_pod_pick_lines",
    )
    picked_at = models.DateTimeField(null=True, blank=True)
    picked_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="picked_pod_pick_lines",
    )
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="released_pod_pick_lines",
    )
    voided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("location_code", "blank_sku", "shopify_order_number", "sequence")
        constraints = [
            models.UniqueConstraint(
                fields=("work_item", "sequence"),
                name="pod_pick_line_work_item_sequence_uniq",
            ),
        ]

    def __str__(self) -> str:
        return self.scan_identifier
