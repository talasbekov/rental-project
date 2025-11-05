"""Admin registrations for properties domain."""

from __future__ import annotations

from django.contrib import admin
from mptt.admin import MPTTModelAdmin

from .models import Amenity, Location, Property, PropertyAvailability, PropertyPhoto, PropertySeasonalRate, PropertyType


@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "icon")
    list_filter = ("category",)
    search_fields = ("name", "category")


class PropertyPhotoInline(admin.TabularInline):
    model = PropertyPhoto
    extra = 0
    fields = ("image", "caption", "order", "is_primary")


class PropertySeasonalRateInline(admin.TabularInline):
    model = PropertySeasonalRate
    extra = 0
    fields = ("start_date", "end_date", "price_per_night", "min_nights")


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "city",
        "district",
        "property_type",
        "status",
        "base_price",
        "max_guests",
        "owner",
    )
    list_filter = ("status", "city", "property_type", "property_class", "has_pets_allowed")
    search_fields = ("title", "city", "district", "owner__email")
    inlines = (PropertyPhotoInline, PropertySeasonalRateInline)
    filter_horizontal = ("amenities",)
    readonly_fields = ("created_at", "updated_at", "published_at")


@admin.register(PropertyPhoto)
class PropertyPhotoAdmin(admin.ModelAdmin):
    list_display = ("property", "order", "is_primary", "uploaded_at")
    list_filter = ("is_primary",)
    search_fields = ("property__title",)


@admin.register(PropertyType)
class PropertyTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")


@admin.register(PropertyAvailability)
class PropertyAvailabilityAdmin(admin.ModelAdmin):
    list_display = ("property", "start_date", "end_date", "status", "source")
    list_filter = ("status", "source")
    search_fields = ("property__title",)


@admin.register(Location)
class LocationAdmin(MPTTModelAdmin):
    list_display = ("name", "parent", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    mptt_level_indent = 20
