from django.contrib import admin
from .models import Property

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'property_class', 'number_of_rooms', 'price_per_day', 'created_at')
    search_fields = ('name', 'address', 'owner__username')
    list_filter = ('property_class', 'number_of_rooms', 'owner')
    readonly_fields = ('created_at', 'updated_at')
