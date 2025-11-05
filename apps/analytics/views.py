"""API views for analytics.

Provides endpoints to retrieve aggregated metrics such as total
bookings, revenue and average ratings. This implementation is
simplified and can be extended to match the detailed analytics
described in the technical specification.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework.views import APIView  # type: ignore
from rest_framework.permissions import IsAuthenticated  # type: ignore
from rest_framework.response import Response  # type: ignore

from apps.bookings.models import Booking
from apps.finances.models import Payment
from apps.properties.models import Property
from apps.reviews.models import Review
from django.db import models  # type: ignore


class OverviewAnalyticsView(APIView):
    """Return general statistics for the platform or a specific user."""

    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):  # type: ignore
        user = request.user
        # Determine scope: admin sees all, realtor sees own properties, guest sees their bookings
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            prop_qs = Property.objects.all()
            booking_qs = Booking.objects.all()
            payment_qs = Payment.objects.filter(status=Payment.Status.SUCCESS)
            review_qs = Review.objects.all()
        elif hasattr(user, "is_platform_superuser") and user.is_platform_superuser():
            prop_qs = Property.objects.all()
            booking_qs = Booking.objects.all()
            payment_qs = Payment.objects.filter(status=Payment.Status.SUCCESS)
            review_qs = Review.objects.all()
        elif hasattr(user, "is_super_admin") and user.is_super_admin():
            prop_qs = Property.objects.filter(agency=user.agency)
            booking_qs = Booking.objects.filter(agency=user.agency)
            payment_qs = Payment.objects.filter(
                booking__agency=user.agency,
                status=Payment.Status.SUCCESS,
            )
            review_qs = Review.objects.filter(property__agency=user.agency)
        elif hasattr(user, "is_realtor") and user.is_realtor():
            prop_qs = Property.objects.filter(owner=user)
            booking_qs = Booking.objects.filter(property__owner=user)
            payment_qs = Payment.objects.filter(
                booking__property__owner=user, status=Payment.Status.SUCCESS
            )
            review_qs = Review.objects.filter(property__owner=user)
        else:
            prop_qs = Property.objects.none()
            booking_qs = Booking.objects.filter(guest=user)
            payment_qs = Payment.objects.filter(
                booking__guest=user, status=Payment.Status.SUCCESS
            )
            review_qs = Review.objects.filter(user=user)

        total_properties = prop_qs.count()
        total_bookings = booking_qs.count()
        total_revenue = payment_qs.aggregate(total=models.Sum('amount')).get('total') or Decimal('0')
        avg_rating = review_qs.aggregate(avg=models.Avg('rating')).get('avg') or None

        return Response(
            {
                'properties': total_properties,
                'bookings': total_bookings,
                'revenue': total_revenue,
                'avg_rating': avg_rating,
            }
        )
