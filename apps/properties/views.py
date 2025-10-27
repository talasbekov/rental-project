"""Views for property catalog."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from django.db.models import Q
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Favorite, Property
from .serializers import (
    FavoriteCreateSerializer,
    FavoriteSerializer,
    PropertyDetailSerializer,
    PropertyListSerializer,
)


class PropertyListView(generics.ListAPIView):
    """Search properties with filtering options."""

    permission_classes = (permissions.AllowAny,)
    serializer_class = PropertyListSerializer

    def get_queryset(self):
        queryset = (
            Property.objects.filter(status=Property.Status.ACTIVE)
            .select_related("owner")
            .prefetch_related("amenities", "photos")
        )
        params = self.request.query_params

        city = params.get("city")
        if city:
            queryset = queryset.filter(city__iexact=city)

        district = params.get("district")
        if district:
            queryset = queryset.filter(district__iexact=district)

        property_type = params.get("type")
        if property_type:
            queryset = queryset.filter(property_type=property_type)

        property_class = params.get("class")
        if property_class:
            queryset = queryset.filter(property_class=property_class)

        min_price = params.get("price_min")
        if min_price:
            queryset = queryset.filter(base_price__gte=min_price)

        max_price = params.get("price_max")
        if max_price:
            queryset = queryset.filter(base_price__lte=max_price)

        min_rooms = params.get("rooms")
        if min_rooms:
            queryset = queryset.filter(rooms__gte=min_rooms)

        min_sleeps = params.get("sleeps")
        if min_sleeps:
            queryset = queryset.filter(sleeps__gte=min_sleeps)

        amenities = params.getlist("amenities")
        if amenities:
            for amenity_id in amenities:
                queryset = queryset.filter(amenities__id=amenity_id)
            queryset = queryset.distinct()

        query = params.get("query")
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) | Q(description__icontains=query) | Q(district__icontains=query)
            )

        check_in = params.get("check_in")
        check_out = params.get("check_out")
        if check_in and check_out:
            queryset = self._exclude_unavailable(queryset, check_in, check_out)

        ordering = params.get("sort")
        if ordering == "price_asc":
            queryset = queryset.order_by("base_price")
        elif ordering == "price_desc":
            queryset = queryset.order_by("-base_price")
        else:
            queryset = queryset.order_by("-created_at")

        return queryset

    def _exclude_unavailable(self, queryset, check_in: str, check_out: str):
        try:
            check_in_date = datetime.fromisoformat(check_in).date()
            check_out_date = datetime.fromisoformat(check_out).date()
        except ValueError:
            return queryset

        # Lazy import to avoid circular dependency until booking module is loaded.
        try:
            from apps.bookings.models import Booking  # type: ignore
        except Exception:  # pragma: no cover - booking app may not exist yet
            return queryset

        overlapping_statuses: Iterable[str] = (
            Booking.Status.PENDING,
            Booking.Status.CONFIRMED,
            Booking.Status.IN_PROGRESS,
        )

        conflicting_property_ids = (
            Booking.objects.filter(
                status__in=overlapping_statuses,
                check_in__lt=check_out_date,
                check_out__gt=check_in_date,
            )
            .values_list("property_id", flat=True)
            .distinct()
        )
        return queryset.exclude(id__in=conflicting_property_ids)


class PropertyDetailView(generics.RetrieveAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = PropertyDetailSerializer
    queryset = Property.objects.filter(status__in=[Property.Status.ACTIVE, Property.Status.INACTIVE]).select_related(
        "owner"
    ).prefetch_related("amenities", "photos")


class FavoriteListCreateView(generics.ListCreateAPIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return Favorite.objects.filter(user=self.request.user).select_related("property", "property__owner").prefetch_related(
            "property__amenities", "property__photos"
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return FavoriteCreateSerializer
        return FavoriteSerializer

    def perform_create(self, serializer):  # type: ignore[override]
        serializer.save()


class FavoriteDeleteView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def delete(self, request, property_id):
        Favorite.objects.filter(user=request.user, property_id=property_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
