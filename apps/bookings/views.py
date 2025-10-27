"""Booking API views."""

from __future__ import annotations

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Booking, Review
from .serializers import (
    BookingCreateSerializer,
    BookingDetailSerializer,
    BookingSerializer,
    ReviewCreateSerializer,
    ReviewSerializer,
)


class BookingListCreateView(generics.ListCreateAPIView):
    serializer_class = BookingSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return (
            Booking.objects.filter(guest=self.request.user)
            .select_related("property", "guest", "property__owner")
            .prefetch_related("property__amenities", "property__photos")
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return BookingCreateSerializer
        return super().get_serializer_class()

    def perform_create(self, serializer):  # type: ignore[override]
        serializer.save()


class BookingDetailView(generics.RetrieveAPIView):
    serializer_class = BookingDetailSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return (
            Booking.objects.filter(guest=self.request.user)
            .select_related("property", "guest", "property__owner")
            .prefetch_related("property__amenities", "property__photos")
        )


class BookingCancelView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, pk):
        booking = generics.get_object_or_404(Booking, pk=pk, guest=request.user)
        reason = request.data.get("reason", "")
        booking.cancel(by_guest=True, reason=reason)
        return Response(BookingDetailSerializer(booking).data, status=status.HTTP_200_OK)


class ReviewListCreateView(generics.ListCreateAPIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        property_id = self.request.query_params.get("property_id")
        queryset = Review.objects.filter(is_published=True)
        if property_id:
            queryset = queryset.filter(property_id=property_id)
        return queryset.select_related("guest", "booking", "property")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ReviewCreateSerializer
        return ReviewSerializer

    def perform_create(self, serializer):  # type: ignore[override]
        serializer.save()
