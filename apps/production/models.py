from django.conf import settings
from django.db import models

from apps.inventory.models import Product


class Recipe(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="recipe")
    yield_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)


class RecipeItem(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="items")
    material = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)


class ProductionBatch(models.Model):
    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    reference = models.CharField(max_length=60, unique=True)
    recipe = models.ForeignKey(Recipe, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    production_date = models.DateField()
    batch_number = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-production_date", "-created_at")


class ProductionConsumption(models.Model):
    batch = models.ForeignKey(
        ProductionBatch,
        on_delete=models.PROTECT,
        related_name="consumptions",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="production_consumptions",
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit = models.CharField(max_length=30)
    reference = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
