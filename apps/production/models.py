from django.conf import settings
from django.db import models
from django.utils import timezone
import uuid

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
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending CEO approval"
        ACTIVE = "ACTIVE", "Active"
        REJECTED = "REJECTED", "Rejected"
        CLOSED = "CLOSED", "Closed"
        PLANNED = "PLANNED", "Planned"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    reference = models.CharField(max_length=60, unique=True)
    recipe = models.ForeignKey(Recipe, on_delete=models.PROTECT, null=True, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    production_date = models.DateField()
    batch_number = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_production_batches",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    request_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-production_date", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=["recipe", "batch_number"],
                name="unique_recipe_batch_number",
            )
        ]


class ProductionOutput(models.Model):
    batch = models.ForeignKey(
        ProductionBatch,
        on_delete=models.PROTECT,
        related_name="outputs",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="production_outputs",
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    production_date = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=60, unique=True)
    request_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
    output = models.ForeignKey(
        ProductionOutput,
        on_delete=models.PROTECT,
        related_name="consumptions",
        null=True,
        blank=True,
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
