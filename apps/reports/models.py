from django.conf import settings
from django.db import models


class GeneratedReport(models.Model):
    class ReportType(models.TextChoices):
        DAILY = "DAILY", "Daily"
        WEEKLY = "WEEKLY", "Weekly"
        MONTHLY = "MONTHLY", "Monthly"
        CUSTOM = "CUSTOM", "Custom period"

    class Office(models.TextChoices):
        ALL = "all", "All offices"
        MWANZA = "mwanza", "Mwanza"
        DAR = "dar", "Dar es Salaam"

    report_type = models.CharField(max_length=10, choices=ReportType.choices)
    from_date = models.DateField()
    to_date = models.DateField()
    office = models.CharField(max_length=10, choices=Office.choices)
    file = models.FileField(upload_to="reports/%Y/%m/")
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="generated_reports",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("office", "-created_at"), name="report_office_created_idx"),
        ]

    def __str__(self):
        return f"{self.get_report_type_display()} report ({self.from_date} - {self.to_date})"
