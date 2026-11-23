from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.inventory.models import InventoryLedger, Product, StockLocation, stock_balance
from apps.inventory.services import post_movement
from apps.procurement.models import Purchase, PurchaseItem, Supplier
from apps.procurement.services import receive_purchase
from apps.production.models import ProductionBatch, Recipe
from apps.production.services import complete_batch
from apps.distribution.models import Transfer, TransferItem
from apps.distribution.services import dispatch_transfer, receive_transfer


class InventoryWorkflowTests(TestCase):
    def setUp(self):
        self.factory = StockLocation.objects.create(
            name="Factory",
            location_type=StockLocation.LocationType.FACTORY,
        )
        self.branch = StockLocation.objects.create(
            name="Mwanza",
            location_type=StockLocation.LocationType.BRANCH_MWANZA,
        )
        self.user = User.objects.create_user(
            username="factory-test",
            password="test-password",
            role=User.Role.FACTORY,
        )
        self.product = Product.objects.create(name="Test Diet", sku="TEST-1", unit="bottle")

    def test_purchase_updates_factory_stock(self):
        supplier = Supplier.objects.create(name="Test Supplier")
        purchase = Purchase.objects.create(
            reference="PO-TEST",
            supplier=supplier,
            purchase_date="2026-11-20",
            created_by=self.user,
        )
        PurchaseItem.objects.create(purchase=purchase, product=self.product, quantity=10, unit_cost=100)
        receive_purchase(purchase)
        self.assertEqual(stock_balance(self.product, self.factory), Decimal("10"))

    def test_insufficient_stock_error_shows_product_balance_and_requested_quantity(self):
        with self.assertRaisesMessage(
            ValueError,
            "Test Diet ipo 0 bottle kwenye Factory; umeomba 8 bottle",
        ):
            post_movement(
                product=self.product,
                location=self.factory,
                movement=InventoryLedger.Movement.TRANSFER_OUT,
                quantity=-8,
            )
        self.assertEqual(stock_balance(self.product, self.factory), Decimal("0"))

    def test_transfer_reduces_and_replenishes_stock(self):
        post_movement(product=self.product, location=self.factory, movement="ADJUSTMENT", quantity=20)
        transfer = Transfer.objects.create(
            reference="TR-TEST",
            destination=self.branch,
            dispatched_by=self.user,
        )
        item = TransferItem.objects.create(transfer=transfer, product=self.product, quantity_sent=8)
        dispatch_transfer(transfer)
        dispatch_transfer(transfer)
        receive_transfer(transfer, {str(item.pk): "8"})
        self.assertEqual(stock_balance(self.product, self.factory), Decimal("12"))
        self.assertEqual(stock_balance(self.product, self.branch), Decimal("8"))

    def test_receipt_requires_dispatch_and_applies_only_incremental_quantity(self):
        post_movement(product=self.product, location=self.factory, movement="ADJUSTMENT", quantity=20)
        transfer = Transfer.objects.create(
            reference="TR-PARTIAL",
            destination=self.branch,
            dispatched_by=self.user,
        )
        item = TransferItem.objects.create(
            transfer=transfer,
            product=self.product,
            quantity_sent=8,
        )

        with self.assertRaisesMessage(ValueError, "must be dispatched from store"):
            receive_transfer(transfer, {str(item.pk): "3"})
        self.assertEqual(stock_balance(self.product, self.factory), Decimal("20"))
        self.assertEqual(stock_balance(self.product, self.branch), Decimal("0"))

        dispatch_transfer(transfer)
        receive_transfer(transfer, {str(item.pk): "3"})
        self.assertEqual(stock_balance(self.product, self.factory), Decimal("12"))
        self.assertEqual(stock_balance(self.product, self.branch), Decimal("3"))

        with self.assertRaisesMessage(ValueError, "Received quantity is invalid"):
            receive_transfer(transfer, {str(item.pk): "2"})

        receive_transfer(transfer, {str(item.pk): "8"})
        self.assertEqual(stock_balance(self.product, self.factory), Decimal("12"))
        self.assertEqual(stock_balance(self.product, self.branch), Decimal("8"))

    def test_production_updates_finished_stock(self):
        recipe = Recipe.objects.create(product=self.product, yield_quantity=1)
        batch = ProductionBatch.objects.create(
            reference="BATCH-TEST",
            recipe=recipe,
            quantity=5,
            production_date="2026-11-20",
            created_by=self.user,
        )
        complete_batch(batch)
        self.assertEqual(stock_balance(self.product, self.factory), Decimal("5"))
