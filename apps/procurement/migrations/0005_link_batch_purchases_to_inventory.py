from django.db import migrations


def link_batch_purchases_to_inventory(apps, schema_editor):
    Purchase = apps.get_model("procurement", "Purchase")
    InventoryLedger = apps.get_model("inventory", "InventoryLedger")
    for purchase in Purchase.objects.exclude(batch_id=None).only("reference", "batch_id").iterator():
        InventoryLedger.objects.filter(
            reference=purchase.reference,
            movement="PURCHASE",
            production_batch__isnull=True,
        ).update(production_batch_id=purchase.batch_id)


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0003_inventoryledger_production_batch"),
        ("procurement", "0004_purchase_batch"),
    ]

    operations = [
        migrations.RunPython(
            link_batch_purchases_to_inventory,
            migrations.RunPython.noop,
        ),
    ]
