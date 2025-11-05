"""Admin registration for bookings."""

from __future__ import annotations

from django.contrib import admin

from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "booking_code",
        "property",
        "guest",
        "status",
        "payment_status",
        "check_in",
        "check_out",
        "total_price",
        "created_at",
    )
    list_filter = ("status", "payment_status", "check_in", "check_out", "source")
    search_fields = ("booking_code", "property__title", "guest__email")
    readonly_fields = (
        "booking_code",
        "created_at",
        "updated_at",
        "total_price",
        "total_nights",
        "nightly_rate",
    )
