"""URL routing for the properties domain."""

from __future__ import annotations

from django.urls import include, path  # type: ignore
from rest_framework.routers import DefaultRouter  # type: ignore

from .views import (
    AmenityViewSet,
    PropertyAvailabilityViewSet,
    PropertyCalendarSettingsView,
    PropertyPublicCalendarView,
    PropertySeasonalRateViewSet,
    PropertyTypeViewSet,
    PropertyViewSet,
    SearchPropertiesView,
)

router = DefaultRouter()
router.register(r"", PropertyViewSet, basename="property")
router.register(r"types", PropertyTypeViewSet, basename="property-type")
router.register(r"amenities", AmenityViewSet, basename="amenity")

availability_list = PropertyAvailabilityViewSet.as_view({"get": "list", "post": "create"})
availability_detail = PropertyAvailabilityViewSet.as_view(
    {"patch": "partial_update", "put": "update", "delete": "destroy", "get": "retrieve"}
)
availability_bulk_delete = PropertyAvailabilityViewSet.as_view({"post": "bulk_delete"})

seasonal_list = PropertySeasonalRateViewSet.as_view({"get": "list", "post": "create"})
seasonal_detail = PropertySeasonalRateViewSet.as_view(
    {"patch": "partial_update", "put": "update", "delete": "destroy", "get": "retrieve"}
)
seasonal_bulk_delete = PropertySeasonalRateViewSet.as_view({"post": "bulk_delete"})

urlpatterns = [
    path("", include(router.urls)),
    # Search endpoint
    path("search/", SearchPropertiesView.as_view(), name="property-search"),
    # Calendar availability management
    path(
        "<int:property_id>/calendar/availability/",
        availability_list,
        name="property-availability-list",
    ),
    path(
        "<int:property_id>/calendar/availability/<int:pk>/",
        availability_detail,
        name="property-availability-detail",
    ),
    path(
        "<int:property_id>/calendar/availability/bulk-delete/",
        availability_bulk_delete,
        name="property-availability-bulk-delete",
    ),
    # Seasonal rates
    path(
        "<int:property_id>/calendar/seasonal-rates/",
        seasonal_list,
        name="property-seasonal-rate-list",
    ),
    path(
        "<int:property_id>/calendar/seasonal-rates/<int:pk>/",
        seasonal_detail,
        name="property-seasonal-rate-detail",
    ),
    path(
        "<int:property_id>/calendar/seasonal-rates/bulk-delete/",
        seasonal_bulk_delete,
        name="property-seasonal-rate-bulk-delete",
    ),
    # Calendar settings
    path(
        "<int:property_id>/calendar/settings/",
        PropertyCalendarSettingsView.as_view(),
        name="property-calendar-settings",
    ),
    # Public calendar
    path(
        "<int:property_id>/calendar/public/",
        PropertyPublicCalendarView.as_view(),
        name="property-calendar-public",
    ),
]
