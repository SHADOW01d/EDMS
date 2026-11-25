from decimal import Decimal

from django.db import migrations


CATALOG = [
    ("Effective Diet Full Package", "ED-PK-FULL", "FINISHED_GOOD", "pcs", "100000"),
    ("Effective Diet Pekee", "ED-SINGLE", "FINISHED_GOOD", "pcs", "65000"),
    ("Presha Masala Pekee", "PRESHA-SINGLE", "FINISHED_GOOD", "pcs", "25000"),
    ("Wild Honey / Asali Pekee", "HONEY-SINGLE", "FINISHED_GOOD", "litre", "15000"),
    ("Soya lishe", "RAW-SOYA", "RAW_MATERIAL", "kg", "0"),
    ("Hiliki", "RAW-HILIKI", "RAW_MATERIAL", "kg", "0"),
    ("Karanga", "RAW-KARANGA", "RAW_MATERIAL", "kg", "0"),
    ("Mbegu za maboga", "RAW-PUMPKIN-SEEDS", "RAW_MATERIAL", "kg", "0"),
    ("Tangawizi", "RAW-GINGER", "RAW_MATERIAL", "kg", "0"),
    ("Pilipili manga", "RAW-BLACK-PEPPER", "RAW_MATERIAL", "kg", "0"),
    ("Karafu", "RAW-CLOVE", "RAW_MATERIAL", "kg", "0"),
    ("Mdarasini", "RAW-CINNAMON", "RAW_MATERIAL", "kg", "0"),
    ("Asali mbichi", "RAW-RAW-HONEY", "RAW_MATERIAL", "litre", "0"),
    ("Mifuko ya Effective Diet", "PKG-ED-BAGS", "PACKAGING", "pcs", "0"),
    ("Kopo za Presha Masala", "PKG-PRESHA-CANS", "PACKAGING", "pcs", "0"),
    ("Kopo za Asali", "PKG-HONEY-CANS", "PACKAGING", "pcs", "0"),
    ("Sticker za Asali", "PKG-HONEY-STICKERS", "PACKAGING", "pcs", "0"),
    ("Seal za Asali", "PKG-HONEY-SEALS", "PACKAGING", "pcs", "0"),
    ("Sticker za Presha Masala", "PKG-PRESHA-STICKERS", "PACKAGING", "pcs", "0"),
    ("Seal za Presha Masala", "PKG-PRESHA-SEALS", "PACKAGING", "pcs", "0"),
]


def seed_catalog(apps, schema_editor):
    Product = apps.get_model("inventory", "Product")
    for name, sku, category, unit, price in CATALOG:
        Product.objects.update_or_create(
            sku=sku,
            defaults={
                "name": name,
                "category": category,
                "unit": unit,
                "unit_price": Decimal(price),
                "active": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0003_inventoryledger_production_batch"),
    ]

    operations = [
        migrations.RunPython(seed_catalog, migrations.RunPython.noop),
    ]
