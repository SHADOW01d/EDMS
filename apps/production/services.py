from decimal import Decimal
import uuid

from django.db import transaction
from django.utils import timezone

from apps.inventory.models import Product, StockLocation
from apps.inventory.services import post_movement
from .models import ProductionBatch, ProductionConsumption, ProductionOutput


def production_product_family(product):
    name = product.name.casefold()
    sku = product.sku.casefold()
    if "full package" in name or sku == "ed-pk-full":
        return "full_package"
    if "effective diet" in name:
        return "effective_diet"
    if "presha masala" in name or "pressure masala" in name:
        return "pressure_masala"
    if "asali" in name or "honey" in name:
        return "honey"
    return None


def is_manufactured_product(product):
    return production_product_family(product) in {
        "effective_diet",
        "pressure_masala",
        "honey",
    }


def is_full_package_product(product):
    return production_product_family(product) == "full_package"


def full_package_components():
    sku_by_family = {
        "effective_diet": "ED-SINGLE",
        "pressure_masala": "PRESHA-SINGLE",
        "honey": "HONEY-SINGLE",
    }
    products = []
    for family, sku in sku_by_family.items():
        product = Product.objects.filter(
            sku__iexact=sku,
            category=Product.Category.FINISHED_GOOD,
            active=True,
        ).first()
        if not product or production_product_family(product) != family:
            raise ValueError(
                f"Set up an active single-item product for {family.replace('_', ' ')}."
            )
        products.append(product)
    return products


def _is_honey_raw_material(product):
    name = product.name.casefold()
    return product.category == Product.Category.RAW_MATERIAL and (
        "asali" in name or "honey" in name
    )


def _is_honey_jar_packaging(product):
    name = product.name.casefold()
    return (
        product.category == Product.Category.PACKAGING
        and ("asali" in name or "honey" in name)
        and ("kopo" in name or "jar" in name or "can" in name)
    )


@transaction.atomic
def complete_production_output(
    *,
    batch,
    product,
    quantity,
    consumptions,
    created_by,
    production_date=None,
    request_key=None,
):
    request_key = request_key or uuid.uuid4()
    duplicate = ProductionOutput.objects.filter(request_key=request_key).first()
    if duplicate:
        if (
            duplicate.batch_id == batch.pk
            and duplicate.product_id == product.pk
            and duplicate.quantity == Decimal(str(quantity))
        ):
            return duplicate
        raise ValueError("This production submission key was already used.")

    batch = ProductionBatch.objects.select_for_update().get(pk=batch.pk)
    if batch.status != ProductionBatch.Status.ACTIVE:
        raise ValueError("Production can only be recorded in an active, approved batch.")
    if product.category != Product.Category.FINISHED_GOOD or not is_manufactured_product(product):
        raise ValueError("Only Effective Diet, Presha Masala, and Wild Honey can be produced.")
    quantity = Decimal(str(quantity))
    if quantity <= 0:
        raise ValueError("Production quantity must be greater than zero.")

    family = production_product_family(product)
    if family == "honey":
        if not any(_is_honey_raw_material(material) for material, _ in consumptions):
            raise ValueError("Select Asali mbichi and enter the drums used.")
        if not any(_is_honey_jar_packaging(material) for material, _ in consumptions):
            raise ValueError("Select Kopo za Asali and enter the jars used.")
    elif not consumptions:
        raise ValueError("Record at least one raw material or packaging consumption.")

    if not consumptions:
        raise ValueError("Record at least one raw material or packaging consumption.")

    reference = f"OUT-{batch.pk}-{uuid.uuid4().hex.upper()}"
    output = ProductionOutput.objects.create(
        batch=batch,
        product=product,
        quantity=quantity,
        production_date=production_date or timezone.localdate(),
        reference=reference,
        request_key=request_key,
        created_by=created_by,
    )
    factory = StockLocation.objects.select_for_update().get(
        location_type=StockLocation.LocationType.FACTORY,
    )
    for material, consumed_quantity in consumptions:
        consumed_quantity = Decimal(str(consumed_quantity))
        if material.category not in (Product.Category.RAW_MATERIAL, Product.Category.PACKAGING):
            raise ValueError("Production can consume only raw materials and packaging.")
        if consumed_quantity <= 0:
            raise ValueError("Consumption quantities must be greater than zero.")
        ProductionConsumption.objects.create(
            batch=batch,
            output=output,
            product=material,
            quantity=consumed_quantity,
            unit=material.unit,
            reference=output.reference,
        )
        post_movement(
            product=material,
            location=factory,
            movement="PRODUCTION_OUT",
            quantity=-consumed_quantity,
            reference=output.reference,
            production_batch=batch,
        )
    post_movement(
        product=product,
        location=factory,
        movement="PRODUCTION_IN",
        quantity=quantity,
        reference=output.reference,
        production_batch=batch,
    )
    batch.quantity = (batch.quantity or Decimal("0")) + quantity
    batch.save(update_fields=["quantity"])
    return output


@transaction.atomic
def complete_batch(batch):
    if batch.status != ProductionBatch.Status.PLANNED:
        raise ValueError("Only planned batches can be completed")
    factory = StockLocation.objects.get(location_type=StockLocation.LocationType.FACTORY)
    consumptions = list(batch.consumptions.select_related("product").select_for_update())
    if not consumptions:
        scale = Decimal(str(batch.quantity)) / batch.recipe.yield_quantity
        for item in batch.recipe.items.select_related("material").select_for_update():
            required = Decimal(str(item.quantity)) * scale
            consumption = ProductionConsumption.objects.create(
                batch=batch,
                product=item.material,
                quantity=required,
                unit=item.material.unit,
                reference=batch.reference,
            )
            consumptions.append(consumption)
    for consumption in consumptions:
        post_movement(
            product=consumption.product,
            location=factory,
            movement="PRODUCTION_OUT",
            quantity=-Decimal(str(consumption.quantity)),
            reference=batch.reference,
            production_batch=batch,
        )
    post_movement(
        product=batch.recipe.product,
        location=factory,
        movement="PRODUCTION_IN",
        quantity=batch.quantity,
        reference=batch.reference,
        production_batch=batch,
    )
    batch.status = ProductionBatch.Status.COMPLETED
    batch.save(update_fields=["status"])
    return batch
