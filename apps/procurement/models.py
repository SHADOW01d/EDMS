from django.db import models
from django.conf import settings

from apps.inventory.models import Product


class Supplier(models.Model):
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Purchase(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        RECEIVED = "RECEIVED", "Received"
        CANCELLED = "CANCELLED", "Cancelled"

    reference = models.CharField(max_length=60, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    purchase_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    actual_payment = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    calculated_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-purchase_date", "-created_at")


class PurchaseItem(models.Model):
    class PricingUnit(models.TextChoices):
        PIECE = "PIECE", "Piece"
        KG = "KG", "Kilogram"

    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    pricing_unit = models.CharField(
        max_length=10,
        choices=PricingUnit.choices,
        default=PricingUnit.PIECE,
    )
