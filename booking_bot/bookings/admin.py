from django.contrib import admin
from .models import Booking

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'property', 'start_date', 'end_date', 'status', 'total_price', 'created_at')
    search_fields = ('user__username', 'property__name')
    list_filter = ('status', 'start_date', 'end_date')
    readonly_fields = ('created_at', 'updated_at', 'total_price') # Assuming total_price might be calculated
