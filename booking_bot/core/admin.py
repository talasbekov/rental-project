from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "timestamp",
        "user",
        "action",
        "object_type",
        "object_id",
        "ip_address",
    )
    list_filter = ("action", "object_type", "timestamp")
    search_fields = ("user__username", "ip_address", "details")
    date_hierarchy = "timestamp"
    readonly_fields = (
        "user",
        "action",
        "object_type",
        "object_id",
        "details",
        "ip_address",
        "user_agent",
        "timestamp",
        "telegram_chat_id",
        "whatsapp_phone",
    )

    def has_add_permission(self, request):
        # Запрещаем создание логов через админку
        return False

    def has_delete_permission(self, request, obj=None):
        # Только суперпользователи могут удалять логи
        return request.user.is_superuser
