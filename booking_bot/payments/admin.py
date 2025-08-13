from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "booking",
        "amount",
        "payment_method",
        "transaction_id",
        "status",
        "created_at",
    )
    search_fields = ("booking__id", "transaction_id")
    list_filter = ("status", "payment_method")
    readonly_fields = ("created_at", "updated_at")
