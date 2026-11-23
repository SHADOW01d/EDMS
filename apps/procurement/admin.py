from django.contrib import admin

from .models import Purchase, PurchaseItem, Supplier


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 1


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("reference", "supplier", "purchase_date", "status", "total_amount")
    list_filter = ("status",)
    inlines = (PurchaseItemInline,)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "active")
