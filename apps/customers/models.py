from django.conf import settings
from django.db import models
from django.utils import timezone

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
    diagnosis = models.CharField(max_length=255, blank=True)
    short_description = models.TextField(blank=True)
    address = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class CustomerVisit(models.Model):
    class VisitType(models.TextChoices):
        NEW_CUSTOMER = "NEW_CUSTOMER", "Mteja mpya"
        RETURNING_CUSTOMER = "RETURNING_CUSTOMER", "Mteja aliyerudi"
        CUSTOMER_INQUIRY = "CUSTOMER_INQUIRY", "Ameulizia bidhaa/huduma"
        MANAGEMENT_GUEST = "MANAGEMENT_GUEST", "Mgeni wa menejimenti/CEO"
        GOVERNMENT_OFFICIAL = "GOVERNMENT_OFFICIAL", "Afisa wa serikali"
        OTHER = "OTHER", "Mgeni mwingine"

    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        related_name="visits",
        null=True,
        blank=True,
    )
    location = models.ForeignKey(
        StockLocation,
        on_delete=models.PROTECT,
        related_name="customer_visits",
    )
    visit_type = models.CharField(max_length=24, choices=VisitType.choices)
    visitor_name = models.CharField(max_length=150)
    visitor_phone = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)
    visited_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        ordering = ("-visited_at",)
        indexes = [
            models.Index(fields=("location", "visited_at"), name="custvisit_loc_date_idx"),
            models.Index(fields=("location", "visitor_phone"), name="custvisit_loc_phone_idx"),
        ]

    @property
    def contact_name(self):
        return self.customer.name if self.customer_id else self.visitor_name


class BranchDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Inasubiri"
        DISPATCHED = "DISPATCHED", "Imetumwa"
        DELIVERED = "DELIVERED", "Imefikishwa"
        FAILED = "FAILED", "Imeshindikana"

    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        related_name="deliveries",
        null=True,
        blank=True,
    )
    location = models.ForeignKey(
        StockLocation,
        on_delete=models.PROTECT,
        related_name="branch_deliveries",
    )
    recipient_name = models.CharField(max_length=150)
    recipient_phone = models.CharField(max_length=30, blank=True)
    destination = models.CharField(max_length=255)
    parcel_count = models.PositiveIntegerField(default=1)
    delivery_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-delivery_date", "-created_at")
        indexes = [
            models.Index(fields=("location", "delivery_date"), name="delivery_loc_date_idx"),
            models.Index(fields=("location", "status"), name="delivery_loc_status_idx"),
        ]


class CustomerCall(models.Model):
    class Direction(models.TextChoices):
        UNKNOWN = "UNKNOWN", "Haikubainishwa"
        INBOUND = "INBOUND", "Tumepigiwa na mteja"
        OUTBOUND = "OUTBOUND", "Tumempigia mteja"

    class CallType(models.TextChoices):
        INSTRUCTION = "INSTRUCTION", "Simu ya maelekezo"
        COMPLIANCE = "COMPLIANCE", "Simu ya kufuatilia utekelezaji"
        FOLLOW_UP = "FOLLOW_UP", "Simu ya ufuatiliaji"

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="calls",
        null=True,
        blank=True,
    )
    location = models.ForeignKey(
        StockLocation,
        on_delete=models.PROTECT,
        related_name="customer_calls",
        null=True,
        blank=True,
    )
    called_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    called_at = models.DateTimeField(auto_now_add=True)
    direction = models.CharField(
        max_length=10,
        choices=Direction.choices,
        default=Direction.UNKNOWN,
    )
    call_type = models.CharField(max_length=20, choices=CallType.choices, blank=True)
    caller_name = models.CharField(max_length=150, blank=True)
    caller_phone = models.CharField(max_length=30, blank=True)
    outcome = models.CharField(max_length=100)
    notes = models.TextField(blank=True)
    follow_up_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("-called_at",)

    @property
    def contact_name(self):
        return self.caller_name or (self.customer.name if self.customer else "")

    @property
    def branch_location(self):
        return self.location or (self.customer.location if self.customer else None)


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
        constraints = [
            models.UniqueConstraint(
                fields=("location", "report_date"),
                condition=models.Q(batch__isnull=True),
                name="unique_unbatched_branch_daily_report",
            ),
            models.UniqueConstraint(
                fields=("location", "report_date", "batch"),
                condition=models.Q(batch__isnull=False),
                name="unique_batched_branch_daily_report",
            ),
        ]
