from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(choices=[("AUTHENTICATION", "Authentication"), ("ACCOUNT", "Account"), ("PROCUREMENT", "Procurement"), ("INVENTORY", "Inventory"), ("PRODUCTION", "Production"), ("DISTRIBUTION", "Distribution"), ("SALES", "Sales"), ("CUSTOMER", "Customer"), ("REPORT", "Report"), ("SECURITY", "Security")], max_length=20)),
                ("action", models.CharField(max_length=100)),
                ("object_type", models.CharField(blank=True, max_length=120)),
                ("object_id", models.CharField(blank=True, max_length=120)),
                ("previous_values", models.JSONField(blank=True, default=dict)),
                ("new_values", models.JSONField(blank=True, default=dict)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=500)),
                ("request_path", models.CharField(blank=True, max_length=500)),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="audit_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-timestamp",), "indexes": [models.Index(fields=["category", "timestamp"], name="core_audit_cat_ts"), models.Index(fields=["action", "timestamp"], name="core_audit_act_ts")]},
        ),
    ]
