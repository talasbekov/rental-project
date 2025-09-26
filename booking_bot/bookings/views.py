import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import generics, status, viewsets, serializers as drf_serializers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Booking
from .serializers import BookingSerializer
from ..users.models import UserProfile
from booking_bot.services.booking_service import (
    BookingError,
    BookingRequest,
    cancel_booking as service_cancel_booking,
    create_booking,
)

User = get_user_model()

logger = logging.getLogger(__name__)


class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def perform_create(self, serializer):
        """Создание бронирования через сервисный слой"""
        logger.info("Creating booking for user: %s", self.request.user)

        data = serializer.validated_data
        request_dto = BookingRequest(
            user=self.request.user,
            property=data["property"],
            start_date=data["start_date"],
            end_date=data["end_date"],
            status="pending_payment",
            hold_calendar=False,
        )

        try:
            booking = create_booking(request_dto)
        except BookingError as exc:
            logger.info("Booking creation failed: %s", exc)
            raise drf_serializers.ValidationError({"detail": str(exc)}) from exc

        serializer.instance = booking

        from booking_bot.bookings.tasks import cancel_expired_booking

        if booking.expires_at:
            cancel_expired_booking.apply_async(args=[booking.id], eta=booking.expires_at)

        return booking

    def get_queryset(self):
        """Фильтрация бронирований по правам доступа"""
        user = self.request.user
        if user.is_authenticated:
            # Админы видят все
            if (
                user.is_staff
                or hasattr(user, "profile")
                and user.profile.role in ["admin", "super_admin"]
            ):
                return Booking.objects.all()
            # Обычные пользователи - только свои
            return Booking.objects.filter(user=user)
        return Booking.objects.none()

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def cancel(self, request, pk=None):
        """Отмена бронирования с освобождением дат"""
        booking = self.get_object()

        # Проверка прав
        if booking.user != request.user and not request.user.is_staff:
            return Response(
                {"error": "У вас нет прав для отмены этого бронирования"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if booking.status == "cancelled":
            return Response(
                {"message": "Бронирование уже отменено"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Блокируем запись для изменения
        cancel_reason = request.data.get("reason", "Отменено пользователем")

        cancelled = service_cancel_booking(booking, reason=cancel_reason)
        cancelled.cancelled_by = request.user
        cancelled.save(update_fields=["cancelled_by"])

        logger.info(
            "Booking %s cancelled by %s, reason: %s",
            booking.id,
            request.user,
            cancel_reason,
        )

        return Response({"message": "Бронирование успешно отменено"})


class UserBookingsListView(generics.ListAPIView):
    serializer_class = (
        BookingSerializer  # Assuming BookingSerializer shows enough detail
    )
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Return bookings for the current authenticated user, ordered by creation date descending
        return Booking.objects.filter(user=self.request.user).order_by("-created_at")
