import uuid

from django.db import migrations, models


def assign_request_keys(apps, schema_editor):
    Sale = apps.get_model("sales", "Sale")
    for sale in Sale.objects.all().iterator():
        Sale.objects.filter(pk=sale.pk).update(request_key=uuid.uuid4())


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0002_saleitem_batch"),
    ]

    operations = [
        migrations.AddField(
            model_name="sale",
            name="request_key",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(assign_request_keys, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="sale",
            name="request_key",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
