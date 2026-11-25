from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "category", "action", "actor", "object_type", "object_id", "ip_address")
    list_filter = ("category", "action", "timestamp")
    search_fields = ("action", "object_type", "object_id", "ip_address", "actor__username")
    readonly_fields = (
        "actor", "category", "action", "object_type", "object_id",
        "previous_values", "new_values", "ip_address", "user_agent",
        "request_path", "timestamp",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
