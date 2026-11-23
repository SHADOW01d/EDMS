from django.contrib import admin

from .models import InventoryLedger, Product, StockLocation


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "unit", "unit_price", "reorder_level", "active")
    list_filter = ("category", "active")
    search_fields = ("name", "sku")


@admin.register(StockLocation)
class StockLocationAdmin(admin.ModelAdmin):
    list_display = ("name", "location_type")


@admin.register(InventoryLedger)
class InventoryLedgerAdmin(admin.ModelAdmin):
    list_display = ("created_at", "product", "location", "movement", "quantity", "balance_after", "reference")
    list_filter = ("movement", "location")
    search_fields = ("product__name", "product__sku", "reference")
