from django.db import migrations


def set_honey_production_units(apps, schema_editor):
    Product = apps.get_model("inventory", "Product")
    InventoryLedger = apps.get_model("inventory", "InventoryLedger")
    PurchaseItem = apps.get_model("procurement", "PurchaseItem")
    SaleItem = apps.get_model("sales", "SaleItem")

    raw_honey = Product.objects.filter(sku="RAW-RAW-HONEY").first()
    if raw_honey and raw_honey.unit.casefold() in {"litre", "liter", "lita"}:
        has_stock_history = InventoryLedger.objects.filter(product_id=raw_honey.pk).exists()
        has_purchase_history = PurchaseItem.objects.filter(product_id=raw_honey.pk).exists()
        if not has_stock_history and not has_purchase_history:
            raw_honey.unit = "madumu"
            raw_honey.save(update_fields=["unit"])

    honey_jars = Product.objects.filter(sku="HONEY-SINGLE").first()
    if honey_jars and honey_jars.unit.casefold() in {"litre", "liter", "lita"}:
        has_stock_history = InventoryLedger.objects.filter(product_id=honey_jars.pk).exists()
        has_sale_history = SaleItem.objects.filter(product_id=honey_jars.pk).exists()
        if not has_stock_history and not has_sale_history:
            honey_jars.unit = "vikopo"
            honey_jars.save(update_fields=["unit"])


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0004_seed_initial_catalog"),
        ("procurement", "0005_link_batch_purchases_to_inventory"),
        ("sales", "0003_sale_request_key"),
    ]

    operations = [
        migrations.RunPython(set_honey_production_units, migrations.RunPython.noop),
    ]
