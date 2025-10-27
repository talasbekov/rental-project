"""Admin registration for bookings."""

from django.contrib import admin

from .models import Booking, Review


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "property",
        "guest",
        "status",
        "check_in",
        "check_out",
        "total_amount",
        "created_at",
    )
    list_filter = ("status", "check_in", "check_out")
    search_fields = ("id", "guest__email", "property__title")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("booking", "property", "guest", "rating", "is_published", "created_at")
    list_filter = ("is_published", "rating")
    search_fields = ("property__title", "guest__email")
