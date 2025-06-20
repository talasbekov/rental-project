from django.contrib.auth import get_user_model
from rest_framework import viewsets, status, serializers as drf_serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Booking
from .serializers import BookingSerializer
from rest_framework.permissions import IsAuthenticated, AllowAny
# TODO: Add custom permission to ensure only booking owner or admin can cancel/modify
from rest_framework import generics # Added for ListAPIView

from ..users.models import UserProfile

User = get_user_model()

class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # User is now self.request.user due to IsAuthenticated permission class
        # No need to manually fetch or create UserProfile based on telegram_id here for booking creation,
        # as the user should already exist and be authenticated.

        # вычисляем цену
        prop = serializer.validated_data['property']
        sd = serializer.validated_data['start_date']
        ed = serializer.validated_data['end_date']
        duration = (ed - sd).days
        if duration <= 0:
            raise drf_serializers.ValidationError("Booking duration must be at least 1 day.")
        total_price = duration * prop.price_per_day

        # сохраняем бронь: сразу привязываем аутентифицированного пользователя
        serializer.save(
            user=self.request.user, # CHANGED from profile to self.request.user
            total_price=total_price,
            status='pending'
        )

    @action(detail=True, methods=['post']) # Add more specific permission later
    def cancel(self, request, pk=None):
        booking = self.get_object()

        # Add logic here: who can cancel?
        # For now, let's assume the user who booked it or an admin.
        # Make sure request.user is the Django User model instance
        if booking.user != request.user and not (hasattr(request.user, 'is_staff') and request.user.is_staff): # Example: allow staff/admin
             return Response({'error': 'You do not have permission to cancel this booking.'}, status=status.HTTP_403_FORBIDDEN)

        if booking.status == 'cancelled':
            return Response({'message': 'Booking is already cancelled.'}, status=status.HTTP_400_BAD_REQUEST)

        # Add conditions under which a booking can be cancelled (e.g., not too close to start_date)

        booking.status = 'cancelled'
        booking.save()
        return Response({'message': 'Booking cancelled successfully.'})

    def get_queryset(self):
        """
        Users should only see their own bookings unless they are admin/super_admin.
        """
        user = self.request.user
        if user.is_authenticated:
            # This check for profile and role needs User model to have profile linked,
            # and profile to have role. Or use Django's built-in is_staff or is_superuser.
            # Example using is_staff for admin-like access:
            if hasattr(user, 'is_staff') and user.is_staff:
                return Booking.objects.all()
            return Booking.objects.filter(user=user)
        return Booking.objects.none() # Should not happen if IsAuthenticated is effective


class UserBookingsListView(generics.ListAPIView):
    serializer_class = BookingSerializer # Assuming BookingSerializer shows enough detail
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Return bookings for the current authenticated user, ordered by creation date descending
        return Booking.objects.filter(user=self.request.user).order_by('-created_at')
