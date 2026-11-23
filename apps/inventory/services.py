from decimal import Decimal

from django.db import transaction

from .models import InventoryLedger, stock_balance


def post_movement(
    *,
    product,
    location,
    movement,
    quantity,
    reference="",
    notes="",
    production_batch=None,
):
    quantity = Decimal(str(quantity))
    from .models import Product
    batch_for_balance = (
        production_batch
        if product.category == Product.Category.FINISHED_GOOD
        else None
    )
    available = Decimal(str(stock_balance(product, location, batch_for_balance)))
    balance = available + quantity
    if balance < 0:
        requested = abs(quantity)
        available_text = format(available.normalize(), "f")
        requested_text = format(requested.normalize(), "f")
        raise ValueError(
            f"Stock haitoshi: {product.name} ipo {available_text} {product.unit} "
            f"kwenye {location.name}; umeomba {requested_text} {product.unit}. "
            "Pokea au zalisha stock kwanza."
        )
    return InventoryLedger.objects.create(
        product=product,
        location=location,
        movement=movement,
        quantity=quantity,
        balance_after=balance,
        reference=reference,
        notes=notes,
        production_batch=production_batch,
    )
