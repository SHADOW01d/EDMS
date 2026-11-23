from decimal import Decimal

from django.db import transaction

from apps.inventory.models import StockLocation
from apps.inventory.services import post_movement
from .models import ProductionBatch, ProductionConsumption


@transaction.atomic
def complete_batch(batch):
    if batch.status != ProductionBatch.Status.PLANNED:
        raise ValueError("Only planned batches can be completed")
    factory = StockLocation.objects.get(location_type=StockLocation.LocationType.FACTORY)
    scale = Decimal(str(batch.quantity)) / batch.recipe.yield_quantity
    for item in batch.recipe.items.select_related("material"):
        required = Decimal(str(item.quantity)) * scale
        ProductionConsumption.objects.update_or_create(
            batch=batch,
            product=item.material,
            defaults={
                "quantity": required,
                "unit": item.material.unit,
                "reference": batch.reference,
            },
        )
        post_movement(
            product=item.material,
            location=factory,
            movement="PRODUCTION_OUT",
            quantity=-required,
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
