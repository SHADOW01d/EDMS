from django.contrib import admin

from .models import Sale, SaleItem


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 1


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("reference", "location", "customer", "sold_at", "total_amount")
    list_filter = ("location",)
    inlines = (SaleItemInline,)
