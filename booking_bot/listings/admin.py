from django.contrib import admin
from .models import Property, PropertyPhoto

class PropertyPhotoInline(admin.TabularInline):
    model = PropertyPhoto
    extra = 1  # Number of empty forms to display

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'property_class', 'district', 'status', 'number_of_rooms', 'price_per_day', 'created_at')
    search_fields = ('name', 'address', 'owner__username', 'district__name', 'status') # Assuming search by district name
    list_filter = ('property_class', 'number_of_rooms', 'owner', 'district', 'status')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'address', 'owner', 'property_class')
        }),
        ('Details', {
            'fields': ('number_of_rooms', 'area', 'price_per_day', 'district', 'status')
        }),
        ('Access Information', {
            'fields': ('key_safe_code', 'digital_lock_code', 'entry_instructions'),
            'classes': ('collapse',) # Collapsible section
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    inlines = [PropertyPhotoInline]
