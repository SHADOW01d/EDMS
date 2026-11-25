from django.contrib import admin

from .models import (
    BranchDailyReport,
    BranchDelivery,
    BranchExpense,
    Customer,
    CustomerCall,
    CustomerVisit,
)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "phone", "diagnosis", "active")
    list_filter = ("location", "active")
    search_fields = ("name", "phone", "diagnosis", "short_description")
    fields = (
        "name",
        "location",
        "phone",
        "diagnosis",
        "short_description",
        "address",
        "active",
    )


@admin.register(CustomerCall)
class CustomerCallAdmin(admin.ModelAdmin):
    list_display = ("contact_name", "location", "direction", "call_type", "called_by", "called_at", "outcome", "follow_up_date")
    list_filter = ("direction", "call_type", "called_at")
    search_fields = ("customer__name", "caller_name", "caller_phone", "outcome", "notes")

    @admin.display(description="Contact")
    def contact_name(self, obj):
        return obj.contact_name


@admin.register(CustomerVisit)
class CustomerVisitAdmin(admin.ModelAdmin):
    list_display = ("contact_name", "location", "visit_type", "visited_at", "recorded_by")
    list_filter = ("location", "visit_type", "visited_at")
    search_fields = ("visitor_name", "visitor_phone", "customer__name", "notes")
    readonly_fields = ("visited_at",)

    @admin.display(description="Visitor")
    def contact_name(self, obj):
        return obj.contact_name


@admin.register(BranchDelivery)
class BranchDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "recipient_name",
        "location",
        "delivery_date",
        "parcel_count",
        "status",
        "recorded_by",
    )
    list_filter = ("location", "status", "delivery_date")
    search_fields = ("recipient_name", "recipient_phone", "destination", "customer__name")


@admin.register(BranchExpense)
class BranchExpenseAdmin(admin.ModelAdmin):
    list_display = ("location", "category", "amount", "expense_date", "recorded_by")


@admin.register(BranchDailyReport)
class BranchDailyReportAdmin(admin.ModelAdmin):
    list_display = ("location", "report_date", "status", "submitted_by", "approved_by")
    list_filter = ("location", "status")
