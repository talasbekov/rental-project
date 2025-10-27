"""Admin registrations for properties domain."""

from django.contrib import admin

from .models import Amenity, Favorite, Property, PropertyPhoto


@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ("name", "category")
    list_filter = ("category",)
    search_fields = ("name",)


class PropertyPhotoInline(admin.TabularInline):
    model = PropertyPhoto
    extra = 0


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("title", "city", "district", "property_type", "status", "base_price", "owner")
    list_filter = ("status", "city", "property_type", "property_class")
    search_fields = ("title", "city", "district", "owner__email")
    inlines = (PropertyPhotoInline,)
    filter_horizontal = ("amenities",)


@admin.register(PropertyPhoto)
class PropertyPhotoAdmin(admin.ModelAdmin):
    list_display = ("property", "order", "is_primary", "uploaded_at")
    list_filter = ("is_primary",)
    search_fields = ("property__title",)


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("user", "property", "created_at")
    search_fields = ("user__email", "property__title")
