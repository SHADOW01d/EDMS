from django.conf import settings
from django.db import models

from apps.inventory.models import Product, StockLocation


class Sale(models.Model):
    reference = models.CharField(max_length=60, unique=True)
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT)
    customer = models.ForeignKey("customers.Customer", on_delete=models.SET_NULL, null=True, blank=True)
    sold_at = models.DateTimeField(auto_now_add=True)
    sold_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ("-sold_at",)


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    batch = models.ForeignKey(
        "production.ProductionBatch",
        on_delete=models.PROTECT,
        related_name="sale_items",
        null=True,
        blank=True,
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
