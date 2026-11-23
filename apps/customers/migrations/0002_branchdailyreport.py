from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BranchDailyReport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("location", models.CharField(max_length=20)),
                ("report_date", models.DateField()),
                ("units_sold", models.DecimalField(decimal_places=3, default=0, max_digits=12)),
                ("closing_balance", models.DecimalField(decimal_places=3, default=0, max_digits=12)),
                ("loss_quantity", models.DecimalField(decimal_places=3, default=0, max_digits=12)),
                ("total_customers", models.PositiveIntegerField(default=0)),
                ("new_customers", models.PositiveIntegerField(default=0)),
                ("returning_customers", models.PositiveIntegerField(default=0)),
                ("visitors", models.PositiveIntegerField(default=0)),
                ("deliveries", models.PositiveIntegerField(default=0)),
                ("parcels", models.PositiveIntegerField(default=0)),
                ("instruction_calls", models.PositiveIntegerField(default=0)),
                ("compliance_calls", models.PositiveIntegerField(default=0)),
                ("followup_calls", models.PositiveIntegerField(default=0)),
                ("customer_addresses", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("SUBMITTED", "Submitted"), ("APPROVED", "Approved")], default="SUBMITTED", max_length=20)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="approved_branch_reports", to=settings.AUTH_USER_MODEL)),
                ("submitted_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-report_date", "-created_at"),
                "unique_together": {("location", "report_date")},
            },
        ),
    ]
