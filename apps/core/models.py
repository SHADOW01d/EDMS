from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    class Category(models.TextChoices):
        AUTHENTICATION = "AUTHENTICATION", "Authentication"
        ACCOUNT = "ACCOUNT", "Account"
        PROCUREMENT = "PROCUREMENT", "Procurement"
        INVENTORY = "INVENTORY", "Inventory"
        PRODUCTION = "PRODUCTION", "Production"
        DISTRIBUTION = "DISTRIBUTION", "Distribution"
        SALES = "SALES", "Sales"
        CUSTOMER = "CUSTOMER", "Customer"
        REPORT = "REPORT", "Report"
        SECURITY = "SECURITY", "Security"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    category = models.CharField(max_length=20, choices=Category.choices)
    action = models.CharField(max_length=100)
    object_type = models.CharField(max_length=120, blank=True)
    object_id = models.CharField(max_length=120, blank=True)
    previous_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    request_path = models.CharField(max_length=500, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-timestamp",)
        indexes = [
            models.Index(fields=("category", "timestamp"), name="core_audit_cat_ts"),
            models.Index(fields=("action", "timestamp"), name="core_audit_act_ts"),
        ]

    def __str__(self):
        return f"{self.timestamp.isoformat()} {self.action}"
