from django.contrib import admin

from .models import ProductionBatch, ProductionOutput, Recipe, RecipeItem


class RecipeItemInline(admin.TabularInline):
    model = RecipeItem
    extra = 1


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("product", "yield_quantity")
    inlines = (RecipeItemInline,)


@admin.register(ProductionBatch)
class ProductionBatchAdmin(admin.ModelAdmin):
    list_display = ("reference", "quantity", "status", "created_by", "approved_by", "production_date")
    list_filter = ("status",)


@admin.register(ProductionOutput)
class ProductionOutputAdmin(admin.ModelAdmin):
    list_display = ("reference", "batch", "product", "quantity", "production_date", "created_by")
    list_filter = ("product", "production_date")
