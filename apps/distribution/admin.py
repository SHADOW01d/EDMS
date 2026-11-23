from django.contrib import admin

from .models import Transfer, TransferItem


class TransferItemInline(admin.TabularInline):
    model = TransferItem
    extra = 1


@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    list_display = ("reference", "destination", "status", "dispatched_at", "received_at")
    list_filter = ("status", "destination")
    inlines = (TransferItemInline,)
