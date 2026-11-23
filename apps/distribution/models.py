from django.conf import settings
from django.db import models

from apps.inventory.models import Product, StockLocation


class Transfer(models.Model):
    class Status(models.TextChoices):
        DISPATCHED = "DISPATCHED", "Dispatched"
        RECEIVED = "RECEIVED", "Received"
        PARTIAL = "PARTIAL", "Partially received"
        CANCELLED = "CANCELLED", "Cancelled"

    reference = models.CharField(max_length=60, unique=True)
    destination = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name="incoming_transfers")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DISPATCHED)
    dispatched_at = models.DateTimeField(auto_now_add=True)
    received_at = models.DateTimeField(null=True, blank=True)
    dispatched_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        ordering = ("-dispatched_at",)


class TransferItem(models.Model):
    transfer = models.ForeignKey(Transfer, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    batch = models.ForeignKey(
        "production.ProductionBatch",
        on_delete=models.PROTECT,
        related_name="transfer_items",
        null=True,
        blank=True,
    )
    quantity_sent = models.DecimalField(max_digits=12, decimal_places=3)
    quantity_received = models.DecimalField(max_digits=12, decimal_places=3, default=0)
