from django.db import transaction

from apps.inventory.models import StockLocation
from apps.inventory.services import post_movement
from .models import Purchase


@transaction.atomic
def receive_purchase(purchase):
    purchase = Purchase.objects.select_for_update().get(pk=purchase.pk)
    if purchase.status == Purchase.Status.RECEIVED:
        raise ValueError("Purchase has already been received")
    if purchase.status != Purchase.Status.DRAFT:
        raise ValueError("Only draft purchases can be received")
    factory = StockLocation.objects.get(location_type=StockLocation.LocationType.FACTORY)
    items = list(purchase.items.select_related("product"))
    if not items:
        raise ValueError("Purchase has no items")
    for item in items:
        post_movement(
            product=item.product,
            location=factory,
            movement="PURCHASE",
            quantity=item.quantity,
            reference=purchase.reference,
        )
    purchase.status = Purchase.Status.RECEIVED
    purchase.save(update_fields=["status"])
    return purchase
