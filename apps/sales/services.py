from decimal import Decimal

from django.db import transaction

from apps.inventory.services import post_movement
from .models import Sale


@transaction.atomic
def confirm_sale(sale):
    for item in sale.items.select_related("product", "batch"):
        post_movement(
            product=item.product,
            location=sale.location,
            movement="SALE",
            quantity=-Decimal(str(item.quantity)),
            reference=sale.reference,
            production_batch=item.batch,
        )
    return sale
