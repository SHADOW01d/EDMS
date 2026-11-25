from decimal import Decimal

from django.db import transaction

from apps.inventory.services import post_movement
from apps.production.services import full_package_components, is_full_package_product
from .models import Sale


@transaction.atomic
def confirm_sale(sale):
    for item in sale.items.select_related("product", "batch"):
        sale_products = (
            full_package_components()
            if is_full_package_product(item.product)
            else (item.product,)
        )
        for product in sale_products:
            post_movement(
                product=product,
                location=sale.location,
                movement="SALE",
                quantity=-Decimal(str(item.quantity)),
                reference=sale.reference,
                production_batch=item.batch,
            )
    return sale
