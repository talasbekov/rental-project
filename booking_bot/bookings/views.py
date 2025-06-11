from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Booking, Property
from .serializers import BookingSerializer
from rest_framework.permissions import IsAuthenticated
# TODO: Add custom permission to ensure only booking owner or admin can cancel/modify

class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated] # Ensure user is authenticated

    def perform_create(self, serializer):
        property_obj = serializer.validated_data['property']
        start_date = serializer.validated_data['start_date']
        end_date = serializer.validated_data['end_date']

        duration = (end_date - start_date).days
        if duration <= 0: # Should be caught by serializer validation, but double check
            raise serializers.ValidationError("Booking duration must be at least 1 day.")

        total_price = duration * property_obj.price_per_day

        # Set user to current authenticated user
        serializer.save(user=self.request.user, total_price=total_price, status='pending')

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated]) # Add more specific permission later
    def cancel(self, request, pk=None):
        booking = self.get_object()

        # Add logic here: who can cancel?
        # For now, let's assume the user who booked it or an admin.
        if booking.user != request.user: # and not request.user.profile.role in ['admin', 'super_admin']:
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
            # and profile to have role. Assuming this from previous UserProfile setup.
            if hasattr(user, 'profile') and user.profile.role in ['admin', 'super_admin']:
                return Booking.objects.all()
            return Booking.objects.filter(user=user)
        return Booking.objects.none() # Should not happen if IsAuthenticated is effective
