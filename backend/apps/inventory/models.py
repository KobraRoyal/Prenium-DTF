from django.db import models

from apps.core.models import BaseModel
from apps.customers.models import Customer
from apps.pod.models import BlankVariant


class SkuKind(models.TextChoices):
    BLANK = "blank", "Blank vierge"
    FINISHED = "finished", "Produit fini"
    RETURN = "return", "Retour restockable"


class StockOwnerKind(models.TextChoices):
    ATELIER = "atelier", "Atelier"
    CUSTOMER = "customer", "Client"


class Warehouse(BaseModel):
    code = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("code",)
        permissions = [
            ("manage_warehouse", "Can manage warehouse zones and locations"),
        ]

    def __str__(self) -> str:
        return self.name


class WarehouseZone(BaseModel):
    class Kind(models.TextChoices):
        BLANKS = "blanks", "Vierges POD"
        FINISHED = "finished", "Produits finis"
        RETURNS = "returns", "Retours"
        PRODUCTION = "production", "Staging production"
        CLIENT = "client", "Stock client"

    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="zones")
    code = models.SlugField(max_length=32)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=32, choices=Kind.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("warehouse_id", "code")
        constraints = [
            models.UniqueConstraint(
                fields=("warehouse", "code"),
                name="inventory_warehouse_zone_code_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("warehouse", "kind", "is_active")),
        ]

    def __str__(self) -> str:
        return f"{self.warehouse.code}/{self.code}"


class StorageLocation(BaseModel):
    zone = models.ForeignKey(WarehouseZone, on_delete=models.PROTECT, related_name="locations")
    code = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("code",)
        indexes = [
            models.Index(fields=("zone", "is_active")),
            models.Index(fields=("is_active", "code")),
        ]

    def __str__(self) -> str:
        return self.code


class ProductLocationRule(BaseModel):
    sku_kind = models.CharField(max_length=16, choices=SkuKind.choices)
    blank_variant = models.ForeignKey(
        BlankVariant,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="location_rules",
    )
    finished_sku = models.CharField(max_length=80, blank=True, default="")
    owner_kind = models.CharField(
        max_length=16,
        choices=StockOwnerKind.choices,
        default=StockOwnerKind.ATELIER,
    )
    customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="product_location_rules",
    )
    location = models.ForeignKey(
        StorageLocation,
        on_delete=models.PROTECT,
        related_name="product_rules",
    )

    class Meta:
        ordering = ("sku_kind", "finished_sku")
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "sku_kind",
                    "blank_variant",
                    "finished_sku",
                    "owner_kind",
                    "customer",
                ),
                name="inventory_product_location_rule_uniq",
                nulls_distinct=False,
            ),
        ]
        indexes = [
            models.Index(fields=("sku_kind", "owner_kind")),
        ]

    def __str__(self) -> str:
        return f"{self.sku_kind}→{self.location.code}"


class StockBalance(BaseModel):
    sku_kind = models.CharField(max_length=16, choices=SkuKind.choices)
    blank_variant = models.ForeignKey(
        BlankVariant,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="stock_balances",
    )
    finished_sku = models.CharField(max_length=80, blank=True, default="")
    location = models.ForeignKey(
        StorageLocation,
        on_delete=models.PROTECT,
        related_name="stock_balances",
    )
    owner_kind = models.CharField(
        max_length=16,
        choices=StockOwnerKind.choices,
        default=StockOwnerKind.ATELIER,
    )
    customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="stock_balances",
    )
    qty_on_hand = models.PositiveIntegerField(default=0)
    qty_reserved = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("location__code",)
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "sku_kind",
                    "blank_variant",
                    "finished_sku",
                    "location",
                    "owner_kind",
                    "customer",
                ),
                name="inventory_stock_balance_uniq",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=models.Q(qty_reserved__lte=models.F("qty_on_hand")),
                name="inventory_stock_reserved_lte_on_hand",
            ),
        ]
        indexes = [
            models.Index(fields=("sku_kind", "owner_kind", "location")),
        ]

    @property
    def qty_available(self) -> int:
        return max(self.qty_on_hand - self.qty_reserved, 0)


class StockMovement(BaseModel):
    class Kind(models.TextChoices):
        RECEIPT = "receipt", "Réception"
        PICK = "pick", "Picking"
        PUTAWAY = "putaway", "Rangement"
        TRANSFER = "transfer", "Transfert"
        ADJUSTMENT = "adjustment", "Ajustement"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    sku_kind = models.CharField(max_length=16, choices=SkuKind.choices)
    blank_variant = models.ForeignKey(
        BlankVariant,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    finished_sku = models.CharField(max_length=80, blank=True, default="")
    from_location = models.ForeignKey(
        StorageLocation,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="outbound_movements",
    )
    to_location = models.ForeignKey(
        StorageLocation,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="inbound_movements",
    )
    owner_kind = models.CharField(
        max_length=16,
        choices=StockOwnerKind.choices,
        default=StockOwnerKind.ATELIER,
    )
    quantity = models.PositiveIntegerField()
    scanned_bin_code = models.CharField(max_length=64, blank=True, default="")
    note = models.CharField(max_length=255, blank=True, default="")
    actor = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stock_movements",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("kind", "created_at")),
        ]
