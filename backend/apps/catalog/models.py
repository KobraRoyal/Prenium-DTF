from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import BaseModel

ZERO_AMOUNT = Decimal("0.00")


class CatalogServiceQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class CatalogService(BaseModel):
    class ServiceType(models.TextChoices):
        DTF_TRANSFER = "dtf_transfer", "DTF au metre"
        FILE_PREPARATION = "file_preparation", "Preparation de fichier"

    class Unit(models.TextChoices):
        LINEAR_METER = "linear_meter", "Metre lineaire"
        FIXED = "fixed", "Forfait"

    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    service_type = models.CharField(max_length=32, choices=ServiceType.choices)
    unit = models.CharField(max_length=32, choices=Unit.choices)
    base_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(ZERO_AMOUNT)],
    )
    currency = models.CharField(max_length=3, default="EUR")
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    objects = CatalogServiceQuerySet.as_manager()

    class Meta:
        ordering = ("display_order", "name")
        indexes = [
            models.Index(fields=("is_active", "display_order")),
            models.Index(fields=("service_type", "is_active")),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def allows_variable_quantity(self) -> bool:
        return self.unit == self.Unit.LINEAR_METER

