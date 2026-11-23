from django.contrib import admin

from .models import ProductionBatch, Recipe, RecipeItem


class RecipeItemInline(admin.TabularInline):
    model = RecipeItem
    extra = 1


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("product", "yield_quantity")
    inlines = (RecipeItemInline,)


@admin.register(ProductionBatch)
class ProductionBatchAdmin(admin.ModelAdmin):
    list_display = ("reference", "recipe", "quantity", "status", "production_date")
    list_filter = ("status",)
