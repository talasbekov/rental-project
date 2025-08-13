from django.contrib.auth import get_user_model
from rest_framework import viewsets, status, serializers as drf_serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Booking
from .serializers import BookingSerializer
from rest_framework.permissions import IsAuthenticated, AllowAny

# TODO: Add custom permission to ensure only booking owner or admin can cancel/modify
from rest_framework import generics  # Added for ListAPIView

from ..users.models import UserProfile

User = get_user_model()

# booking_bot/bookings/views.py - исправленная версия с защитой от гонок

from django.db import transaction
from django.db.models import Q
from rest_framework import viewsets, status, serializers as drf_serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def perform_create(self, serializer):
        """Создание бронирования с защитой от гонок"""
        logger.info(f"Creating booking for user: {self.request.user}")

        # Получаем данные из валидированного сериализатора
        prop = serializer.validated_data["property"]
        sd = serializer.validated_data["start_date"]
        ed = serializer.validated_data["end_date"]

        # Блокируем квартиру для проверки (SELECT FOR UPDATE)
        locked_property = Property.objects.select_for_update().get(id=prop.id)

        # Проверяем доступность на выбранные даты
        conflicting_bookings = Booking.objects.filter(
            property=locked_property,
            status__in=["pending_payment", "confirmed"],
            start_date__lt=ed,
            end_date__gt=sd,
        ).exists()

        if conflicting_bookings:
            raise drf_serializers.ValidationError(
                {"dates": "Выбранные даты уже забронированы"}
            )

        # Вычисляем стоимость
        duration = (ed - sd).days
        if duration <= 0:
            raise drf_serializers.ValidationError(
                "Минимальный срок бронирования - 1 день"
            )

        total_price = duration * locked_property.price_per_day

        # Создаем бронирование со статусом pending_payment
        booking = serializer.save(
            user=self.request.user,
            total_price=total_price,
            status="pending_payment",
            expires_at=datetime.now() + timedelta(minutes=15),  # 15 минут на оплату
        )

        logger.info(f"Booking created: {booking.id}, expires at {booking.expires_at}")

        # Запускаем отложенную задачу для отмены неоплаченного бронирования
        from booking_bot.bookings.tasks import cancel_expired_booking

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
        locked_booking = Booking.objects.select_for_update().get(id=booking.id)

        # Сохраняем причину отмены
        cancel_reason = request.data.get("reason", "Отменено пользователем")

        locked_booking.status = "cancelled"
        locked_booking.cancelled_at = datetime.now()
        locked_booking.cancel_reason = cancel_reason
        locked_booking.save()

        # Освобождаем календарные дни (если используется система календаря)
        if hasattr(self, "_update_calendar_availability"):
            self._update_calendar_availability(locked_booking, "free")

        logger.info(
            f"Booking {booking.id} cancelled by {request.user}, reason: {cancel_reason}"
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
