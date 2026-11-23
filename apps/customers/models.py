from django.conf import settings
from django.db import models

from apps.inventory.models import StockLocation


class Customer(models.Model):
    name = models.CharField(max_length=150)
    location = models.ForeignKey(
        StockLocation,
        on_delete=models.PROTECT,
        related_name="customers",
        null=True,
        blank=True,
    )
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class CustomerCall(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="calls")
    called_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    called_at = models.DateTimeField(auto_now_add=True)
    outcome = models.CharField(max_length=100)
    notes = models.TextField(blank=True)
    follow_up_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("-called_at",)


class BranchExpense(models.Model):
    location = models.CharField(max_length=20)
    category = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)
    expense_date = models.DateField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    batch = models.ForeignKey(
        "production.ProductionBatch",
        on_delete=models.PROTECT,
        related_name="expenses",
        null=True,
        blank=True,
    )
    recorded_at = models.DateTimeField(auto_now_add=True)


class BranchDailyReport(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"

    location = models.CharField(max_length=20)
    report_date = models.DateField()
    units_sold = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    closing_balance = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    loss_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    total_customers = models.PositiveIntegerField(default=0)
    new_customers = models.PositiveIntegerField(default=0)
    returning_customers = models.PositiveIntegerField(default=0)
    visitors = models.PositiveIntegerField(default=0)
    deliveries = models.PositiveIntegerField(default=0)
    parcels = models.PositiveIntegerField(default=0)
    instruction_calls = models.PositiveIntegerField(default=0)
    compliance_calls = models.PositiveIntegerField(default=0)
    followup_calls = models.PositiveIntegerField(default=0)
    customer_addresses = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_branch_reports",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    batch = models.ForeignKey(
        "production.ProductionBatch",
        on_delete=models.PROTECT,
        related_name="daily_reports",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-report_date", "-created_at")
        unique_together = ("location", "report_date")
