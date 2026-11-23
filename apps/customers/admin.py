from django.contrib import admin

from .models import BranchDailyReport, BranchExpense, Customer, CustomerCall


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "phone", "email", "active")
    list_filter = ("location", "active")
    search_fields = ("name", "phone", "email")


@admin.register(CustomerCall)
class CustomerCallAdmin(admin.ModelAdmin):
    list_display = ("customer", "called_by", "called_at", "outcome", "follow_up_date")
    list_filter = ("outcome",)


@admin.register(BranchExpense)
class BranchExpenseAdmin(admin.ModelAdmin):
    list_display = ("location", "category", "amount", "expense_date", "recorded_by")


@admin.register(BranchDailyReport)
class BranchDailyReportAdmin(admin.ModelAdmin):
    list_display = ("location", "report_date", "status", "submitted_by", "approved_by")
    list_filter = ("location", "status")
