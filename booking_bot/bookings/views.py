from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Booking, Property
from .serializers import BookingSerializer
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.openapi import AutoSchema
from rest_framework import generics # Added for ListAPIView
from booking_bot.users.models import UserProfile # Needed to find user by telegram_chat_id
from django.contrib.auth.models import User # Needed for UserProfile.user


class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]
    schema = AutoSchema()

    def perform_create(self, serializer):
        property_obj = serializer.validated_data['property']
        start_date = serializer.validated_data['start_date']
        end_date = serializer.validated_data['end_date']

        duration = (end_date - start_date).days
        if duration <= 0:
            raise serializers.ValidationError("Booking duration must be at least 1 day.")

        total_price = duration * property_obj.price_per_day

        user_to_book = None
        # Check if request.user exists and is authenticated
        if hasattr(self.request, 'user') and self.request.user and self.request.user.is_authenticated:
            user_to_book = self.request.user
        else:
            # If user is anonymous, try to get user from telegram_chat_id passed by bot
            telegram_chat_id = serializer.validated_data.get('telegram_chat_id')
            if telegram_chat_id:
                try:
                    profile = UserProfile.objects.get(telegram_chat_id=telegram_chat_id)
                    user_to_book = profile.user
                except UserProfile.DoesNotExist:
                    raise serializers.ValidationError(f"User profile for telegram_chat_id {telegram_chat_id} not found.")

        if not user_to_book:
            raise serializers.ValidationError("User could not be determined for booking. Ensure telegram_chat_id is provided if user is anonymous.")

        serializer.save(user=user_to_book, total_price=total_price, status='pending')

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        if booking.user != request.user: # and not request.user.profile.role in ['admin', 'super_admin']:
             return Response({'error': 'You do not have permission to cancel this booking.'}, status=status.HTTP_403_FORBIDDEN)

        if booking.status == 'cancelled':
            return Response({'message': 'Booking is already cancelled.'}, status=status.HTTP_400_BAD_REQUEST)

        booking.status = 'cancelled'
        booking.save()
        return Response({'message': 'Booking cancelled successfully.'})

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated:
            if hasattr(user, 'profile') and user.profile.role in ['admin', 'super_admin']:
                return Booking.objects.all()
            return Booking.objects.filter(user=user)
        return Booking.objects.none()


class UserBookingsListView(generics.ListAPIView):
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Booking.objects.filter(user=self.request.user).order_by('-created_at')
