from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.inventory.models import InventoryLedger, StockLocation
from apps.inventory.services import post_movement
from .models import Transfer


@transaction.atomic
def dispatch_transfer(transfer):
    transfer = Transfer.objects.select_for_update().get(pk=transfer.pk)
    if transfer.status != Transfer.Status.DISPATCHED:
        raise ValueError("Transfer is not in dispatched state")
    factory = StockLocation.objects.get(location_type=StockLocation.LocationType.FACTORY)
    items = list(transfer.items.select_related("product"))
    if not items:
        raise ValueError("Transfer has no items")

    existing_movements = InventoryLedger.objects.filter(
        reference=transfer.reference,
        location=factory,
        movement=InventoryLedger.Movement.TRANSFER_OUT,
    )
    if existing_movements.exists():
        expected_outgoing = {}
        for item in items:
            key = (item.product_id, item.batch_id)
            expected_outgoing[key] = (
                expected_outgoing.get(key, Decimal("0"))
                - item.quantity_sent
            )
        posted_outgoing = {
            (row["product_id"], row["production_batch_id"]): row["total"]
            for row in existing_movements.values(
                "product_id",
                "production_batch_id",
            ).annotate(total=Sum("quantity"))
        }
        if posted_outgoing != expected_outgoing:
            raise ValueError("Transfer has incomplete or inconsistent stock deductions")
        return transfer

    for item in items:
        post_movement(
            product=item.product,
            location=factory,
            movement=InventoryLedger.Movement.TRANSFER_OUT,
            quantity=-item.quantity_sent,
            reference=transfer.reference,
            production_batch=item.batch,
        )
    return transfer


@transaction.atomic
def receive_transfer(transfer, quantities=None):
    transfer = Transfer.objects.select_for_update().get(pk=transfer.pk)
    if transfer.status in (Transfer.Status.RECEIVED, Transfer.Status.CANCELLED):
        raise ValueError("Transfer cannot be received")
    factory = StockLocation.objects.get(location_type=StockLocation.LocationType.FACTORY)
    items = list(transfer.items.select_related("product"))
    expected_outgoing = {}
    for item in items:
        key = (item.product_id, item.batch_id)
        expected_outgoing[key] = (
            expected_outgoing.get(key, Decimal("0"))
            - item.quantity_sent
        )
    posted_outgoing = {
        (row["product_id"], row["production_batch_id"]): row["total"]
        for row in InventoryLedger.objects.filter(
            reference=transfer.reference,
            location=factory,
            movement=InventoryLedger.Movement.TRANSFER_OUT,
        ).values("product_id", "production_batch_id").annotate(total=Sum("quantity"))
    }
    if not items or posted_outgoing != expected_outgoing:
        raise ValueError("Transfer must be dispatched from store before it can be received")

    received_all = True
    for item in items:
        received = item.quantity_sent if quantities is None else Decimal(str(quantities.get(str(item.pk), item.quantity_sent)))
        if received < item.quantity_received or received > item.quantity_sent:
            raise ValueError("Received quantity is invalid")
        newly_received = received - item.quantity_received
        item.quantity_received = received
        item.save(update_fields=["quantity_received"])
        if newly_received:
            post_movement(
                product=item.product,
                location=transfer.destination,
                movement="TRANSFER_IN",
                quantity=newly_received,
                reference=transfer.reference,
                production_batch=item.batch,
            )
        if received != item.quantity_sent:
            received_all = False
    transfer.status = Transfer.Status.RECEIVED if received_all else Transfer.Status.PARTIAL
    transfer.received_at = timezone.now()
    transfer.save(update_fields=["status", "received_at"])
    return transfer
