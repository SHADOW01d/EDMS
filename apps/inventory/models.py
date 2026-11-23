from django.db import models
from django.db.models import Sum
from django.utils import timezone


class Product(models.Model):
    class Category(models.TextChoices):
        FINISHED_GOOD = "FINISHED_GOOD", "Finished good"
        RAW_MATERIAL = "RAW_MATERIAL", "Raw material"
        PACKAGING = "PACKAGING", "Packaging"

    name = models.CharField(max_length=120)
    sku = models.CharField(max_length=50, unique=True)
    unit = models.CharField(max_length=30, default="unit")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reorder_level = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.FINISHED_GOOD,
    )
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class StockLocation(models.Model):
    class LocationType(models.TextChoices):
        FACTORY = "FACTORY", "Factory"
        BRANCH_MWANZA = "BRANCH_MWANZA", "Mwanza branch"
        BRANCH_DAR = "BRANCH_DAR", "Dar branch"

    name = models.CharField(max_length=100)
    location_type = models.CharField(max_length=20, choices=LocationType.choices, unique=True)

    def __str__(self):
        return self.name


class InventoryLedger(models.Model):
    class Movement(models.TextChoices):
        PURCHASE = "PURCHASE", "Purchase"
        PRODUCTION_IN = "PRODUCTION_IN", "Production input"
        PRODUCTION_OUT = "PRODUCTION_OUT", "Production output"
        TRANSFER_OUT = "TRANSFER_OUT", "Transfer out"
        TRANSFER_IN = "TRANSFER_IN", "Transfer in"
        SALE = "SALE", "Sale"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"
        LOSS = "LOSS", "Loss"

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="ledger_entries")
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name="ledger_entries")
    movement = models.CharField(max_length=20, choices=Movement.choices)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    balance_after = models.DecimalField(max_digits=12, decimal_places=3)
    reference = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    production_batch = models.ForeignKey(
        "production.ProductionBatch",
        on_delete=models.PROTECT,
        related_name="inventory_movements",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.product} {self.quantity} at {self.location}"


def stock_balance(product, location, production_batch=None):
    entries = InventoryLedger.objects.filter(product=product, location=location)
    if production_batch is not None:
        entries = entries.filter(production_batch=production_batch)
    elif production_batch is None:
        pass
    value = entries.aggregate(total=Sum("quantity"))["total"]
    return value or 0
