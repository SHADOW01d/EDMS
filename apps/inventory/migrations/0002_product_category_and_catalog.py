from django.db import migrations, models
from decimal import Decimal


def seed_catalog(apps, schema_editor):
    Product = apps.get_model("inventory", "Product")

    catalog = [
        ("Effective Diet", "ED-PK-FULL", "FINISHED_GOOD", "package", "100000"),
        ("Effective Diet Pekee", "ED-SINGLE", "FINISHED_GOOD", "package", "65000"),
        ("Presha Masala Pekee", "PRESHA-SINGLE", "FINISHED_GOOD", "package", "25000"),
        ("Wild Honey / Asali Pekee", "HONEY-SINGLE", "FINISHED_GOOD", "package", "15000"),
        ("Soya lishe", "RAW-SOYA", "RAW_MATERIAL", "kg", "0"),
        ("Hiliki", "RAW-HILIKI", "RAW_MATERIAL", "kg", "0"),
        ("Karanga", "RAW-KARANGA", "RAW_MATERIAL", "kg", "0"),
        ("Mbegu za maboga", "RAW-PUMPKIN-SEEDS", "RAW_MATERIAL", "kg", "0"),
        ("Tangawizi", "RAW-GINGER", "RAW_MATERIAL", "kg", "0"),
        ("Pilipili manga", "RAW-BLACK-PEPPER", "RAW_MATERIAL", "kg", "0"),
        ("Karafu", "RAW-CLOVE", "RAW_MATERIAL", "kg", "0"),
        ("Mdarasini", "RAW-CINNAMON", "RAW_MATERIAL", "kg", "0"),
        ("Asali mbichi", "RAW-RAW-HONEY", "RAW_MATERIAL", "lita", "0"),
        ("Mifuko ya Effective Diet", "PKG-ED-BAGS", "PACKAGING", "pcs", "0"),
        ("Kopo za Presha Masala", "PKG-PRESHA-CANS", "PACKAGING", "pcs", "0"),
        ("Kopo za Asali", "PKG-HONEY-CANS", "PACKAGING", "pcs", "0"),
        ("Sticker za Asali", "PKG-HONEY-STICKERS", "PACKAGING", "pcs", "0"),
        ("Seal za Asali", "PKG-HONEY-SEALS", "PACKAGING", "pcs", "0"),
        ("Sticker za Presha Masala", "PKG-PRESHA-STICKERS", "PACKAGING", "pcs", "0"),
        ("Seal za Presha Masala", "PKG-PRESHA-SEALS", "PACKAGING", "pcs", "0"),
    ]

    for name, sku, category, unit, unit_price in catalog:
        Product.objects.update_or_create(
            sku=sku,
            defaults={
                "name": name,
                "category": category,
                "unit": unit,
                "unit_price": Decimal(unit_price),
                "active": True,
            },
        )


def unseed_catalog(apps, schema_editor):
    Product = apps.get_model("inventory", "Product")
    skus = [
        "ED-PK-FULL", "ED-SINGLE", "PRESHA-SINGLE", "HONEY-SINGLE",
        "RAW-SOYA", "RAW-HILIKI", "RAW-KARANGA", "RAW-PUMPKIN-SEEDS",
        "RAW-GINGER", "RAW-BLACK-PEPPER", "RAW-CLOVE", "RAW-CINNAMON",
        "RAW-RAW-HONEY", "PKG-ED-BAGS", "PKG-PRESHA-CANS",
        "PKG-HONEY-CANS", "PKG-HONEY-STICKERS", "PKG-HONEY-SEALS",
        "PKG-PRESHA-STICKERS", "PKG-PRESHA-SEALS",
    ]
    Product.objects.filter(sku__in=skus).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="category",
            field=models.CharField(
                choices=[
                    ("FINISHED_GOOD", "Finished good"),
                    ("RAW_MATERIAL", "Raw material"),
                    ("PACKAGING", "Packaging"),
                ],
                default="FINISHED_GOOD",
                max_length=20,
            ),
        ),
        migrations.RunPython(seed_catalog, unseed_catalog),
    ]
