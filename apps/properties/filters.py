"""FilterSet definitions for properties search and listing."""

from __future__ import annotations

import django_filters  # type: ignore
from django.db.models import Count, Q  # type: ignore

from .models import Property


class PropertyFilterSet(django_filters.FilterSet):
    """FilterSet for Property with common filters used in list and search."""

    city = django_filters.CharFilter(field_name="city", lookup_expr="icontains")
    district = django_filters.CharFilter(field_name="district", lookup_expr="icontains")
    property_type = django_filters.NumberFilter(field_name="property_type_id", lookup_expr="exact")
    property_class = django_filters.CharFilter(field_name="property_class", lookup_expr="exact")

    rooms_min = django_filters.NumberFilter(field_name="rooms", lookup_expr="gte")
    rooms_max = django_filters.NumberFilter(field_name="rooms", lookup_expr="lte")
    price_min = django_filters.NumberFilter(field_name="base_price", lookup_expr="gte")
    price_max = django_filters.NumberFilter(field_name="base_price", lookup_expr="lte")
    guests = django_filters.NumberFilter(method="filter_guests")

    # CSV of amenity ids, requires all selected amenities
    amenities = django_filters.CharFilter(method="filter_amenities")

    class Meta:
        model = Property
        fields = [
            "city",
            "district",
            "property_type",
            "property_class",
        ]

    def filter_guests(self, queryset, name, value):  # type: ignore
        try:
            guests = int(value)
        except Exception:  # noqa: BLE001
            return queryset
        return queryset.filter(max_guests__gte=guests)

    def filter_amenities(self, queryset, name, value):  # type: ignore
        if not value:
            return queryset
        try:
            ids = [int(x) for x in str(value).replace(" ", "").split(",") if x]
        except Exception:  # noqa: BLE001
            return queryset
        if not ids:
            return queryset
        # Require all of the amenities: annotate count of matched amenities
        qs = queryset.filter(amenities__id__in=ids).annotate(
            matched_amenities=Count("amenities", filter=Q(amenities__id__in=ids), distinct=True)
        ).filter(matched_amenities=len(ids))
        return qs.distinct()

