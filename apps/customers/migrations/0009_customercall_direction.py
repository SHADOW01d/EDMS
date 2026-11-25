from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0008_support_unregistered_callers"),
    ]

    operations = [
        migrations.AddField(
            model_name="customercall",
            name="direction",
            field=models.CharField(
                choices=[
                    ("UNKNOWN", "Haikubainishwa"),
                    ("INBOUND", "Tumepigiwa na mteja"),
                    ("OUTBOUND", "Tumempigia mteja"),
                ],
                default="UNKNOWN",
                max_length=10,
            ),
        ),
    ]
